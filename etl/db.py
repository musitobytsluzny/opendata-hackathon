"""Database utilities for PostGIS integration."""
import logging
from pathlib import Path
from typing import Optional, Any, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import geopandas as gpd

from etl.config import DATABASE_URL, TARGET_CRS, CZECH_NATIONAL_CRS

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Get or initialize SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


def standardize_gdf(gdf: gpd.GeoDataFrame, geom_col: str = "geom") -> gpd.GeoDataFrame:
    """Ensure standard CRS (EPSG:4326), valid geometry, and lowercase columns."""
    if gdf.empty:
        return gdf

    gdf = gdf.copy()
    gdf.columns = [str(c).lower().strip() for c in gdf.columns]

    current_geom_col = gdf.geometry.name
    if current_geom_col != geom_col:
        gdf = gdf.rename_geometry(geom_col)

    if gdf.crs is None:
        logger.warning("CRS is missing; assigning default S-JTSK (EPSG:5514)")
        gdf.set_crs(CZECH_NATIONAL_CRS, inplace=True)

    if gdf.crs.to_string() != TARGET_CRS:
        logger.info(f"Transforming CRS from {gdf.crs} to {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    # Ensure valid geometries
    gdf[geom_col] = gdf[geom_col].make_valid()
    gdf = gdf.set_geometry(geom_col)

    return gdf


def save_geodataframe(
    gdf: gpd.GeoDataFrame,
    table_name: str,
    if_exists: str = "replace",
    geom_col: str = "geom",
    index: bool = False
) -> int:
    """Save GeoDataFrame to PostGIS and ensure GIST spatial index."""
    if gdf.empty:
        logger.warning(f"GeoDataFrame for table '{table_name}' is empty. Skipping save.")
        return 0

    gdf = standardize_gdf(gdf, geom_col=geom_col)
    engine = get_engine()

    logger.info(f"Saving {len(gdf)} records to PostGIS table '{table_name}'...")
    gdf.to_postgis(
        name=table_name,
        con=engine,
        if_exists=if_exists,
        index=index
    )

    # Create GIST spatial index
    with engine.connect() as conn:
        index_name = f"idx_{table_name}_{geom_col}"
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} USING GIST ({geom_col});"))
        conn.commit()

    logger.info(f"Table '{table_name}' saved successfully with GIST index.")
    return len(gdf)


def execute_sql(sql_statement: str, params: Optional[Dict[str, Any]] = None) -> None:
    """Execute arbitrary SQL statement."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(sql_statement), params or {})
        conn.commit()


def execute_sql_file(file_path: Path) -> None:
    """Execute SQL file content."""
    logger.info(f"Executing SQL file: {file_path}")
    sql_content = file_path.read_text(encoding="utf-8")
    execute_sql(sql_content)
