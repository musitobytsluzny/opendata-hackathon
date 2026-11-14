"""Small spatial operations. IDs resolve to stored geometry; model-written SQL is forbidden."""

import json

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from app.services.geo_data import METRICS, catalog, read_connection

PLACE_TABLES = {
    "obec": ("ruian_obce", "kod_obce", "nazev"),
    "ku": ("ruian_ku", "kod_ku", "nazev"),
    "poi": ("osm_poi", "id", "name"),
    "parcela": ("ruian_parcely", "id", "cislo_parcely"),
}
CATEGORIES = {"healthcare", "education", "transport", "shopping"}


def provenance(tables):
    return [item for item in catalog()["datasets"] if item["table_name"] in tables]


def result(title, rows, columns, features=None, tables=(), note=""):
    sources = provenance(tables)
    return {
        "result": {
            "title": title,
            "rows": rows,
            "columns": columns,
            "features": features or [],
            "sources": sources,
            "note": note,
            "sample": any(s["data_kind"] == "demo" for s in sources),
        }
    }


def column(key, label, numeric=False, unit=""):
    return {"key": key, "label": label, "numeric": numeric, "unit": unit}


def resolve(connection, place_id):
    kind, separator, key = place_id.partition(":")
    if not separator or kind not in PLACE_TABLES or not key or len(key) > 60:
        raise HTTPException(422, "Neplatný identifikátor místa; použijte výsledek hledání.")
    table, primary, name = PLACE_TABLES[kind]
    # The fragments come exclusively from PLACE_TABLES. The value is bound.
    row = (
        connection.execute(
            text(f"""
        SELECT CAST({primary} AS text) AS key, {name} AS name,
               ST_AsGeoJSON(ST_PointOnSurface(geom)) AS point,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.00001)) AS geometry
        FROM {table} WHERE CAST({primary} AS text)=:key LIMIT 1
    """),
            {"key": key},
        )
        .mappings()
        .first()
    )
    if row is None or row["point"] is None:
        raise HTTPException(404, "Místo není v načtených datech.")
    return dict(row, id=place_id, table=table)


def feature(row, point=False):
    return {
        "type": "Feature",
        "id": row["id"],
        "properties": {"label": row["name"]},
        "geometry": json.loads(row["point" if point else "geometry"]),
    }


def search_places(query, kind="obec", limit=10):
    if kind not in PLACE_TABLES:
        raise HTTPException(422, "Neznámý typ místa.")
    table, primary, name = PLACE_TABLES[kind]
    with read_connection() as connection:
        rows = (
            connection.execute(
                text(f"""
            SELECT CAST({primary} AS text) AS key, {name} AS name,
                   ST_AsGeoJSON(ST_PointOnSurface(geom)) AS point
            FROM {table}
            WHERE unaccent(COALESCE({name}, '')) ILIKE unaccent(:query) ESCAPE '!'
            ORDER BY (lower({name})=lower(:exact)) DESC, {name}, {primary}
            LIMIT :limit
        """),
                {
                    "query": "%"
                    + query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                    + "%",
                    "exact": query,
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    places = [dict(row, id=f"{kind}:{row['key']}") for row in rows if row["point"]]
    return result(
        "Nalezená místa",
        [{"id": p["id"], "name": p["name"]} for p in places],
        [column("name", "Místo"), column("id", "Identifikátor")],
        [feature(p, point=True) for p in places],
        [table],
        "Bod obce či katastru je vnitřní bod území, nikoliv adresa nebo vstup do budovy.",
    )


def place_geometry(place_id):
    with read_connection() as connection:
        row = resolve(connection, place_id)
    return result(
        row["name"],
        [{"id": place_id, "name": row["name"]}],
        [column("name", "Místo")],
        [feature(row)],
        [row["table"]],
    )


def municipality_statistics(metric, district=None, limit=20, descending=True):
    if metric not in METRICS and metric != "area_m2":
        raise HTTPException(422, "Neznámá metrika.")
    table, _, title, _, unit = (
        METRICS[metric] if metric != "area_m2" else ("ruian_obce", "", "Rozloha obce", "", "m²")
    )
    source = (
        f"{table} s JOIN ruian_obce o USING(kod_obce)" if metric != "area_m2" else "ruian_obce o"
    )
    expressions = {
        "area_m2": "ST_Area(o.geom::geography)",
        "population": "s.pocet_obyvatel",
        "seniors_pct": "100.0*s.seniori_65_plus/NULLIF(s.pocet_obyvatel,0)",
        "children_pct": "100.0*s.deti_0_14/NULLIF(s.pocet_obyvatel,0)",
        "greenery_pct": "s.podil_zelene_pct",
        "ndvi": "s.avg_ndvi",
    }
    expression = expressions[metric]
    order = "DESC" if descending else "ASC"
    with read_connection() as connection:
        data = (
            connection.execute(
                text(f"""
            SELECT o.kod_obce, o.nazev, d.nazev AS district, {expression} AS value,
                   ST_AsGeoJSON(ST_PointOnSurface(o.geom)) AS point
            FROM {source}
            JOIN okresy d USING(kod_okresu)
            WHERE (CAST(:district AS text) IS NULL OR unaccent(d.nazev)=unaccent(:district))
              AND {expression} IS NOT NULL
            ORDER BY value {order}, o.kod_obce LIMIT :limit
        """),
                {"district": district, "limit": limit},
            )
            .mappings()
            .all()
        )
    rows = [
        {
            "id": f"obec:{r['kod_obce']}",
            "name": r["nazev"],
            "district": r["district"],
            "value": float(r["value"]),
        }
        for r in data
    ]
    features = [
        feature(dict(id=r["id"], name=r["name"], point=d["point"]), point=True)
        for r, d in zip(rows, data, strict=True)
    ]
    return result(
        title,
        rows,
        [
            column("name", "Obec"),
            column("district", "Okres"),
            dict(column("value", title, True, unit), additive=metric in {"population", "area_m2"}),
        ],
        features,
        [table, "ruian_obce"],
        f"Výběr nejvýše {limit} obcí s dostupnou hodnotou; nejde o součet celého kraje.",
    )


def nearby_places(origin_id, category=None, radius_m=5000, limit=10):
    if category is not None and category not in CATEGORIES:
        raise HTTPException(422, "Neznámá kategorie POI.")
    with read_connection() as connection:
        origin = resolve(connection, origin_id)
        data = (
            connection.execute(
                text("""
            WITH origin AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography AS g)
            SELECT p.id,p.name,p.category,ST_AsGeoJSON(p.geom) AS point,
                   ST_Distance(p.geom::geography,o.g) AS distance_m
            FROM osm_poi p CROSS JOIN origin o
            WHERE (CAST(:category AS text) IS NULL OR p.category=:category)
              AND ST_DWithin(p.geom::geography,o.g,:radius)
              AND ('poi:' || p.id) <> :origin
            ORDER BY distance_m,p.id LIMIT :limit
        """),
                {
                    "point": origin["point"],
                    "category": category,
                    "radius": radius_m,
                    "origin": origin_id,
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    rows = [
        {
            "id": "poi:" + r["id"],
            "name": r["name"],
            "category": r["category"],
            "distance_m": round(r["distance_m"], 1),
        }
        for r in data
    ]
    features = [feature(origin, point=True)] + [
        feature(dict(r, id="poi:" + r["id"]), point=True) for r in data
    ]
    return result(
        "Místa v okolí: " + origin["name"],
        rows,
        [
            column("name", "Místo"),
            column("category", "Kategorie"),
            column("distance_m", "Vzdušná vzdálenost", True, "m"),
        ],
        features,
        [origin["table"], "osm_poi"],
        "Geodetická vzdálenost po elipsoidu WGS84 od bodu místa, nikoli délka cesty. Jen načtené POI.",
    )


def measure_distance(from_id, to_id):
    with read_connection() as connection:
        start, end = resolve(connection, from_id), resolve(connection, to_id)
        distance = connection.scalar(
            text("""
            SELECT ST_Distance(ST_SetSRID(ST_GeomFromGeoJSON(:a),4326)::geography,
                               ST_SetSRID(ST_GeomFromGeoJSON(:b),4326)::geography)
        """),
            {"a": start["point"], "b": end["point"]},
        )
    features = [feature(start, point=True), feature(end, point=True)]
    features.append(
        {
            "type": "Feature",
            "id": "measurement",
            "properties": {"label": f"{distance / 1000:.2f} km vzdušně", "measurement": True},
            "geometry": {
                "type": "LineString",
                "coordinates": [json.loads(p["point"])["coordinates"] for p in (start, end)],
            },
        }
    )
    return result(
        "Vzdušná vzdálenost",
        [{"from": start["name"], "to": end["name"], "distance_m": round(distance, 1)}],
        [
            column("from", "Odkud"),
            column("to", "Kam"),
            column("distance_m", "Vzdálenost", True, "m"),
        ],
        features,
        [start["table"], end["table"]],
        "Výpočet PostGIS po elipsoidu WGS84 mezi body míst. U území jde o vnitřní bod, nikoliv vstup nebo hranici.",
    )


def find_route(from_id, to_id):
    with read_connection() as connection:
        start, end = resolve(connection, from_id), resolve(connection, to_id)
    points = [json.loads(p["point"])["coordinates"] for p in (start, end)]
    coordinates = ";".join(",".join(str(round(v, 7)) for v in point) for point in points)
    # Fixed service and driving profile: no model-supplied URLs or invented walking times.
    try:
        with httpx.Client(timeout=12) as client:
            response = client.get(
                "https://router.project-osrm.org/route/v1/driving/" + coordinates,
                params={
                    "overview": "simplified",
                    "geometries": "geojson",
                    "steps": "false",
                    "radiuses": "1000;1000",
                },
            )
            response.raise_for_status()
            data = response.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError("No route")
        route = data["routes"][0]
        geometry = route["geometry"]
        if geometry.get("type") != "LineString" or len(geometry.get("coordinates", [])) > 10000:
            raise ValueError("Invalid route geometry")
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        raise HTTPException(
            503, "Silniční trasu se nepodařilo vypočítat. Délku ani čas neodhadujte."
        ) from None
    features = [
        feature(start, point=True),
        feature(end, point=True),
        {
            "type": "Feature",
            "id": "route",
            "properties": {
                "label": f"{route['distance'] / 1000:.2f} km · {route['duration'] / 60:.0f} min autem",
                "measurement": True,
            },
            "geometry": geometry,
        },
    ]
    answer = result(
        "Trasa autem",
        [
            {
                "from": start["name"],
                "to": end["name"],
                "distance_km": round(route["distance"] / 1000, 2),
                "duration_min": round(route["duration"] / 60, 1),
            }
        ],
        [
            column("from", "Odkud"),
            column("to", "Kam"),
            column("distance_km", "Délka trasy", True, "km"),
            column("duration_min", "Modelový čas jízdy", True, "min"),
        ],
        features,
        [start["table"], end["table"]],
        "OSRM / OpenStreetMap, automobilový profil. Modelový čas bez živé dopravy; nejde o pěší trasu. Koncové body mohou být přichyceny k silnici do 1 km.",
    )
    answer["result"]["sources"].append(
        {"name": "OSRM / OpenStreetMap", "url": "https://project-osrm.org/"}
    )
    return answer


MAP_LAYERS = {
    "flood": ("vuv_zaplavova_uzemi", "COALESCE(tok_nazev,'Záplavové území')", "Záplavová území"),
    "protected": ("aopk_chranena_uzemi", "nazev", "Chráněná území"),
    "roads": ("zabaged_silnice", "COALESCE(cislo_silnice,trida,'Silnice')", "Silnice"),
    "water": ("zabaged_vodni_toky", "COALESCE(jmeno,'Vodní tok')", "Vodní toky"),
    "parcels": ("ruian_parcely", "cislo_parcely", "Parcely"),
}


def load_map_layer(layer, around_id, radius_m=2000, limit=100):
    if layer not in MAP_LAYERS:
        raise HTTPException(422, "Neznámá mapová vrstva.")
    table, label, title = MAP_LAYERS[layer]
    with read_connection() as connection:
        origin = resolve(connection, around_id)
        data = (
            connection.execute(
                text(f"""
            WITH region AS (SELECT ST_Buffer(ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography,:radius)::geometry AS g)
            SELECT t.id::text AS id,{label} AS name,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(t.geom,0.00002)) AS geometry
            FROM {table} t CROSS JOIN region r WHERE ST_Intersects(t.geom,r.g)
            ORDER BY t.id LIMIT :limit
        """),
                {"point": origin["point"], "radius": radius_m, "limit": limit + 1},
            )
            .mappings()
            .all()
        )
    truncated = len(data) > limit
    features = [
        {
            "type": "Feature",
            "id": f"{layer}:{row['id']}",
            "properties": {"label": row["name"]},
            "geometry": json.loads(row["geometry"]),
        }
        for row in data[:limit]
    ]
    return result(
        title + " · " + origin["name"],
        [{"name": row["name"]} for row in data[: min(limit, 50)]],
        [column("name", "Prvek")],
        features,
        [table],
        f"Průnik s okolím {radius_m} m od bodu místa. "
        + (
            f"Výsledek je omezený na {limit} prvků; zmenšete oblast pro úplný detail."
            if truncated
            else "Jen skutečně načtená data."
        ),
    )


def parcel_at_point(lat, lon):
    with read_connection() as connection:
        data = (
            connection.execute(
                text("""
            SELECT id::text AS key,cislo_parcely AS name,kod_ku,vymera_m2,druh_pozemku,
                   ST_AsGeoJSON(geom) AS geometry
            FROM ruian_parcely WHERE ST_Covers(geom,ST_SetSRID(ST_Point(:lon,:lat),4326))
            ORDER BY id LIMIT 5
        """),
                {"lat": lat, "lon": lon},
            )
            .mappings()
            .all()
        )
    external = False
    if not data:
        try:
            with httpx.Client(timeout=12) as client:
                response = client.get(
                    "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/5/query",
                    params={
                        "geometry": f"{lon},{lat}",
                        "geometryType": "esriGeometryPoint",
                        "inSR": 4326,
                        "outSR": 4326,
                        "outFields": "*",
                        "f": "geojson",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            if "error" in payload or payload.get("exceededTransferLimit"):
                raise ValueError("Incomplete parcel lookup")
            data = [
                {
                    "key": str(int(f["properties"]["id"])),
                    "name": f["properties"]["cisloparcely"],
                    "kod_ku": f["properties"]["katastralniuzemi"],
                    "vymera_m2": f["properties"]["vymeraparcely"],
                    "druh_pozemku": None,
                    "geometry": json.dumps(f["geometry"]),
                }
                for f in payload.get("features", [])[:5]
            ]
            external = True
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(
                503, "Parcela není lokálně načtená a ČÚZK právě neodpovídá."
            ) from None
    rows = [
        {
            "id": "parcela:" + row["key"],
            "name": row["name"],
            "kod_ku": row["kod_ku"],
            "area_m2": row["vymera_m2"],
            "land_type": row["druh_pozemku"],
        }
        for row in data
    ]
    features = [
        {
            "type": "Feature",
            "id": row["id"],
            "properties": {"label": "Parcela " + str(row["name"])},
            "geometry": json.loads(source["geometry"]),
        }
        for row, source in zip(rows, data, strict=True)
    ]
    answer = result(
        f"Parcela {rows[0]['name']} · KÚ {rows[0]['kod_ku']}"
        if len(rows) == 1
        else "Parcely v místě kliknutí",
        rows,
        [
            column("name", "Parcela"),
            column("kod_ku", "Kód KÚ"),
            column("area_m2", "Výměra", True, "m²"),
            column("land_type", "Druh pozemku"),
        ],
        features,
        [] if external else ["ruian_parcely"],
        "Při kliknutí na hranici může být více shod; vyberte konkrétní parcelu. Externí parcela nemusí být dostupná pro lokální analytické dotazy.",
    )
    if external:
        answer["result"]["sources"].append(
            {"name": "ČÚZK RÚIAN – aktuální dotaz", "url": "https://cuzk.gov.cz/"}
        )
    return answer
