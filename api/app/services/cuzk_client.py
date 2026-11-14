"""ČÚZK ArcGIS REST API client for on-demand parcel and address lookups."""

import json
import logging
import re

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

CUZK_BASE_URL = "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer"
TIMEOUT_SECONDS = 10.0


def _clean_sql_like(val: str) -> str:
    """Sanitize string for SQL LIKE in ArcGIS where clause."""
    return val.replace("'", "''").replace("%", "").replace(";", "")


def parse_parcel_number(cislo: str) -> tuple[int, int | None]:
    """Parse parcel number string into (kmenove_cislo, poddeleni_cisla).
    Examples: '841/1' -> (841, 1), '969' -> (969, None).
    """
    clean = cislo.strip()
    match = re.match(r"^(\d+)(?:/(\d+))?$", clean)
    if not match:
        raise ValueError(f"Neplatný formát čísla parcely: {cislo}")
    kmen = int(match.group(1))
    pod = int(match.group(2)) if match.group(2) else None
    return kmen, pod


def fetch_parcel_by_number(kod_ku: int, cislo: str) -> dict | None:
    """Fetch parcel from ČÚZK Layer 5 (Parcela) by cadastral code and parcel number."""
    try:
        kmen, pod = parse_parcel_number(cislo)
    except ValueError:
        return None

    # First attempt: exact match on cisloparcely
    where = f"katastralniuzemi={kod_ku} AND cisloparcely='{_clean_sql_like(cislo)}'"
    params = {
        "where": where,
        "outFields": "*",
        "outSR": "4326",
        "f": "json",
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/5/query", params=params)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])

            # Second attempt if exact string not matched: kmen and pod
            if not features:
                pod_cond = f"poddelenicisla={pod}" if pod is not None else "poddelenicisla IS NULL"
                where2 = f"katastralniuzemi={kod_ku} AND kmenovecislo={kmen} AND {pod_cond}"
                params["where"] = where2
                resp2 = client.get(f"{CUZK_BASE_URL}/5/query", params=params)
                resp2.raise_for_status()
                features = resp2.json().get("features", [])

            if not features:
                return None

            feat = features[0]
            rings = feat.get("geometry", {}).get("rings")
            if not rings:
                return None

            return {
                "attributes": feat["attributes"],
                "geometry": feat["geometry"],
                "geojson": {"type": "Polygon", "coordinates": rings},
            }
    except Exception as e:
        logger.warning("Error fetching parcel from ČÚZK: %s", e)
        return None


def fetch_parcel_at_point(lon: float, lat: float) -> dict | None:
    """Fetch parcel from ČÚZK Layer 5 (Parcela) intersecting given WGS84 coordinates."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "f": "json",
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/5/query", params=params)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return None

            feat = features[0]
            rings = feat.get("geometry", {}).get("rings")
            if not rings:
                return None

            return {
                "attributes": feat["attributes"],
                "geometry": feat["geometry"],
                "geojson": {"type": "Polygon", "coordinates": rings},
            }
    except Exception as e:
        logger.warning("Error fetching parcel at point from ČÚZK: %s", e)
        return None


def search_address(
    query: str | None = None,
    cislo_popisne: int | None = None,
    cislo_orientacni: int | None = None,
    obec: str | None = None,
    ulice: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Search address places in ČÚZK Layer 1 (AdresniMisto)."""
    clauses: list[str] = []

    if cislo_popisne is not None:
        if cislo_orientacni is not None:
            clauses.append(
                f"cislodomovni = {int(cislo_popisne)} AND cisloorientacni = {int(cislo_orientacni)}"
            )
        else:
            clauses.append(
                f"(cislodomovni = {int(cislo_popisne)} OR cisloorientacni = {int(cislo_popisne)})"
            )
    elif cislo_orientacni is not None:
        clauses.append(f"cisloorientacni = {int(cislo_orientacni)}")

    if obec:
        clauses.append(f"adresa LIKE '%{_clean_sql_like(obec)}%'")
    if ulice:
        clauses.append(f"adresa LIKE '%{_clean_sql_like(ulice)}%'")

    if query and not clauses:
        clean_q = query.strip()
        num_match = re.search(r"(\d+)(?:/(\d+))?", clean_q)
        if num_match:
            n1 = int(num_match.group(1))
            n2 = int(num_match.group(2)) if num_match.group(2) else None
            if n2 is not None:
                clauses.append(f"(cislodomovni = {n1} AND cisloorientacni = {n2})")
            else:
                clauses.append(f"(cislodomovni = {n1} OR cisloorientacni = {n1})")
            text_only = clean_q[: num_match.start()] + clean_q[num_match.end() :]
        else:
            text_only = clean_q

        parts = [p.strip() for p in text_only.split(",") if p.strip()]
        if len(parts) > 1:
            for p in parts:
                if len(p) >= 2:
                    clauses.append(f"adresa LIKE '%{_clean_sql_like(p)}%'")
        else:
            words = [w for w in re.split(r"[\s]+", text_only) if len(w) >= 3]
            for w in words:
                clauses.append(f"adresa LIKE '%{_clean_sql_like(w)}%'")

    where = " AND ".join(clauses) if clauses else "1=1"
    params = {
        "where": where,
        "outFields": "adresa,cislodomovni,cisloorientacni,cisloorientacnipismeno,psc,stavebniobjekt,ulice",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": limit,
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/1/query", params=params)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for feat in data.get("features", []):
                attrs = feat.get("attributes", {})
                geom = feat.get("geometry", {})
                if "x" in geom and "y" in geom:
                    results.append(
                        {
                            "adresa": attrs.get("adresa"),
                            "cislodomovni": attrs.get("cislodomovni"),
                            "cisloorientacni": attrs.get("cisloorientacni"),
                            "psc": attrs.get("psc"),
                            "stavebniobjekt": attrs.get("stavebniobjekt"),
                            "lon": geom["x"],
                            "lat": geom["y"],
                        }
                    )
            return results
    except Exception as e:
        logger.warning("Error searching address in ČÚZK: %s", e)
        return []


def fetch_cadastral_area_by_code(kod_ku: int) -> dict | None:
    """Fetch cadastral area from ČÚZK Layer 7 (KatastralniUzemi)."""
    params = {"where": f"kod={kod_ku}", "outFields": "kod,nazev,obec", "f": "json"}
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/7/query", params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])
            if not features:
                return None
            attr = features[0].get("attributes", {})
            return {
                "kod": attr.get("kod"),
                "nazev": attr.get("nazev"),
                "kod_obce": attr.get("obec"),
            }
    except Exception as e:
        logger.warning("Error fetching KÚ %s from ČÚZK: %s", kod_ku, e)
        return None


def fetch_cadastral_area_by_name(nazev: str) -> list[dict]:
    """Search cadastral areas in ČÚZK Layer 7 by name."""
    clean = _clean_sql_like(nazev.strip())
    params = {
        "where": f"nazev LIKE '%{clean}%'",
        "outFields": "kod,nazev,obec",
        "f": "json",
        "resultRecordCount": 5,
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/7/query", params=params)
            resp.raise_for_status()
            results = []
            for feat in resp.json().get("features", []):
                attr = feat.get("attributes", {})
                results.append(
                    {
                        "kod": attr.get("kod"),
                        "nazev": attr.get("nazev"),
                        "kod_obce": attr.get("obec"),
                    }
                )
            return results
    except Exception as e:
        logger.warning("Error searching KÚ '%s' from ČÚZK: %s", nazev, e)
        return []


def fetch_municipality_by_code(kod_obce: int) -> dict | None:
    """Fetch municipality name from ČÚZK Layer 12 (Obec)."""
    params = {"where": f"kod={kod_obce}", "outFields": "kod,nazev", "f": "json"}
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.get(f"{CUZK_BASE_URL}/12/query", params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])
            if not features:
                return None
            attr = features[0].get("attributes", {})
            return {"kod": attr.get("kod"), "nazev": attr.get("nazev")}
    except Exception as e:
        logger.warning("Error fetching Obec %s from ČÚZK: %s", kod_obce, e)
        return None


def ensure_cadastral_area_and_municipality(connection, kod_ku: int) -> int | None:
    """Ensure ruian_ku and ruian_obce records exist in the database for kod_ku."""
    existing_obec = connection.scalar(
        text("SELECT kod_obce FROM ruian_ku WHERE kod_ku = :ku"), {"ku": kod_ku}
    )
    if existing_obec is not None:
        return existing_obec

    ku_data = fetch_cadastral_area_by_code(kod_ku)
    if not ku_data:
        return None

    kod_obce = ku_data.get("kod_obce")
    if kod_obce is None or not connection.scalar(
        text("SELECT 1 FROM ruian_obce WHERE kod_obce=:code"), {"code": kod_obce}
    ):
        return None

    connection.execute(
        text(
            "INSERT INTO ruian_ku (kod_ku, kod_obce, nazev) VALUES (:ku, :o, :n) "
            "ON CONFLICT (kod_ku) DO NOTHING"
        ),
        {"ku": kod_ku, "o": kod_obce, "n": ku_data.get("nazev", f"K.ú. {kod_ku}")},
    )
    return kod_obce


def save_parcel_to_db(connection, parcel_feat: dict) -> bool:
    """Save or update parcel in ruian_parcely from ČÚZK feature dictionary."""
    attrs = parcel_feat.get("attributes", {})
    geojson = json.dumps(parcel_feat.get("geojson", {}))
    kod_ku = attrs.get("katastralniuzemi")
    cislo = attrs.get("cisloparcely")
    druh_id = attrs.get("druhpozemkukod")
    vymera = int(attrs.get("vymeraparcely") or 0)
    raw_id = attrs.get("id")
    if not (kod_ku and cislo and raw_id):
        return False

    parcel_id = str(int(raw_id))

    # Verify druh_id exists in ciselnik_druh_pozemku
    if druh_id is not None:
        exists = connection.scalar(
            text("SELECT 1 FROM ciselnik_druh_pozemku WHERE id = :id"), {"id": druh_id}
        )
        if not exists:
            druh_id = None

    # Ensure KU and Obec records exist in database
    kod_obce = ensure_cadastral_area_and_municipality(connection, kod_ku)
    if kod_obce is None:
        return False

    query = text("""
        INSERT INTO ruian_parcely (id, kod_ku, cislo_parcely, druh_pozemku_id, vymera_m2, geom, kod_obce)
        VALUES (:id, :kod_ku, :cislo, :druh_id, :vymera, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)), :kod_obce)
        ON CONFLICT (id) DO UPDATE SET
            geom = EXCLUDED.geom,
            vymera_m2 = EXCLUDED.vymera_m2,
            druh_pozemku_id = EXCLUDED.druh_pozemku_id,
            cislo_parcely = EXCLUDED.cislo_parcely
    """)
    connection.execute(
        query,
        {
            "id": parcel_id,
            "kod_ku": kod_ku,
            "cislo": cislo,
            "druh_id": druh_id,
            "vymera": vymera,
            "geojson": geojson,
            "kod_obce": kod_obce,
        },
    )
    return True
