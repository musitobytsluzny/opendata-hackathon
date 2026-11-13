"""Read-only domain queries shared by MCP and the API; never execute model-written SQL."""

from contextlib import contextmanager

from sqlalchemy import text

from app.database.connection import engine
from app.schemas.chat import Metric

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
        "sample": sample,
        "note": "Jen dostupné obce, nikoli úplné okresní součty; chybějící okresy nejsou nuly.",
    }


def prevalidate_point(lat: float, lon: float):
    with read_connection() as connection:
        result = connection.scalar(
            text("SELECT fn_prevalidate_point(:lat, :lon)"), {"lat": lat, "lon": lon}
        )
    result.pop("geojson", None)
    return result


def prevalidate_parcel(kod_ku: int, cislo: str):
    with read_connection() as connection:
        result = connection.scalar(
            text("SELECT fn_prevalidate_parcel(:kod, :cislo)"), {"kod": kod_ku, "cislo": cislo}
        )
    result.pop("geojson", None)
    return result
