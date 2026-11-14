"""Adversarial production regressions: ambiguous data, malformed state and isolation."""

import unittest
from unittest.mock import patch

import httpx
from app.schemas.user import UserCreate, UserUpdate
from app.services import chat_results, cuzk_client, geo_data
from pydantic import ValidationError


class ProductionEdges(unittest.TestCase):
    def setUp(self):
        chat_results._cache.clear()
        self.addCleanup(chat_results._cache.clear)

    def test_account_updates_reject_null_and_oversized_values_before_db(self):
        for body in [
            {"password": None},
            {"username": None},
            {"username": "x" * 51},
            {"username": "   "},
            {"username": "bad\x00name"},
            {"profile": {"firstname": None}},
            {"profile": {"lastname": "x" * 101}},
        ]:
            with self.subTest(body=repr(body)):
                with self.assertRaises(ValidationError):
                    UserUpdate.model_validate(body)

    def test_registration_rejects_blank_username_and_unbounded_password(self):
        for username, password in [("   ", "long-enough"), ("name", "x" * 4097)]:
            with self.assertRaises(ValidationError):
                UserCreate(
                    username=username,
                    password=password,
                    profile={"firstname": "A", "lastname": "B"},
                )

    def test_ambiguous_address_does_not_choose_first_hit(self):
        candidates = [
            {"adresa": "Náměstí 1, obec A", "lon": 13, "lat": 49},
            {"adresa": "Náměstí 1, obec B", "lon": 14, "lat": 50},
        ]
        with (
            patch.object(cuzk_client, "search_address", return_value=candidates),
            patch.object(
                geo_data,
                "read_connection",
                side_effect=AssertionError("Must not select first address"),
            ),
        ):
            result = geo_data.prevalidate_address(adresa="Náměstí 1")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["candidates"]), 2)

    def test_arcgis_http_200_error_is_not_a_successful_zoning_lookup(self):
        client = httpx.Client
        with patch.object(
            cuzk_client.httpx,
            "Client",
            side_effect=lambda **kw: client(
                **kw,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json={"error": {"code": 499, "message": "Token required"}}
                    )
                ),
            ),
        ):
            result = cuzk_client.fetch_zoning_at_point(13.4, 49.7)
        self.assertFalse(result["zoning_plan"]["available"])
        self.assertIn("error", result["zoning_plan"])
        self.assertIsNone(result["zoning_plan"].get("is_developable_area"))

    def test_missing_zoning_coverage_does_not_mean_non_buildable(self):
        client = httpx.Client
        with patch.object(
            cuzk_client.httpx,
            "Client",
            side_effect=lambda **kw: client(
                **kw,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                ),
            ),
        ):
            result = cuzk_client.fetch_zoning_at_point(13.4, 49.7)
        self.assertFalse(result["zoning_plan"]["available"])
        self.assertIsNone(result["zoning_plan"]["is_developable_area"])
        self.assertIsNone(result["zoning_plan"]["in_built_up_area"])

    def test_one_user_cannot_flush_another_users_recent_results(self):
        payload = {"title": "Data", "columns": [], "rows": []}
        victim = chat_results.remember(payload, 1)
        for _ in range(130):
            chat_results.remember(payload, 2)
        self.assertIn(victim.result_id, chat_results.restore([victim.result_id], 1))

    def test_city_summary_does_not_replay_a_previous_parcel_comparison(self):
        item = chat_results.remember(
            {
                "title": "Porovnání parcel",
                "columns": [],
                "rows": [
                    {"id": "parcela:1", "area_m2": 20, "assessment_kind": "indicative"},
                    {"id": "parcela:2", "area_m2": 40, "assessment_kind": "indicative"},
                ],
            },
            1,
        )
        self.assertIsNone(
            chat_results.requested_comparison_reference(
                "Nové téma: shrň porovnání měst podle obyvatel", {item.result_id: item}
            )
        )

    def test_sort_handles_mixed_legacy_values(self):
        item = chat_results.remember(
            {
                "title": "Data",
                "columns": [{"key": "name", "label": "Název"}],
                "rows": [{"id": "a", "name": "A"}, {"id": "b", "name": 3}],
            },
            1,
        )
        result = chat_results.transform(
            {"result_id": item.result_id, "sort_key": "name"}, {item.result_id: item}, 1
        )
        self.assertEqual(len(result.rows), 2)

    def test_model_map_links_become_real_owned_map_artifacts(self):
        item = chat_results.remember(
            {
                "title": "Místo",
                "columns": [],
                "rows": [],
                "features": [
                    {
                        "type": "Feature",
                        "id": "a",
                        "properties": {},
                        "geometry": {"type": "Point", "coordinates": [13, 49]},
                    }
                ],
            },
            1,
        )
        text, shown = chat_results.repair_tool_links(
            f"[Zobrazit](show_map?result_id={item.result_id})", {item.result_id: item}, []
        )
        self.assertEqual(text, "Zobrazit")
        self.assertEqual(shown[0].view, "map")
        self.assertEqual(shown[0].features, item.features)
        text, shown = chat_results.repair_tool_links(
            f"[Cizí](show_map?result_id={item.result_id})",
            chat_results.restore([item.result_id], 2),
            [],
        )
        self.assertFalse(shown)
        self.assertIn("není dostupný", text)

    def test_password_work_is_bounded_before_expensive_hashing(self):
        import threading

        from app.services import passwords
        from fastapi import HTTPException

        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        try:
            with (
                patch.object(passwords, "_slots", slots),
                patch.object(passwords._hash, "hash") as hash_call,
            ):
                with self.assertRaises(HTTPException) as error:
                    passwords.hash_password("not-a-real-password")
                self.assertEqual(error.exception.status_code, 429)
                hash_call.assert_not_called()
        finally:
            slots.release()

    def test_fallback_text_contains_verified_values_and_distinguishes_unknown(self):
        item = chat_results.remember(
            {
                "title": "Prověření",
                "columns": [
                    {"key": "area", "label": "Výměra", "numeric": True, "unit": "m²"},
                    {"key": "risk", "label": "Průnik Q100"},
                    {"key": "radon", "label": "Radon"},
                ],
                "rows": [{"area": 123.5, "risk": False, "radon": None}],
                "note": "Omezené pokrytí.",
            },
            1,
        )
        answer = chat_results.fallback_answer([item])
        self.assertIn("123,5 m²", answer)
        self.assertIn("Průnik Q100:** ne", answer)
        self.assertIn("Radon:** neověřeno", answer)
        self.assertIn("Omezené pokrytí", answer)
