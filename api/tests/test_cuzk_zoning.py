"""Deterministic unit tests for Plzeňský kraj zoning/radon lookup and ČÚZK client helpers."""

import unittest
from unittest.mock import patch

import httpx
from app.services import cuzk_client, geo_data


class CuzkZoningTests(unittest.TestCase):
    def test_fetch_zoning_at_point_parses_layers_and_filters_nulls(self):
        sample_payload = {
            "results": [
                {
                    "layerId": 11,
                    "layerName": "Hranice zastavěného území obce - plocha A001",
                    "attributes": {
                        "název zdroje": "ÚP Plzeň",
                        "datum vydání": "31.5.2016",
                    },
                },
                {
                    "layerId": 443,
                    "layerName": "Plochy s rozdílným způsobem využití",
                    "attributes": {
                        "kód funkční plochy": "SM - plocha smíšená obytná městská",
                        "název jevu ": "SM - plocha smíšená obytná městská",
                        "intenzita využití území": "obytné",
                        "Popis jevu": "Bolevec",
                        "časový horizont jevu": "1 - stav",
                        "popis zdroje": "Územní plán Plzeň - zapracování KÚPK",
                        "datum vydání": "1.10.2016",
                        "zda je v souladu s platnou ÚPD": "S - soulad s ÚPD",
                        "zda jde o veřejně prospěšnou stavbu nebo opatření": "X - není VPS/VPO",
                        "poskytovatel údaje o území": "Null",
                    },
                },
                {
                    "layerId": 8,
                    "layerName": "Zastavitelná plocha - plocha A001b",
                    "attributes": {
                        "kód funkční plochy": "BI - bydlení individuální",
                        "časový horizont jevu": "2 - návrh",
                        "číslo lokality dle evidence CzechInvest nebo evidence obce či kraje": "Z12",
                    },
                },
                {
                    "layerId": 441,
                    "layerName": "Radonové riziko - plocha A062",
                    "attributes": {
                        "kategorie (typ) prvku": "střední",
                        "doplňující poznámka": "sediment deluvioeolický",
                    },
                },
            ]
        }

        def handler(request):
            self.assertIn("mapExtent=", str(request.url))
            return httpx.Response(200, json=sample_payload)

        real_client = httpx.Client

        def mock_client(*args, **kwargs):
            return real_client(transport=httpx.MockTransport(handler))

        with patch("app.services.cuzk_client.httpx.Client", side_effect=mock_client):
            result = cuzk_client.fetch_zoning_at_point(13.3742, 49.7760)

        zoning = result["zoning_plan"]
        self.assertTrue(zoning["available"])
        self.assertTrue(zoning["in_built_up_area"])
        self.assertEqual(zoning["built_up_area_source"], "ÚP Plzeň (31.5.2016)")
        self.assertTrue(zoning["is_developable_area"])
        self.assertFalse(zoning["is_non_developable_parcel"])
        self.assertEqual(len(zoning["functional_uses"]), 1)
        self.assertEqual(
            zoning["functional_uses"][0]["kod_funkce"],
            "SM - plocha smíšená obytná městská",
        )
        self.assertEqual(zoning["developable_areas"][0]["lokalita"], "Z12")
        self.assertEqual(result["radon_risk"]["category"], "střední")
        self.assertEqual(result["radon_risk"]["geology"], "sediment deluvioeolický")

    def test_fetch_zoning_handles_upstream_failure_gracefully(self):
        def handler(request):
            return httpx.Response(503)

        real_client = httpx.Client

        def mock_client(*args, **kwargs):
            return real_client(transport=httpx.MockTransport(handler))

        with patch("app.services.cuzk_client.httpx.Client", side_effect=mock_client):
            result = cuzk_client.fetch_zoning_at_point(13.3742, 49.7760)

        self.assertFalse(result["zoning_plan"]["available"])
        self.assertIn("error", result["zoning_plan"])
        self.assertIsNone(result["radon_risk"])

    def test_enrich_with_zoning_merges_payload(self):
        fake_zoning = {
            "zoning_plan": {"available": True, "in_built_up_area": True},
            "radon_risk": {"category": "střední"},
        }
        with patch("app.services.cuzk_client.fetch_zoning_at_point", return_value=fake_zoning):
            enriched = geo_data._enrich_with_zoning({"parcel": {"cislo": "841/1"}}, 13.37, 49.77)
        self.assertTrue(enriched["zoning_plan"]["in_built_up_area"])
        self.assertEqual(enriched["radon_risk"]["category"], "střední")
