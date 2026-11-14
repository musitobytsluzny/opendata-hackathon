"""Read-only domain queries shared by MCP and the API; never execute model-written SQL."""

import re
from contextlib import contextmanager

import httpx
from sqlalchemy import text

from app.database.connection import engine
from app.schemas.chat import Metric
from app.services import cuzk_client

DISTRICTS = {
    "Domažlice": "CZ0321000000",
    "Klatovy": "CZ0322000000",
    "Plzeň-město": "CZ0323000000",
    "Plzeň-jih": "CZ0324000000",
    "Plzeň-sever": "CZ0325000000",
    "Rokycany": "CZ0326000000",
    "Tachov": "CZ0327000000",
}
METRICS = {
    "population": (
        "csu_demografie_obce",
        "SUM(s.pocet_obyvatel)",
        "Počet obyvatel dostupných obcí",
        "Obyvatelé",
        "",
    ),
    "seniors_pct": (
        "csu_demografie_obce",
        "100.0 * SUM(s.seniori_65_plus) / NULLIF(SUM(s.pocet_obyvatel), 0)",
        "Podíl seniorů v dostupných obcích",
        "Senioři",
        "%",
    ),
    "children_pct": (
        "csu_demografie_obce",
        "100.0 * SUM(s.deti_0_14) / NULLIF(SUM(s.pocet_obyvatel), 0)",
        "Podíl dětí v dostupných obcích",
        "Děti",
        "%",
    ),
    "greenery_pct": (
        "sentinel_ndvi_obce",
        "AVG(s.podil_zelene_pct)",
        "Průměrný podíl zeleně dostupných obcí",
        "Zeleň",
        "%",
    ),
    "ndvi": ("sentinel_ndvi_obce", "AVG(s.avg_ndvi)", "Průměr NDVI dostupných obcí", "NDVI", ""),
}


@contextmanager
def read_connection():
    with engine.begin() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SELECT set_config('statement_timeout', '5000', true)"))
        yield connection


def catalog():
    with read_connection() as connection:
        if connection.scalar(text("SELECT to_regclass('etl_dataset_status')")) is None:
            return {"datasets": [], "note": "ETL schéma není připravené."}
        rows = (
            connection.execute(
                text(
                    "SELECT table_name, data_kind, row_count, loaded_at FROM etl_dataset_status "
                    "ORDER BY table_name LIMIT 32"
                )
            )
            .mappings()
            .all()
        )
    return {
        "datasets": [dict(row, loaded_at=row["loaded_at"].isoformat()) for row in rows],
        "note": "Pouze načtené vrstvy; demo = syntetické údaje. Žádná vrstva nezaručuje úplné pokrytí.",
    }


def statistics(metric: Metric):
    if metric not in METRICS:
        raise ValueError("Unsupported metric")
    table, expression, title, short, unit = METRICS[metric]
    sources = catalog()["datasets"]
    required = {table, "ruian_obce"}
    relevant = [row for row in sources if row["table_name"] in required]
    if len(relevant) < 2 or any(row["row_count"] == 0 for row in relevant):
        return {
            "map": None,
            "datasets": relevant,
            "note": "Pro tuto metriku nejsou načtená data. Nevymýšlej hodnoty.",
        }
    period = (
        "MIN(s.rok)::text || '–' || MAX(s.rok)::text"
        if table == "csu_demografie_obce"
        else "'období neuvedeno'"
    )
    # Both interpolated fragments come exclusively from the fixed allowlist above.
    with read_connection() as connection:
        rows = (
            connection.execute(
                text(f"""
            SELECT d.nazev AS district, {expression} AS value, COUNT(*) AS municipalities,
                   {period} AS period
            FROM {table} s JOIN ruian_obce o ON o.kod_obce=s.kod_obce
            JOIN okresy d ON d.kod_okresu=o.kod_okresu
            GROUP BY d.nazev ORDER BY d.nazev LIMIT 7
        """)
            )
            .mappings()
            .all()
        )
    values = [
        {"okres": DISTRICTS[row["district"]], "value": float(row["value"])}
        for row in rows
        if row["district"] in DISTRICTS and row["value"] is not None
    ]
    sample = any(row["data_kind"] == "demo" for row in relevant)
    count = sum(row["municipalities"] for row in rows)
    return {
        "map": {
            "metric": title,
            "short": short,
            "unit": unit,
            "signed": False,
            "rows": values,
            "source": {
                "name": f"{table}; pokrytí {count} obcí",
                "publisher": "Syntetická demo data ETL" if sample else "Lokální ETL",
                "period": ", ".join(sorted({row["period"] for row in rows})),
            },
        },
        "datasets": relevant,
        "district_names": {code: name for name, code in DISTRICTS.items()},
        "sample": sample,
        "note": "Jen dostupné obce, nikoli úplné okresní součty; chybějící okresy nejsou nuly.",
    }


def _enrich_with_zoning(result: dict, lon: float | None, lat: float | None) -> dict:
    """Attach Plzeňský kraj spatial planning (ÚAP/ÚPD) and radon risk for coordinates."""
    if lon is None or lat is None:
        return result
    zoning_data = cuzk_client.fetch_zoning_at_point(float(lon), float(lat))
    if isinstance(result, dict):
        result.update(zoning_data)
    return result


def prevalidate_point(lat: float, lon: float):
    with read_connection() as connection:
        result = connection.scalar(
            text("SELECT fn_prevalidate_point(:lat, :lon)"), {"lat": lat, "lon": lon}
        )
    if not result:
        return {"status": "not_found", "message": "Bod nelze ověřit."}
    result.pop("geojson", None)
    return _enrich_with_zoning(result, lon=lon, lat=lat)


@contextmanager
def write_connection():
    with engine.begin() as connection:
        connection.execute(text("SELECT set_config('statement_timeout', '10000', true)"))
        yield connection


def resolve_kod_ku(connection, nazev_ku: str, cislo: str | None = None) -> int | None:
    cleaned = nazev_ku.strip()
    if cleaned.isdigit():
        return int(cleaned)

    query = text("""
        SELECT ku.kod_ku
        FROM ruian_ku ku
        LEFT JOIN ruian_parcely p ON p.kod_ku = ku.kod_ku AND p.cislo_parcely = :cislo
        WHERE unaccent(ku.nazev) ILIKE unaccent(:name)
           OR unaccent(:name) ILIKE ('%' || unaccent(ku.nazev) || '%')
        ORDER BY (p.id IS NOT NULL) DESC, ku.kod_ku ASC
        LIMIT 1
    """)
    code = connection.scalar(query, {"name": cleaned, "cislo": cislo or ""})
    if code:
        return code

    stem = cleaned[:5] if len(cleaned) >= 5 else cleaned
    query_stem = text("""
        SELECT ku.kod_ku
        FROM ruian_ku ku
        LEFT JOIN ruian_parcely p ON p.kod_ku = ku.kod_ku AND p.cislo_parcely = :cislo
        WHERE unaccent(ku.nazev) ILIKE unaccent(:stem || '%')
        ORDER BY (p.id IS NOT NULL) DESC, ku.kod_ku ASC
        LIMIT 1
    """)
    code = connection.scalar(query_stem, {"stem": stem, "cislo": cislo or ""})
    if code:
        return code

    # Search ČÚZK Layer 7 on-demand if not present in local ruian_ku
    cuzk_kus = cuzk_client.fetch_cadastral_area_by_name(cleaned)
    if cuzk_kus:
        best_ku = cuzk_kus[0]
        try:
            with write_connection() as write_conn:
                cuzk_client.ensure_cadastral_area_and_municipality(write_conn, best_ku["kod"])
        except Exception:
            pass
        return best_ku["kod"]
    return None


def prevalidate_parcel(
    kod_ku: int | None = None,
    cislo: str = "",
    *,
    nazev_ku: str | None = None,
):
    with read_connection() as connection:
        if kod_ku is None and nazev_ku:
            kod_ku = resolve_kod_ku(connection, nazev_ku, cislo)
        if kod_ku is None:
            return {
                "status": "not_found",
                "message": f"Katastrální území odpovídající '{nazev_ku}' nebylo nalezeno.",
            }
        result = connection.scalar(
            text("SELECT fn_prevalidate_parcel(:kod, :cislo)"), {"kod": kod_ku, "cislo": cislo}
        )

    # Fetch parcel geometry on-demand from ČÚZK if missing locally
    if not result or result.get("status") == "not_found":
        cuzk_feat = cuzk_client.fetch_parcel_by_number(kod_ku, cislo)
        if cuzk_feat:
            try:
                with write_connection() as write_conn:
                    cuzk_client.save_parcel_to_db(write_conn, cuzk_feat)
                with read_connection() as connection:
                    result = connection.scalar(
                        text("SELECT fn_prevalidate_parcel(:kod, :cislo)"),
                        {"kod": kod_ku, "cislo": cislo},
                    )
            except Exception:
                pass

    if not result or result.get("status") == "not_found":
        return result or {"status": "not_found", "message": "Parcela nebyla nalezena."}

    result.pop("geojson", None)

    with read_connection() as connection:
        coords = (
            connection.execute(
                text(
                    "SELECT ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat "
                    "FROM ruian_parcely WHERE kod_ku = :kod AND cislo_parcely = :cislo LIMIT 1"
                ),
                {"kod": kod_ku, "cislo": cislo},
            )
            .mappings()
            .first()
        )
    if coords and coords["lon"] is not None and coords["lat"] is not None:
        lon, lat = float(coords["lon"]), float(coords["lat"])
        if isinstance(result.get("parcel"), dict):
            result["parcel"]["coordinates"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
        _enrich_with_zoning(result, lon=lon, lat=lat)

    return result


def prevalidate_address(
    adresa: str | None = None,
    cislo_popisne: int | None = None,
    cislo_orientacni: int | None = None,
    obec: str | None = None,
    ulice: str | None = None,
):
    matches = cuzk_client.search_address(
        query=adresa,
        cislo_popisne=cislo_popisne,
        cislo_orientacni=cislo_orientacni,
        obec=obec,
        ulice=ulice,
    )
    if not matches:
        return {
            "status": "not_found",
            "message": "Adresní místo nebylo v katastru nemovitostí (RÚIAN) nalezeno.",
        }

    match = matches[0]
    lon, lat = match["lon"], match["lat"]

    with read_connection() as connection:
        local_parcel = (
            connection.execute(
                text(
                    "SELECT p.kod_ku, p.cislo_parcely FROM ruian_parcely p "
                    "WHERE ST_Intersects(p.geom, ST_SetSRID(ST_Point(:lon, :lat), 4326)) LIMIT 1"
                ),
                {"lon": lon, "lat": lat},
            )
            .mappings()
            .first()
        )

    if local_parcel:
        kod_ku = local_parcel["kod_ku"]
        cislo = local_parcel["cislo_parcely"]
    else:
        cuzk_feat = cuzk_client.fetch_parcel_at_point(lon, lat)
        if not cuzk_feat:
            # Even without parcel polygon, point prevalidation + zoning can still run at address coordinates
            fallback = prevalidate_point(lat=lat, lon=lon)
            if isinstance(fallback, dict):
                fallback["address"] = {
                    "adresa": match["adresa"],
                    "cislodomovni": match.get("cislodomovni"),
                    "cisloorientacni": match.get("cisloorientacni"),
                    "psc": match.get("psc"),
                    "lat": lat,
                    "lon": lon,
                }
                fallback["parcel_note"] = (
                    f"Pro adresu '{match['adresa']}' nebyl nalezen polygon parcely, "
                    "analýza vychází ze souřadnic adresního bodu."
                )
            return fallback
        try:
            with write_connection() as write_conn:
                cuzk_client.save_parcel_to_db(write_conn, cuzk_feat)
        except Exception:
            pass
        attrs = cuzk_feat["attributes"]
        kod_ku = attrs["katastralniuzemi"]
        cislo = attrs["cisloparcely"]

    result = prevalidate_parcel(kod_ku=kod_ku, cislo=cislo)
    if isinstance(result, dict):
        result["address"] = {
            "adresa": match["adresa"],
            "cislodomovni": match.get("cislodomovni"),
            "cisloorientacni": match.get("cisloorientacni"),
            "psc": match.get("psc"),
            "lat": lat,
            "lon": lon,
        }
    return result


def search_amenities(query: str, obec: str | None = None, kategorie: str | None = None) -> dict:
    results = []
    with read_connection() as connection:
        q_like = f"%{query.strip()}%"
        rows = (
            connection.execute(
                text(
                    "SELECT id, name, category, amenity, ST_X(geom) as lon, ST_Y(geom) as lat "
                    "FROM osm_poi "
                    "WHERE unaccent(name) ILIKE unaccent(:q) OR unaccent(amenity) ILIKE unaccent(:q) "
                    "LIMIT 5"
                ),
                {"q": q_like},
            )
            .mappings()
            .all()
        )
        for row in rows:
            results.append(
                {
                    "nazev": row["name"],
                    "kategorie": row["category"],
                    "typ": row["amenity"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "zdroj": "lokální databáze POI",
                }
            )

    if len(results) < 3:
        base = query.strip()
        queries_to_try = []
        if obec and obec.lower() not in base.lower():
            queries_to_try.append(f"{base}, {obec}")
        else:
            queries_to_try.append(base)

        cleaned = re.sub(r"\b(budov[aě]|škol[ae]|informace|o|při)\b", "", base, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned != base:
            queries_to_try.append(
                f"{cleaned}, {obec}" if obec and obec.lower() not in cleaned.lower() else cleaned
            )

        if "domov" in base.lower() and "mládež" in base.lower():
            queries_to_try.append(f"domov mládeže, {obec or 'Plzeň'}")
        if "voš" in base.lower() or "spše" in base.lower():
            queries_to_try.append(f"VOŠ a SPŠE, {obec or 'Plzeň'}")

        seen_names = {r["nazev"] for r in results}
        for q_try in queries_to_try:
            try:
                params = {
                    "q": q_try,
                    "format": "json",
                    "limit": 3,
                    "countrycodes": "cz",
                }
                with httpx.Client(
                    timeout=3.0, headers={"User-Agent": "OpenDataHackathon/1.0"}
                ) as client:
                    resp = client.get("https://nominatim.openstreetmap.org/search", params=params)
                    if resp.status_code == 200:
                        for it in resp.json():
                            name = it.get("name") or it.get("display_name", "").split(",")[0]
                            if name not in seen_names:
                                seen_names.add(name)
                                results.append(
                                    {
                                        "nazev": name,
                                        "adresa": it.get("display_name"),
                                        "kategorie": it.get("class")
                                        or kategorie
                                        or "občanská vybavenost",
                                        "typ": it.get("type"),
                                        "lat": float(it["lat"]),
                                        "lon": float(it["lon"]),
                                        "zdroj": "OpenStreetMap",
                                    }
                                )
            except Exception:
                pass
            if len(results) >= 3:
                break

    return {
        "vysledky": results[:5],
        "pocet": len(results[:5]),
        "dotaz": query,
        "obec": obec,
    }
