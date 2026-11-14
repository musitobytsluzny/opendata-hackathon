"""Observed map context along an actual foot route. Never a guarantee of child safety."""

import json
import math
import threading
import time
from functools import lru_cache

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from app.services.workspace_data import (
    column,
    feature,
    provenance,
    read_connection,
    resolve,
    result,
)

_FOOT_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


@lru_cache(maxsize=64)
def foot_route(coordinates, epoch):
    """Fixed official foot profile; bounded cache and serialized public-service requests."""
    global _LAST_REQUEST
    try:
        with _FOOT_LOCK:
            time.sleep(max(0, 1 - (time.monotonic() - _LAST_REQUEST)))
            try:
                with httpx.Client(timeout=12) as client:
                    response = client.get(
                        "https://routing.openstreetmap.de/routed-foot/route/v1/foot/" + coordinates,
                        params={
                            "overview": "full",
                            "geometries": "geojson",
                            "steps": "false",
                            "radiuses": "150;150",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
            finally:
                _LAST_REQUEST = time.monotonic()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise ValueError("No actual foot route")
        route = payload["routes"][0]
        if (
            route["geometry"].get("type") != "LineString"
            or not 2 <= len(route["geometry"].get("coordinates", [])) <= 20000
        ):
            raise ValueError("Invalid foot geometry")
        if any(not math.isfinite(route[key]) or route[key] < 0 for key in ["distance", "duration"]):
            raise ValueError("Invalid foot distance")
        return route
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        raise HTTPException(
            503,
            "Pěší trasu se nepodařilo vypočítat. Nehodnoť nebezpečí podél domnělé trasy ani ji nenahrazuj automobilovou trasou.",
        ) from None


def analyse_route_context(origin_id, destination_id, corridor_m=30):
    sources = provenance(["vuv_zaplavova_uzemi", "zabaged_vodni_toky", "osm_route_features"])
    loaded = {row["table_name"]: row["row_count"] > 0 for row in sources}
    with read_connection() as connection:
        start, end = resolve(connection, origin_id), resolve(connection, destination_id)
        separation = connection.scalar(
            text(
                "SELECT ST_Distance(ST_SetSRID(ST_GeomFromGeoJSON(:a),4326)::geography,ST_SetSRID(ST_GeomFromGeoJSON(:b),4326)::geography)"
            ),
            {"a": start["point"], "b": end["point"]},
        )
    if separation > 50000:
        raise HTTPException(
            422, "Pro kontrolu místní pěší cesty vyber cíle vzdálené nejvýše 50 km vzdušně."
        )
    coords = ";".join(
        ",".join(str(round(value, 7)) for value in json.loads(place["point"])["coordinates"])
        for place in [start, end]
    )
    route = foot_route(coords, int(time.time() // 900))
    geometry = json.dumps(route["geometry"])
    parameters = {"route": geometry, "buffer": corridor_m}
    rows = []
    features = [
        feature(start, point=True),
        feature(end, point=True),
        {
            "type": "Feature",
            "id": f"foot-route:{origin_id}:{destination_id}",
            "properties": {
                "label": f"Pěšky {round(route['distance'])} m · {route['duration'] / 60:.1f} min",
                "measurement": True,
            },
            "geometry": route["geometry"],
        },
    ]
    checks = [
        ("flood", "vuv_zaplavova_uzemi", "aktivni_zona IS TRUE", "Aktivní záplavové zóny"),
        (
            "flood-q100",
            "vuv_zaplavova_uzemi",
            "q_stupen='Q100' AND aktivni_zona IS NOT TRUE",
            "Vymezené území Q100",
        ),
        ("water", "zabaged_vodni_toky", "TRUE", "Mapované vodní toky"),
        (
            "crossing",
            "osm_route_features",
            "kind='crossing'",
            "Mapované přechody/křížení pro chodce",
        ),
        (
            "signals",
            "osm_route_features",
            "kind='traffic_signals' OR tags_json->>'crossing'='traffic_signals'",
            "Mapované dopravní signalizace",
        ),
        (
            "major-roads",
            "osm_route_features",
            "kind='road_segment' AND highway IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link')",
            "Komunikace vyšších tříd v okolí trasy",
        ),
        (
            "sidewalk-no",
            "osm_route_features",
            "kind='road_segment' AND tags_json->>'sidewalk' IN ('no','none')",
            "Úseky se značkou sidewalk=no/none",
        ),
        (
            "sidewalk-unknown",
            "osm_route_features",
            "kind='road_segment' AND highway NOT IN ('footway','path','steps','pedestrian') AND NOT tags_json ? 'sidewalk'",
            "Úseky bez údaje o chodníku",
        ),
        (
            "lighting-no",
            "osm_route_features",
            "kind='road_segment' AND tags_json->>'lit'='no'",
            "Úseky se značkou lit=no",
        ),
    ]
    with read_connection() as connection:
        for key, table, where, title in checks:
            if not loaded.get(table):
                rows.append({"check": title, "mapped_count": None, "status": "vrstva není načtená"})
                continue
            count = connection.scalar(
                text(
                    f"SELECT count(*) FROM {table} WHERE ({where}) AND ST_DWithin(geom::geography,ST_SetSRID(ST_GeomFromGeoJSON(:route),4326)::geography,:buffer)"
                ),
                parameters,
            )
            rows.append(
                {
                    "check": title,
                    "mapped_count": count,
                    "status": f"v koridoru {corridor_m} m"
                    if count
                    else "bez nálezu v načtené vrstvě",
                }
            )
            if count and len(features) < 150:
                candidates = (
                    connection.execute(
                        text(
                            f"SELECT id,ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.00001)) AS geometry FROM {table} WHERE ({where}) AND ST_DWithin(geom::geography,ST_SetSRID(ST_GeomFromGeoJSON(:route),4326)::geography,:buffer) ORDER BY id LIMIT 15"
                        ),
                        parameters,
                    )
                    .mappings()
                    .all()
                )
                for candidate in candidates:
                    features.append(
                        {
                            "type": "Feature",
                            "id": f"route-context:{key}:{candidate['id']}",
                            "properties": {"label": title},
                            "geometry": json.loads(candidate["geometry"]),
                        }
                    )
    answer = result(
        "Mapové jevy podél pěší cesty",
        rows,
        [
            column("check", "Kontrola"),
            column("mapped_count", "Mapových prvků", True),
            column("status", "Rozsah zjištění"),
        ],
        features,
        [
            "osm_route_features",
            "vuv_zaplavova_uzemi",
            "zabaged_vodni_toky",
            start["table"],
            end["table"],
        ],
        f"Skutečná pěší trasa {round(route['distance'])} m, modelový čas {route['duration'] / 60:.1f} min. Kontrola koridoru do {corridor_m} m, nikoliv celkový posudek bezpečnosti. Body mohou být přichyceny k pěší síti do 150 m; vchody nejsou potvrzené. Vodní tok není sám o sobě označené nebezpečí; 2D blízkost neřeší mosty a mimoúrovňová křížení. Chybějící sidewalk tag není důkaz chybějícího chodníku. Počet mapových prvků není počet nebezpečí. Neověřeno: aktuální provoz a rychlosti, funkčnost signalizace a osvětlení, stav povrchu, rozhled, počasí, kriminalita a bezpečnost pro konkrétní dítě.",
    )
    answer["result"]["view"] = "map"
    answer["result"]["sources"].append(
        {"name": "FOSSGIS · OSRM foot / OpenStreetMap", "url": "https://routing.openstreetmap.de/"}
    )
    answer["route"] = {
        "mode": "foot",
        "distance_m": route["distance"],
        "duration_min": route["duration"] / 60,
        "corridor_m": corridor_m,
        "start_id": origin_id,
        "destination_id": destination_id,
    }
    findings = "\n".join(
        f"- **{row['check']}:** "
        + (
            "neověřeno — vrstva není načtená"
            if row["mapped_count"] is None
            else f"{row['mapped_count']} mapových prvků; {row['status']}"
        )
        for row in rows
    )
    answer["prepared_text"] = (
        f"**Pěší cesta: {start['name']} → {end['name']}**\n\n"
        f"Vypočtená trasa měří **{round(route['distance'])} m**, modelový čas je **{route['duration'] / 60:.1f} min**. Trasu a nálezy zobrazuji na mapě.\n\n"
        f"Kontrola koridoru do **{corridor_m} m** od trasy:\n\n{findings}\n\n"
        "Počet prvků není počet nebezpečí ani potvrzení, že je dítě musí překonat. Tok nemusí představovat překážku; průnik v mapě neověřuje most ani výškové oddělení.\n\n"
        "**Co údaje neříkají:** Chybějící údaj o chodníku neznamená chybějící chodník. `sidewalk=no` znamená mapovaný údaj o absenci chodníku, nikoli zákaz či nemožnost chůze; samostatná pěší cesta může být vedle silnice. Nulový nález přechodu, osvětlení nebo záplav nepotvrzuje jejich nepřítomnost v terénu ani bezpečnost cesty.\n\n"
        "**Neověřeno:** aktuální provoz a rychlosti, rozhled, stav povrchu, funkčnost signalizace a osvětlení, počasí, kriminalita a vhodnost pro konkrétní dítě. Koncové body jsou přichycené k pěší síti do 150 m; skutečné vstupy do budov nejsou potvrzené."
    )
    answer["interpretation"] = (
        "Pouze pozorované jevy v mapových datech. Nula nálezů neznamená bezpečnou cestu."
    )
    return answer
