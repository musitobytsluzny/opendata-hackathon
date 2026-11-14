"""Measured parcel candidates near the midpoint of two verified places."""

import json

from fastapi import HTTPException
from sqlalchemy import text

from app.services.workspace_data import column, feature, read_connection, resolve, result


def balanced_parcels(first_id, second_id, radius_m=5000, tolerance_m=25, limit=5, search_all=False):
    if first_id == second_id:
        raise HTTPException(
            422,
            "Obě místa jsou totožná: každá parcela je od nich stejně vzdálená. Přidejte další výběrové kritérium nebo zadejte dva odlišné cíle.",
        )
    if not 100 <= radius_m <= 20000 or not 0 <= tolerance_m <= 1000 or not 1 <= limit <= 10:
        raise HTTPException(422, "Radius 100–20000 m, tolerance 0–1000 m a počet 1–10.")
    with read_connection() as connection:
        first, second = resolve(connection, first_id), resolve(connection, second_id)
        connection.execute(text("SELECT set_config('statement_timeout','30000',true)"))
        data = (
            connection.execute(
                text(f"""
            WITH endpoints AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:a),4326) a,
                       ST_SetSRID(ST_GeomFromGeoJSON(:b),4326) b
            ), center AS (
                SELECT *,ST_Transform(ST_LineInterpolatePoint(ST_MakeLine(ST_Transform(a,5514),ST_Transform(b,5514)),0.5),4326) mid FROM endpoints
            ), candidates AS MATERIALIZED (
                SELECT p.id,ST_PointOnSurface(p.geom) point,c.a,c.b,c.mid
                FROM ruian_parcely p CROSS JOIN center c
                {"WHERE TRUE" if search_all else "WHERE p.geom && ST_Envelope(ST_Buffer(c.mid::geography,:radius)::geometry)"}
            ), distances AS MATERIALIZED (
                SELECT id,ST_Distance(point::geography,a::geography) distance_a,
                         ST_Distance(point::geography,b::geography) distance_b
                FROM candidates {"" if search_all else "WHERE ST_DWithin(point::geography,mid::geography,:radius)"}
            )
            , best AS (
                SELECT *,abs(distance_a-distance_b) difference_m,
                       abs(distance_a-distance_b)<=:tolerance within_tolerance,
                       count(*) OVER () searched_parcels
                FROM distances
                ORDER BY abs(distance_a-distance_b),greatest(distance_a,distance_b),id
                LIMIT :limit
            )
            SELECT best.*,p.cislo_parcely,p.kod_ku,p.vymera_m2,p.druh_pozemku,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(p.geom,0.00001)) geometry
            FROM best JOIN ruian_parcely p ON p.id=best.id
            ORDER BY difference_m,greatest(distance_a,distance_b),best.id
        """),
                {
                    "a": first["point"],
                    "b": second["point"],
                    "radius": radius_m,
                    "tolerance": tolerance_m,
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    rows = [
        {
            "id": "parcela:" + str(r["id"]),
            "name": r["cislo_parcely"],
            "kod_ku": r["kod_ku"],
            "area_m2": r["vymera_m2"],
            "land_type": r["druh_pozemku"],
            "distance_a_m": round(r["distance_a"], 2),
            "distance_b_m": round(r["distance_b"], 2),
            "difference_m": round(r["difference_m"], 4),
            "within_tolerance": r["within_tolerance"],
        }
        for r in data
    ]
    features = [feature(first, point=True), feature(second, point=True)]
    for row, source in zip(rows, data):
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {"label": f"Parcela {row['name']} · rozdíl {row['difference_m']} m"},
                "geometry": json.loads(source["geometry"]),
            }
        )
    scope_note = (
        "v celé načtené databázi"
        if search_all
        else f"s vnitřním bodem do {radius_m} m od středu obou míst (střed počítán v S-JTSK)"
    )
    answer = result(
        "Parcely s vyrovnanou vzdáleností",
        rows,
        [
            column("name", "Parcela"),
            column("kod_ku", "Kód KÚ"),
            column("area_m2", "Výměra", True, "m²"),
            column("distance_a_m", "K prvnímu místu", True, "m"),
            column("distance_b_m", "Ke druhému místu", True, "m"),
            column("difference_m", "Rozdíl vzdáleností", True, "m"),
            column("within_tolerance", "V toleranci"),
        ],
        features,
        ["ruian_parcely", first["table"], second["table"]],
        f"A: {first['name']}. B: {second['name']}. Vzdušné geodetické vzdálenosti WGS84 od vnitřního bodu parcely k ověřeným bodům institucí; nejde o vchod, délku cesty ani vzdálenost hranice. Prohledáno {data[0]['searched_parcels'] if data else 0} načtených parcel {scope_note}. Řazeno podle nejmenšího rozdílu, potom menší maximální vzdálenosti. Tolerance {tolerance_m} m je testovaná před zaokrouhlením. Platí pouze pro prohledané načtené parcely, ne chybějící data. Číselná přesnost výpočtu není přesnost zdroje ani důkaz přesné rovnosti v terénu. Pokud žádný řádek není v toleranci, vracíme nejbližší výsledky mimo toleranci; nezaměňuj je za shodu. Výběr neověřuje prodejnost, zastavitelnost ani vhodnost k bydlení.",
    )
    answer["result"]["view"] = "map"
    answer["search"] = {
        "first_id": first_id,
        "first_name": first["name"],
        "second_id": second_id,
        "second_name": second["name"],
        "radius_m": None if search_all else radius_m,
        "scope": "loaded_parcels" if search_all else "midpoint_radius",
        "exhaustive_within_scope": True,
        "tolerance_m": tolerance_m,
        "metric": "geodesic_point_distance",
        "searched_parcels": data[0]["searched_parcels"] if data else 0,
        "matches_in_returned_rows": sum(r["within_tolerance"] for r in rows),
        "global_optimum": False,
    }
    count = answer["search"]["searched_parcels"]
    if rows:
        best = rows[0]

        def fmt(value):
            return str(value).replace(".", ",")

        answer["prepared_text"] = (
            f"Prohledal jsem **{count:,} načtených parcel** {scope_note}. Na mapě zobrazuji {len(rows)} kandidátů s nejmenším rozdílem vzdušných vzdáleností.\n\n"
            f"Nejmenší vypočtený rozdíl má **parcela {best['name']} (KÚ {best['kod_ku']})**:\n\n"
            f"- {first['name']}: **{fmt(best['distance_a_m'])} m**.\n"
            f"- {second['name']}: **{fmt(best['distance_b_m'])} m**.\n"
            f"- Rozdíl před zaokrouhlením vzdáleností: **{fmt(best['difference_m'])} m**.\n\n"
            f"Požadovaná tolerance rozdílu: **{fmt(tolerance_m)} m**. "
            + (
                f"Z {len(rows)} zobrazených kandidátů ji splňuje {sum(r['within_tolerance'] for r in rows)}."
                if best["within_tolerance"]
                else "Ani nejlepší kandidát toleranci nesplňuje; nejde o přesnou shodu."
            )
            + "\n\nVzdálenosti měříme od vnitřního bodu parcely k evidovaným bodům institucí, nikoli od vchodu nebo podél cesty. Číselná přesnost výpočtu není přesnost podkladů ani potvrzení rovnosti v terénu. Výběr nezaručuje prodejnost či zastavitelnost a nevztahuje se na chybějící data."
        )
    else:
        answer["prepared_text"] = (
            f"V prohledaném rozsahu ({scope_note}) nejsou dostupné parcely. Zobrazuji pouze obě instituce; chybějící nález není důkazem neexistence pozemků."
        )
    return answer
