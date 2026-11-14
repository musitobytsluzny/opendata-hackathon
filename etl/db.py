"""Transactional, constrained and repeatable PostgreSQL / PostGIS writes."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import geoalchemy2  # noqa: F401 - register reflected PostGIS types
import geopandas as gpd
import pandas as pd
from geoalchemy2 import WKTElement
from shapely import force_2d
from shapely.geometry import MultiLineString, MultiPolygon
from sqlalchemy import MetaData, Table, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from etl.config import DATABASE_URL, TARGET_CRS

TABLES = (
    "facility_poi",
    "municipality_status",
    "csu_demografie_obce",
    "sentinel_ndvi_obce",
    "ruian_parcely",
    "ruian_ku",
    "ruian_obce",
    "okresy",
    "kraje",
    "ciselnik_druh_pozemku",
    "ciselnik_povodnove_riziko",
    "ciselnik_kategorie_ochrany",
    "vuv_zaplavova_uzemi",
    "aopk_chranena_uzemi",
    "zabaged_silnice",
    "zabaged_vodni_toky",
    "osm_poi",
    "chmu_stanice_voda",
)
REFERENCES = {
    "kraje",
    "okresy",
    "ciselnik_druh_pozemku",
    "ciselnik_povodnove_riziko",
    "ciselnik_kategorie_ochrany",
}
_engine = None
_connection = ContextVar("etl_connection", default=None)
_kind = ContextVar("etl_data_kind", default="external")


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


@contextmanager
def transaction(kind="external", lock_key="opendata-etl"):
    """One commit for a complete CLI job; nested operations reuse its connection."""
    if _connection.get() is not None:
        yield _connection.get()
        return
    with get_engine().begin() as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(current_schema()), hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )
        connection_token = _connection.set(conn)
        kind_token = _kind.set(kind)
        try:
            yield conn
        finally:
            _kind.reset(kind_token)
            _connection.reset(connection_token)


def execute_sql(sql_statement, params=None):
    with transaction() as conn:
        conn.execute(text(sql_statement), params or {})


def execute_sql_file(file_path: Path):
    execute_sql(file_path.read_text(encoding="utf-8"))


def standardize_gdf(gdf: gpd.GeoDataFrame, geom_col="geom"):
    if gdf.empty:
        return gdf
    if gdf.crs is None:
        raise ValueError("Missing CRS; provide the documented source CRS before importing")
    gdf = gdf.copy()
    original_geometry = gdf.geometry.name
    names = [str(column).lower().strip() for column in gdf.columns]
    if len(names) != len(set(names)):
        raise ValueError("Column names collide after normalization")
    gdf.columns = names
    gdf = gdf.set_geometry(str(original_geometry).lower().strip())
    if gdf.geometry.name != geom_col:
        gdf = gdf.rename_geometry(geom_col)
    gdf = gdf.to_crs(TARGET_CRS)
    gdf[geom_col] = gdf.geometry.make_valid().map(force_2d)
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise ValueError("Null or empty geometry in dataset")
    return gdf


def save_dataframe(frame, table_name):
    if table_name not in TABLES:
        raise ValueError(f"Not an ETL-managed table: {table_name}")
    if frame.empty:
        return 0
    with transaction() as conn:
        table = Table(table_name, MetaData(), autoload_with=conn)
        unknown = set(frame.columns) - set(table.c.keys())
        if unknown:
            raise ValueError(f"Unsupported columns in {table_name}: {sorted(unknown)}")
        kind = "reference" if table_name in REFERENCES else _kind.get()
        previous = conn.scalar(
            text("SELECT data_kind FROM etl_dataset_status WHERE table_name=:name"),
            {"name": table_name},
        )
        if kind != "reference" and previous is not None and previous != kind:
            raise ValueError(
                f"Refusing to mix {previous} and {kind} data in {table_name}; use a separate database or explicit reset"
            )
        if (
            kind == "demo"
            and previous is None
            and conn.scalar(select(func.count()).select_from(table))
        ):
            raise ValueError(
                f"Refusing to seed demo data into nonempty untracked table {table_name}"
            )
        frame = frame.copy()
        if isinstance(frame, gpd.GeoDataFrame):
            geometry_column = frame.geometry.name
            expected_type = table.c[geometry_column].type.geometry_type

            def normalize(geometry):
                if expected_type == "MULTIPOLYGON" and geometry.geom_type == "Polygon":
                    return MultiPolygon([geometry])
                if expected_type == "MULTILINESTRING" and geometry.geom_type == "LineString":
                    return MultiLineString([geometry])
                return geometry

            frame[geometry_column] = frame.geometry.map(normalize)
            frame = pd.DataFrame(frame)
            frame[geometry_column] = frame[geometry_column].map(
                lambda geom: WKTElement(geom.wkt, srid=4326)
            )
        keys = [column.name for column in table.primary_key if column.name in frame.columns]
        if keys:
            frame = frame.drop_duplicates(subset=keys, keep="last")
        records = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
        statement = insert(table)
        if keys and len(keys) == len(table.primary_key):
            updates = {name: statement.excluded[name] for name in frame.columns if name not in keys}
            statement = (
                statement.on_conflict_do_update(index_elements=keys, set_=updates)
                if updates
                else statement.on_conflict_do_nothing()
            )
        else:
            statement = statement.on_conflict_do_nothing()
        conn.execute(statement, records)
        count = conn.scalar(select(func.count()).select_from(table))
        conn.execute(
            text(
                "INSERT INTO etl_dataset_status (table_name, data_kind, row_count) VALUES (:name,:kind,:count) ON CONFLICT (table_name) DO UPDATE SET data_kind=EXCLUDED.data_kind,row_count=EXCLUDED.row_count,loaded_at=now()"
            ),
            {"name": table_name, "kind": kind, "count": count},
        )
    return len(records)


def save_geodataframe(gdf, table_name, if_exists="append", geom_col="geom", index=False):
    if if_exists != "append" or index:
        raise ValueError("Only constrained append/upsert without dataframe indexes is supported")
    return save_dataframe(standardize_gdf(gdf, geom_col), table_name)
