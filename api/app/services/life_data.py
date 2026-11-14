"""Measured neighbours, local services and alternatives from attributable spatial data."""

import json
import math
import re
import unicodedata

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from app.services.workspace_data import (
    column,
    expand_institution_abbreviations,
    feature,
    read_connection,
    resolve,
    result,
)

KINDS = {
    "school": ("school", "primary_school", "secondary_school", "college", "university"),
    "primary_school": ("primary_school",),
    "secondary_school": ("secondary_school",),
    "university": ("university",),
    "kindergarten": ("kindergarten",),
    "hospital": ("hospital",),
    "healthcare": ("hospital", "healthcare", "clinic", "doctors"),
    "pharmacy": ("pharmacy",),
    "public_transport": ("bus_stop", "railway_station", "public_transport_stop"),
    "railway_station": ("railway_station",),
    "grocery": ("supermarket", "convenience"),
}
LABELS = {
    "school": "Školy",
    "primary_school": "Základní školy",
    "secondary_school": "Střední školy",
    "university": "Vysoké školy",
    "kindergarten": "Mateřské školy",
    "hospital": "Nemocnice",
    "healthcare": "Zdravotnictví",
    "pharmacy": "Lékárny",
    "public_transport": "Veřejná doprava",
    "railway_station": "Železniční stanice",
    "grocery": "Potraviny",
}


def spatial_result(title, rows, columns, origin, features, tables, note):
    answer = result(title, rows, columns, [feature(origin, point=True)] + features, tables, note)
    answer["result"]["view"] = "map"
    return answer


def nearest_municipalities(
    origin_id, limit=3, radius_m=50000, cities_only=False, population_difference_pct=None
):
    with read_connection() as connection:
        origin = resolve(connection, origin_id)
        origin_code = connection.scalar(
            text(
                "SELECT kod_obce FROM ruian_obce WHERE ST_Covers(geom,ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)) ORDER BY kod_obce LIMIT 1"
            ),
            {"point": origin["point"]},
        )
        filters = "AND m.status_kod IN (3,4,5)" if cities_only else ""
        parameters = {
            "point": origin["point"],
            "exclude": origin_code or -1,
            "radius": radius_m,
            "limit": limit,
        }
        if population_difference_pct is not None:
            population = connection.scalar(
                text("SELECT pocet_obyvatel FROM csu_demografie_obce WHERE kod_obce=:code"),
                {"code": origin_code},
            )
            if population is None:
                raise HTTPException(
                    422, "Pro podobnost podle počtu obyvatel chybí demografie výchozí obce."
                )
            filters += " AND c.pocet_obyvatel BETWEEN :lower AND :upper"
            parameters.update(
                lower=population * (1 - population_difference_pct / 100),
                upper=population * (1 + population_difference_pct / 100),
            )
        data = (
            connection.execute(
                text(f"""
            WITH origin AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography AS g)
            SELECT o.kod_obce,o.nazev,m.status_name,c.pocet_obyvatel,
                   ST_AsGeoJSON(ST_PointOnSurface(o.geom)) AS point,
                   ST_Distance(ST_PointOnSurface(o.geom)::geography,p.g) AS distance_m
            FROM ruian_obce o CROSS JOIN origin p
            LEFT JOIN municipality_status m USING(kod_obce)
            LEFT JOIN csu_demografie_obce c USING(kod_obce)
            WHERE o.kod_obce <> :exclude AND ST_DWithin(ST_PointOnSurface(o.geom)::geography,p.g,:radius)
            {filters} ORDER BY distance_m,o.kod_obce LIMIT :limit
        """),
                parameters,
            )
            .mappings()
            .all()
        )
    rows = [
        {
            "id": f"obec:{r['kod_obce']}",
            "name": r["nazev"],
            "status": r["status_name"],
            "population": r["pocet_obyvatel"],
            "distance_m": round(r["distance_m"], 1),
        }
        for r in data
    ]
    features = [
        feature(dict(id=row["id"], name=row["name"], point=raw["point"]), point=True)
        for row, raw in zip(rows, data, strict=True)
    ]
    return spatial_result(
        "Nejbližší města" if cities_only else "Nejbližší obce",
        rows,
        [
            column("name", "Místo"),
            column("status", "Status RÚIAN"),
            column("population", "Obyvatelé", True),
            column("distance_m", "Vzdušná vzdálenost", True, "m"),
        ],
        origin,
        features,
        ["ruian_obce", "municipality_status", "csu_demografie_obce"],
        f"Skutečná geodetická vzdálenost mezi vnitřními body správních území, nikoliv trasa po silnici. Pouze načtené obce Plzeňského kraje do {radius_m} m; města mají oficiální status RÚIAN 3/4/5. "
        + (
            f"Podobnost znamená počet obyvatel v rozmezí ±{population_difference_pct} % od výchozí obce. "
            if population_difference_pct is not None
            else ""
        ),
    )


def same_institution_campus(first, second):
    """Conservative cross-source campus deduplication, never merging generic facility labels."""

    def words(value):
        expanded = expand_institution_abbreviations(str(value).split(",", 1)[0]).casefold()
        folded = "".join(
            c for c in unicodedata.normalize("NFKD", expanded) if not unicodedata.combining(c)
        )
        return [word for word in re.findall(r"[^\W_]+", folded) if word not in {"a", "v", "ve"}]

    one, two = words(first["name"]), words(second["name"])
    short, long = sorted((one, two), key=len)
    generic = {
        "stredni",
        "zakladni",
        "vyssi",
        "odborna",
        "materska",
        "skola",
        "zeleznicni",
        "stanice",
        "zastavka",
        "zarizeni",
        "bez",
        "uvedeneho",
        "nazvu",
    }
    if len(short) < 3 or not set(short) - generic or long[: len(short)] != short:
        return False
    a, b = (json.loads(row["point"])["coordinates"] for row in (first, second))
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    hav = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    )
    # Used only for entity matching tolerance. Reported distances are still PostGIS WGS84 measurements.
    return 2 * 6371008.8 * math.asin(min(1, math.sqrt(hav))) <= 250


def nearby_facilities(origin_id, kind, radius_m=10000, limit=5, exclude_id=None):
    if kind not in KINDS:
        raise HTTPException(422, "Neznámý druh služby.")
    with read_connection() as connection:
        origin = resolve(connection, origin_id)
        data = (
            connection.execute(
                text("""
            WITH origin AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography AS g),
            matches AS (
                SELECT p.place_id AS id,p.name,p.amenity,p.publisher,p.source_url,ST_AsGeoJSON(p.geom) AS point,
                       ST_Distance(p.geom::geography,o.g) AS distance_m,
                       CASE WHEN p.amenity='public_transport_stop' THEN p.name ELSE p.place_id END AS group_key
                FROM all_facility_poi p CROSS JOIN origin o
                WHERE p.amenity = ANY(:amenities) AND p.place_id <> :exclude
                  AND p.place_id <> :origin AND ST_DWithin(p.geom::geography,o.g,:radius)
                  AND NOT (lower(unaccent(p.name))=lower(unaccent(:origin_name)) AND ST_DWithin(p.geom::geography,o.g,100))
                  AND NOT (p.amenity='public_transport_stop' AND p.name=COALESCE(
                      (SELECT name FROM all_facility_poi WHERE place_id=:origin AND amenity='public_transport_stop'),''))
            ), distinct_places AS (
                SELECT DISTINCT ON (group_key) * FROM matches ORDER BY group_key,distance_m,id
            )
            SELECT * FROM distinct_places ORDER BY distance_m,id
        """),
                {
                    "point": origin["point"],
                    "origin_name": origin["name"],
                    "amenities": list(KINDS[kind]),
                    "exclude": exclude_id or "",
                    "origin": origin_id,
                    "radius": radius_m,
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    distinct = []
    for row in data:
        if same_institution_campus(row, origin):
            continue
        if any(same_institution_campus(row, previous) for previous in distinct):
            continue
        distinct.append(row)
        if len(distinct) >= limit:
            break
    data = distinct
    rows = [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["amenity"],
            "distance_m": round(r["distance_m"], 1),
            "publisher": r["publisher"],
        }
        for r in data
    ]
    answer = spatial_result(
        LABELS[kind] + " · " + origin["name"],
        rows,
        [
            column("name", "Zařízení"),
            column("type", "Typ"),
            column("distance_m", "Vzdušná vzdálenost", True, "m"),
            column("publisher", "Zdroj"),
        ],
        origin,
        [feature(r, point=True) for r in data],
        ["facility_poi", "osm_poi", origin["table"]],
        f"Pouze načtená zařízení do {radius_m} m, vzdušně od bodu místa. Nemocnice nejsou nahrazené ordinacemi. Zastávky neznamenají potvrzený odjezd ani frekvenci spojů; MHD PMDP pokrývá Plzeň, ne celý kraj. Prázdný výsledek nedokazuje, že služba neexistuje; ordinační hodiny, kapacity ani aktuální provoz nejsou ověřené.",
    )
    return answer


def accessibility_summary(origin_id, radius_m=20000):
    with read_connection() as connection:
        origin = resolve(connection, origin_id)
    rows, features = [], {}
    for kind in ("school", "kindergarten", "hospital", "pharmacy", "public_transport", "grocery"):
        part = nearby_facilities(origin_id, kind, radius_m, 1)["result"]
        row = part["rows"][0] if part["rows"] else None
        rows.append(
            {
                "place": origin["name"],
                "service": LABELS[kind],
                "name": row["name"] if row else None,
                "distance_m": row["distance_m"] if row else None,
                "publisher": row["publisher"] if row else None,
            }
        )
        for f in part["features"]:
            features[f["id"]] = f
    answer = result(
        "Dostupnost každodenních služeb",
        rows,
        [
            column("place", "Výchozí místo"),
            column("service", "Služba"),
            column("name", "Nejbližší načtené zařízení"),
            column("distance_m", "Vzdušně", True, "m"),
            column("publisher", "Zdroj"),
        ],
        list(features.values()),
        ["facility_poi", "osm_poi"],
        f"Nejbližší načtené zařízení pro každou službu do {radius_m} m. Prázdné pole znamená chybějící nález v datech, nikoliv neexistující službu. Jde o měření polohy, nikoliv pěší dochozí čas, aktuální odjezdy či kvalitu života.",
    )
    answer["result"]["view"] = "map"
    return answer


def facility_alternatives(place_id, radius_m=20000, limit=5, kind=None):
    with read_connection() as connection:
        resolve(connection, place_id)
        amenity = connection.scalar(
            text("SELECT amenity FROM all_facility_poi WHERE place_id=:id"), {"id": place_id}
        )
    if kind is None:
        kind = (
            "school"
            if amenity in KINDS["school"]
            else next((key for key, types in KINDS.items() if types == (amenity,)), None)
        )
    if kind is None:
        kind = next((kind for kind, types in KINDS.items() if amenity in types), None)
    if kind is None:
        raise HTTPException(422, "Zařízení nemá podporovaný přesný typ pro hledání alternativ.")
    return nearby_facilities(place_id, kind, radius_m, limit, exclude_id=place_id)


def rank_driving_candidates(origin_id, candidate_ids, order_by="distance"):
    if order_by not in {"distance", "duration"}:
        raise HTTPException(422, "Řazení musí být distance nebo duration.")
    if (
        not 1 <= len(candidate_ids) <= 8
        or len(set(candidate_ids)) != len(candidate_ids)
        or origin_id in candidate_ids
    ):
        raise HTTPException(422, "Vyberte 1 až 8 různých kandidátů odlišných od výchozího místa.")
    with read_connection() as connection:
        places = [resolve(connection, place_id) for place_id in [origin_id] + candidate_ids]
    coords = ";".join(
        ",".join(str(round(v, 7)) for v in json.loads(p["point"])["coordinates"]) for p in places
    )
    try:
        with httpx.Client(timeout=12) as client:
            response = client.get(
                "https://router.project-osrm.org/table/v1/driving/" + coords,
                params={
                    "sources": "0",
                    "destinations": ";".join(map(str, range(1, len(places)))),
                    "annotations": "distance,duration",
                    "radiuses": ";".join(["1000"] * len(places)),
                },
            )
            response.raise_for_status()
            data = response.json()
        if (
            data.get("code") != "Ok"
            or len(data["distances"][0]) != len(candidate_ids)
            or len(data["durations"][0]) != len(candidate_ids)
        ):
            raise ValueError("Incomplete routing matrix")
        rows = [
            {
                "id": p["id"],
                "from_id": origin_id,
                "from": places[0]["name"],
                "name": p["name"],
                "distance_km": round(distance / 1000, 2) if distance is not None else None,
                "duration_min": round(duration / 60, 1) if duration is not None else None,
            }
            for p, distance, duration in zip(
                places[1:], data["distances"][0], data["durations"][0], strict=True
            )
        ]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(
            503, "Silniční porovnání není dostupné; délky ani časy neodhadujte."
        ) from None
    sort_key = "distance_km" if order_by == "distance" else "duration_min"
    rows.sort(
        key=lambda row: (row[sort_key] is None, row[sort_key] if row[sort_key] is not None else 0)
    )
    answer = spatial_result(
        "Porovnání dojezdu autem",
        rows,
        [
            column("from", "Výchozí místo"),
            column("name", "Kandidát"),
            column("distance_km", "Délka nejrychlejší trasy", True, "km"),
            column("duration_min", "Modelový čas", True, "min"),
        ],
        places[0],
        [feature(p, point=True) for p in places[1:]],
        list({place["table"] for place in places}),
        (
            "Řazeno podle délky silniční trasy (km). "
            if order_by == "distance"
            else "Řazeno podle modelového času jízdy (min). "
        )
        + "Kratší trasa nemusí mít kratší čas. OSRM / OpenStreetMap. Pouze zadaní kandidáti, nikoliv automaticky nejbližší místa z celé databáze. Modelový čas autem bez živé dopravy; nedostupná trasa zůstává prázdná.",
    )

    answer["ordering"] = order_by
    answer["result"]["sources"].append(
        {"name": "OSRM / OpenStreetMap", "url": "https://project-osrm.org/"}
    )
    return answer
