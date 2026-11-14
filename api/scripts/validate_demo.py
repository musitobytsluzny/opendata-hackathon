"""Opt-in live demo audit. Calls configured Gemini/MCP, never writes credentials to reports."""

import argparse
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from app.database.connection import SessionLocal
from app.models import Profile, User
from app.schemas.chat import ChatRequest
from app.schemas.user import UserCreate
from app.services import chat_results, gemini_chat
from app.services.auth_service import create_access_token
from app.services.geo_data import read_connection
from app.services.user_service import create_user
from fastapi import HTTPException
from sqlalchemy import delete, text

SCENARIOS = [
    ("school-find", "school", "Najdi školu VOŠ a SPŠE Plzeň.", "school"),
    ("school-map", "school", "Ukaž ji na mapě.", "map"),
    (
        "school-neighbours",
        "school",
        "Top 3 nejbližší školy k této škole, původní školu vynech.",
        "nearby",
    ),
    (
        "01-population",
        "demo",
        "Kterých pět obcí Plzeňského kraje má nejvíc obyvatel? Vyber vhodný graf.",
        "chart5",
    ),
    ("02-area", "demo", "A teď podle rozlohy v m². Ukaž koláčový graf.", "pie5"),
    ("03-cities", "demo", "Najdi tři nejbližší města k Žihli a ukaž je na mapě.", "cities3"),
    (
        "04-driving",
        "demo",
        "Seřaď tato města podle skutečné vzdálenosti autem ze Žihle. Přidej modelový čas jízdy.",
        "driving",
    ),
    (
        "05-alternatives",
        "demo",
        "Najdi v okolí Žihle alternativní obce s podobným počtem obyvatel, v rozmezí ±30 %.",
        "alternatives",
    ),
    (
        "06-address",
        "demo",
        "Najdi parcelu na adrese Žihle 294, 331 65. Přibliž ji a ukaž její hranici.",
        "parcel",
    ),
    (
        "07-life",
        "demo",
        "Jaké každodenní služby jsou kolem této parcely? Ukaž nejbližší školu, školku, nemocnici a veřejnou dopravu. Chybějící údaje označ.",
        "life",
    ),
    (
        "08-schools-driving",
        "demo",
        "Najdi tři nejbližší základní školy. Porovnej jejich dojezd autem od této parcely.",
        "school-driving",
    ),
    (
        "08b-school-route-context",
        "demo",
        "Jsou cestou z parcely na adrese Žihle 294 do nejbližší základní školy ve stejné obci nějaká nebezpečí, která by mohla čekat děti? Ověř skutečnou pěší trasu a ukaž mapové nálezy i chybějící údaje.",
        "foot-context",
    ),
    (
        "09-layers",
        "demo",
        "Zobraz kolem této parcely záplavová území a chráněná území v okruhu dvou kilometrů.",
        "layers",
    ),
    (
        "10-hide",
        "demo",
        "Skryj chráněná území a nech zobrazenou parcelu a záplavové oblasti.",
        "hide",
    ),
    (
        "11-compare",
        "demo",
        "Porovnej dvě parcely, které jsem právě vybral v mapě, podle výměry, druhu pozemku a evidovaných prostorových omezení. Výměry zobraz vhodným grafem.",
        "comparison",
    ),
    (
        "12-compare-schools",
        "demo",
        "Kolem každé z těchto dvou parcel najdi nejbližší základní školu a porovnej dostupnost autem.",
        "comparison-driving",
    ),
    (
        "13-conclusion",
        "demo",
        "Shrň poslední porovnání pro rodinu s malými dětmi. Odděl naměřená fakta, možné kompromisy a údaje, které ještě potřebujeme zjistit.",
        "summary",
    ),
    (
        "balanced-parcels",
        "balanced",
        "Najdi v celé načtené databázi parcelu stejně vzdálenou vzdušně od VOŠ a SPŠE Plzeň, Koterovská 85, a SOUE elektrotechnického, Vejprnická 56. Ukaž pět nejlepších na mapě a skutečné vzdálenosti i jejich rozdíl. Tolerance rozdílu je 25 metrů.",
        "balanced",
    ),
]


def inspect_reply(reply, trace, expected):
    artifacts = reply.artifacts
    names = {call["name"] for call in trace}
    rows = [row for artifact in artifacts for row in artifact.rows]
    if expected == "balanced":
        assert any(
            c["name"] == "balanced_parcels" and c.get("search", {}).get("scope") == "loaded_parcels"
            for c in trace
        ), "No whole-database equidistance query"
        assert any(
            a.view == "map"
            and len(a.rows) == 5
            and all(
                r.get("distance_a_m") is not None
                and r.get("distance_b_m") is not None
                and r.get("within_tolerance") is True
                for r in a.rows
            )
            and len(a.features) >= 7
            for a in artifacts
        ), "Missing measured parcel polygons and both institutions"
    elif expected == "school":
        assert any(
            "elektrotechn" in str(row.get("name", "")).casefold()
            and str(row.get("id", "")).startswith("facility:")
            for row in rows
        ), "No grounded school ID"
        assert any(a.features for a in artifacts), "No actual school geometry"
    elif expected in {"map", "parcel"}:
        assert any(a.view == "map" and a.features for a in artifacts), "No visible map geometry"
        if expected == "parcel":
            assert any(
                f["geometry"]["type"] in {"Polygon", "MultiPolygon"}
                for a in artifacts
                for f in a.features
            ), "Parcel must be polygon, not guessed point"
    elif expected == "nearby":
        from app.services.life_data import nearby_facilities

        spatial = [
            call
            for call in trace
            if call["name"] in {"nearby_facilities", "nearby_places", "facility_alternatives"}
        ]
        assert spatial, "No measured neighbour query"
        arguments = spatial[-1]["arguments"]
        origin = arguments.get("origin_id") or arguments.get("place_id")
        expected_rows = nearby_facilities(origin, "school", arguments.get("radius_m", 10000), 3)[
            "result"
        ]["rows"]
        expected_ids = {row["id"] for row in expected_rows}
        assert len(expected_ids) == 3 and any(
            len(a.rows) == 3 and {row.get("id") for row in a.rows} == expected_ids
            for a in artifacts
        ), "Nearest schools must cover all levels and exclude the original campus"
    elif expected == "chart5":
        assert any(a.view in {"bar", "pie"} and len(a.rows) == 5 for a in artifacts), (
            "Missing top-five chart"
        )
    elif expected == "pie5":
        assert any(
            a.view == "pie" and len(a.rows) == 5 and any(c.unit == "m²" for c in a.columns)
            for a in artifacts
        ), "Missing area pie"
    elif expected == "cities3":
        assert any(
            len(a.rows) == 3
            and all(
                r.get("status") in {"Město", "Statutární město", "Hlavní město"} for r in a.rows
            )
            for a in artifacts
        ), "Missing official cities"
    elif expected in {"driving", "school-driving", "comparison-driving"}:
        assert names & {"rank_driving_candidates", "find_route"}, "No actual routing query"
        assert any(r.get("distance_km") is not None for r in rows), "No routed distance"
        if expected == "comparison-driving":
            origins = {
                call["arguments"].get("origin_id") or call["arguments"].get("from_id")
                for call in trace
                if call["name"] in {"rank_driving_candidates", "find_route"}
            }
            assert len(origins) >= 2, "Both selected parcels must have actual routing results"
        if expected == "school-driving":
            assert all(
                str(
                    call["arguments"].get("origin_id") or call["arguments"].get("from_id") or ""
                ).startswith("parcela:")
                for call in trace
                if call["name"] in {"rank_driving_candidates", "find_route"}
            ), "Driving must originate at the requested parcel"
            assert (
                any(
                    call["name"] == "rank_driving_candidates"
                    and len(call["arguments"].get("candidate_ids", [])) >= 3
                    for call in trace
                )
                or len([call for call in trace if call["name"] == "find_route"]) >= 3
            ), "All three schools must be routed"

    elif expected == "alternatives":
        assert "alternative_municipalities" in names, "No demographic alternatives query"
        assert rows, "No actual alternatives"
    elif expected == "life":
        assert names & {"accessibility_summary", "nearby_facilities"}, "No facilities query"
        assert rows, "No returned facility/missing-data rows"
        assert all(
            str(call["arguments"].get("origin_id", "")).startswith("parcela:")
            for call in trace
            if call["name"] in {"accessibility_summary", "nearby_facilities"}
        ), "Services must be located around the requested parcel"
    elif expected == "layers":
        requested = {
            call["arguments"].get("layer") for call in trace if call["name"] == "load_map_layer"
        }
        assert {"flood", "protected"} <= requested, "Both requested layers were not queried"
        assert any(a.view == "map" and a.features for a in artifacts), "No actual layer geometry"
    elif expected == "hide":
        assert any(not action.visible for action in reply.layer_actions), (
            "No explicit layer hide action"
        )
    elif expected == "comparison":
        assert "prevalidate_parcel" in names, "No parcel checks"
        assert any(a.view in {"bar", "pie"} and len(a.rows) >= 2 for a in artifacts), (
            "Missing comparative chart"
        )
    elif expected == "foot-context":
        assert "route_context" in names, "No actual walking route corridor check"
        assert any(a.view == "map" and a.features for a in artifacts), "No walking route on map"
        assert any("mapped_count" in r for r in rows), "Missing mapped findings and unknowns"
        assert any("chodníku" in a.note and "Neověřeno" in a.note for a in artifacts), (
            "Missing coverage limits"
        )
    elif expected == "summary":
        assert any(
            a.title == "Ověřené porovnání parcel"
            and len(a.rows) >= 2
            and all(r.get("assessment_kind") == "indicative" for r in a.rows)
            for a in artifacts
        ), "Decision summary must preserve verified parcel assessments"
        assert "Výměra ale není volná plocha" in reply.text, (
            "Missing grounded free-space distinction"
        )
        assert len(reply.text) > 120, "No useful grounded summary"


async def inject_clicks(token, history, refs, user_id):
    """Use real ČÚZK polygons and the same endpoint as mouse clicks; no fake parcel IDs."""
    from app.services.geo_data import prevalidate_parcel

    reference = prevalidate_parcel(cislo="438", kod_ku=796891)
    assert reference.get("parcel"), "Demo address parcel missing"
    with read_connection() as connection:
        bounds = connection.execute(
            text(
                "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) FROM (SELECT ST_Envelope(ST_Buffer(ST_PointOnSurface(geom)::geography,200)::geometry) g FROM ruian_parcely WHERE id=:id) q"
            ),
            {"id": str(reference["parcel"]["id"])},
        ).one()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/5/query",
            params={
                "where": "katastralniuzemi=796891 AND druhpozemkukod=13 AND vymeraparcely BETWEEN 50 AND 3000",
                "geometry": ",".join(map(str, bounds)),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "resultRecordCount": 10,
                "outFields": "id,cisloparcely,katastralniuzemi",
                "outSR": 4326,
                "f": "geojson",
            },
        )
        response.raise_for_status()
        features = response.json()["features"]
        assert len(features) >= 2, "Need two actual parcels for comparison"
        for feature in features[:2]:
            with read_connection() as connection:
                point = (
                    connection.execute(
                        text(
                            "SELECT ST_X(p) AS lon,ST_Y(p) AS lat FROM (SELECT ST_PointOnSurface(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) AS p) q"
                        ),
                        {"geometry": json.dumps(feature["geometry"])},
                    )
                    .mappings()
                    .one()
                )
            response = await client.get(
                "http://localhost:8000/data/parcels/at-point",
                params={"lat": point["lat"], "lon": point["lon"]},
                headers={"Authorization": "Bearer " + token},
            )
            response.raise_for_status()
            artifact = chat_results.remember(response.json()["result"], user_id)
            refs.append(artifact.result_id)
            history.append(
                {
                    "role": "assistant",
                    "text": "Parcela vybraná kliknutím: "
                    + json.dumps(artifact.rows, ensure_ascii=False),
                }
            )


async def run(output, selected):
    with SessionLocal() as db:
        user = create_user(
            db,
            UserCreate(
                username="demo-audit-" + uuid.uuid4().hex[:10],
                password=uuid.uuid4().hex,
                profile={"firstname": "Demo", "lastname": "Audit"},
            ),
        )
        user_id = user.id
        token = create_access_token(user.id, user.username)
    report = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "model": gemini_chat.settings.gemini_model,
        "live": True,
        "cases": [],
    }
    histories, references = {}, {}
    original = gemini_chat.open_mcp_session
    trace = []

    @asynccontextmanager
    async def audited_session(token):
        async with original(token) as session:

            class Audited:
                async def list_tools(self):
                    return await session.list_tools()

                async def call_tool(self, name, arguments):
                    entry = {"name": name, "arguments": arguments}
                    trace.append(entry)
                    result = await session.call_tool(name, arguments)
                    payload = gemini_chat.decode_tool_result(result)
                    if name in {"balanced_parcels", "balanced_parcels_nearby"} and payload.get(
                        "search"
                    ):
                        entry["search"] = payload["search"]
                    if payload.get("error"):
                        entry["error"] = payload["error"]
                    return result

            yield Audited()

    gemini_chat.open_mcp_session = audited_session
    try:
        for key, conversation, question, expected in SCENARIOS:
            if selected and key not in selected:
                continue
            history = histories.setdefault(conversation, [])
            refs = references.setdefault(conversation, [])
            trace.clear()
            entry = {"id": key, "question": question, "expected": expected}
            started = time.monotonic()
            try:
                if expected == "comparison":
                    await inject_clicks(token, history, refs, user_id)
                    entry["selection_method"] = (
                        "Two actual building parcels within 200 m of Žihle 294 → PostGIS interior points → authenticated map-click endpoint; browser gestures covered separately by Playwright."
                    )
                reply = await gemini_chat.answer(
                    ChatRequest(
                        question=question,
                        history=history[-10:],
                        result_ids=list(dict.fromkeys(refs))[-8:],
                    ),
                    user_id,
                    token,
                )
                entry.update(
                    text=reply.text,
                    artifacts=[
                        a.model_dump(exclude={"features"}) | {"geometry_count": len(a.features)}
                        for a in reply.artifacts
                    ],
                    layer_actions=[a.model_dump() for a in reply.layer_actions],
                )
                history.extend(
                    [
                        {"role": "user", "text": question},
                        {"role": "assistant", "text": reply.text[:2000]},
                    ]
                )
                refs.extend(reply.result_ids)
                refs.extend(a.result_id for a in reply.artifacts)
                inspect_reply(reply, trace, expected)
                entry["status"] = "passed"
            except Exception as error:
                entry["status"] = (
                    "blocked"
                    if isinstance(error, HTTPException) and error.status_code in {429, 503, 504}
                    else "failed"
                )
                entry["error"] = (
                    error.detail if isinstance(error, HTTPException) else str(error)[:1000]
                )
            entry.update(seconds=round(time.monotonic() - started, 2), tool_calls=trace.copy())
            report["cases"].append(entry)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(key, entry["status"], entry.get("error", ""), flush=True)
            await asyncio.sleep(3)
    finally:
        gemini_chat.open_mcp_session = original
        with SessionLocal.begin() as db:
            db.execute(delete(Profile).where(Profile.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/app/demo-validation.json"))
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    report = asyncio.run(run(args.output, set(args.only)))
    if any(case["status"] != "passed" for case in report["cases"]):
        raise SystemExit(1)
