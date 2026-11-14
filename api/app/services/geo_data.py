"""Read-only domain queries shared by MCP and the API; never execute model-written SQL."""

from contextlib import contextmanager

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

    # 3. If not found locally in ruian_ku, search ČÚZK Layer 7 on-demand
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
    cislo: str,
    kod_ku: int | None = None,
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

    # If not found locally in DB, fetch on-demand from ČÚZK!
    if not result or result.get("status") == "not_found":
        if "/" not in cislo:
            with read_connection() as connection:
                candidates = (
                    connection.execute(
                        text("""
                            SELECT id, cislo_parcely, druh_pozemku, vymera_m2
                            FROM ruian_parcely
                            WHERE kod_ku = :kod
                              AND split_part(cislo_parcely, '/', 1) = :cislo
                              AND cislo_parcely <> :cislo
                            ORDER BY cislo_parcely
                            LIMIT 10
                        """),
                        {"kod": kod_ku, "cislo": cislo},
                    )
                    .mappings()
                    .all()
                )
            if candidates:
                numbers = [candidate["cislo_parcely"] for candidate in candidates]
                return {
                    "status": "ambiguous" if len(candidates) > 1 else "not_found",
                    "message": (
                        f"Samostatná parcela {cislo} nebyla nalezena. "
                        f"V katastrálním území jsou pod tímto kmenovým číslem: "
                        f"{', '.join(numbers)}. Upřesněte celé číslo parcely."
                    ),
                    "candidates": [dict(candidate) for candidate in candidates],
                }

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

    parcel = result.get("parcel")
    if parcel and parcel.get("id") is not None:
        from app.services.workspace_data import place_geometry

        presentation = place_geometry("parcela:" + str(parcel["id"]))["result"]
        presentation["title"] = f"Parcela {parcel['cislo_parcely']} · {parcel['ku_nazev']}"
        presentation["view"] = "map"
        sources = result.get("data_sources", {})
        in_scope = bool(result.get("location_hierarchy", {}).get("municipality_code"))
        flood_loaded = in_scope and sources.get("vuv_zaplavova_uzemi", {}).get("rows", 0) > 0
        nature_loaded = in_scope and sources.get("aopk_chranena_uzemi", {}).get("rows", 0) > 0
        zoning = result.get("zoning_plan", {})
        planning_status = (
            "developable"
            if zoning.get("is_developable_area")
            else (
                "built_up"
                if zoning.get("in_built_up_area")
                else (
                    "non_developable"
                    if zoning.get("is_non_developable_parcel")
                    else ("available" if zoning.get("available") else "not_available")
                )
            )
        )
        presentation["rows"] = [
            {
                "id": "parcela:" + str(parcel["id"]),
                "kod_ku": parcel["kod_ku"],
                "cislo_parcely": parcel["cislo_parcely"],
                "name": presentation["title"],
                "area_m2": parcel.get("vymera_m2"),
                "land_type": parcel.get("druh_pozemku"),
                "assessment_kind": result.get("assessment_kind"),
                "planning_assessment": planning_status,
                "radon_category": result.get("radon_risk", {}).get("category")
                if result.get("radon_risk")
                else None,
                "flood_q20": result.get("flood_risk", {}).get("in_q20") if flood_loaded else None,
                "flood_q100": result.get("flood_risk", {}).get("in_q100") if flood_loaded else None,
                "active_flood_zone": result.get("flood_risk", {}).get("in_active_zone")
                if flood_loaded
                else None,
                "protected_area": result.get("nature_protection", {}).get("in_protected_area")
                if nature_loaded
                else None,
            }
        ]
        presentation["rows"][0]["planning_status_label"] = {
            "developable": "Bodový nález zastavitelné plochy",
            "built_up": "Bodový nález zastavěného území",
            "non_developable": "Bodový nález nezastavitelné plochy",
            "available": "Bodový nález funkčního využití",
            "not_available": "Neověřeno",
        }.get(planning_status, "Neověřeno")
        if zoning.get("conflicting_designations"):
            presentation["rows"][0]["planning_status_label"] = (
                "Rozporné bodové nálezy; nutno ověřit"
            )
        presentation["columns"] = [
            {"key": "name", "label": "Parcela"},
            {"key": "area_m2", "label": "Výměra", "numeric": True, "unit": "m²"},
            {"key": "land_type", "label": "Druh pozemku"},
            {"key": "flood_q20", "label": "Průnik Q20"},
            {"key": "flood_q100", "label": "Průnik Q100"},
            {"key": "active_flood_zone", "label": "Průnik aktivní záplavové zóny"},
            {"key": "protected_area", "label": "Průnik ochrany přírody"},
            {"key": "planning_status_label", "label": "ÚAP – orientační bodový nález"},
            {"key": "radon_category", "label": "Regionální kategorie radonu"},
        ]
        presentation["note"] += (
            " Nezjištěný průnik s načtenou vrstvou nepotvrzuje bezrizikovost. Neověřeno neznamená nulové riziko. "
            + zoning.get(
                "note", "Územní plán není ověřen pro celou parcelu; nejde o stavební povolení."
            )
        )
        if zoning.get("source_url"):
            presentation["sources"].append(
                {
                    "name": "Geoportál Plzeňského kraje – ÚAP",
                    "url": zoning["source_url"],
                    "assessment_scope": "reference_point_only",
                }
            )

        result["result"] = presentation
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

    unique = list(
        {
            (match.get("adresa"), match.get("lon"), match.get("lat")): match for match in matches
        }.values()
    )
    if len(unique) > 1:
        return {
            "status": "ambiguous",
            "message": "Adresa má více shod. Upřesněte obec, ulici a číslo domu; žádnou variantu nevybíráme automaticky.",
            "candidates": unique,
        }
    match = unique[0]
    lon, lat = match["lon"], match["lat"]

    # 1. Try local parcel at coordinates
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
        # 2. Fetch on-demand from ČÚZK at coordinates
        cuzk_feat = cuzk_client.fetch_parcel_at_point(lon, lat)
        if not cuzk_feat:
            return {
                "status": "not_found",
                "message": f"Pro adresu '{match['adresa']}' se nepodařilo dohledat parcelu v katastru.",
                "address": match,
            }
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
    from app.services.workspace_data import search_places

    categories = {
        "healthcare": "healthcare",
        "zdravotnictví": "healthcare",
        "lékař": "healthcare",
        "lékaři": "healthcare",
        "ordinace": "healthcare",
        "education": "education",
        "škola": "education",
        "školy": "education",
        "školství": "education",
        "zš": "education",
        "mš": "education",
        "transport": "transport",
        "doprava": "transport",
        "zastávka": "transport",
        "shopping": "shopping",
        "obchod": "shopping",
        "potraviny": "shopping",
    }
    category = categories.get(kategorie.strip().casefold()) if kategorie else None
    if kategorie and category is None:
        from app.services import workspace_data

        payload = workspace_data.result(
            "Nalezená místa",
            [],
            [workspace_data.column("name", "Místo"), workspace_data.column("id", "Identifikátor")],
            tables=["osm_poi", "facility_poi"],
            note=(
                f"Samostatná kategorie „{kategorie}“ není v načtených datech podporována. "
                "Prázdný výsledek nedokazuje, že taková místa v okolí neexistují."
            ),
        )
    else:
        payload = search_places(query, "poi", 5, municipality=obec, category=category)
    payload["result"]["view"] = "map"
    features = {feature["id"]: feature for feature in payload["result"]["features"]}
    payload["vysledky"] = [
        {
            "id": row["id"],
            "nazev": row["name"],
            "lon": features[row["id"]]["geometry"]["coordinates"][0],
            "lat": features[row["id"]]["geometry"]["coordinates"][1],
            "zdroj": "načtené prostorové podklady",
        }
        for row in payload["result"]["rows"]
    ]
    payload.update(pocet=len(payload["vysledky"]), dotaz=query, obec=obec)
    return payload
