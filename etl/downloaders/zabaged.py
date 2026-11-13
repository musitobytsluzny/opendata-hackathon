"""Processor for ZABAGED transport and hydrology layers from GeoPackage."""
import logging
from pathlib import Path
import geopandas as gpd

from etl.config import RAW_DATA_DIR, TARGET_CRS
from etl.db import save_geodataframe

logger = logging.getLogger(__name__)


def process_local_zabaged_gpkg(gpkg_path: Path) -> int:
    """Extract roads and watercourses from downloaded ZABAGED GeoPackage."""
    if not gpkg_path.exists():
        logger.info(f"ZABAGED GPKG not found at {gpkg_path}. Place ZABAGED GeoPackage here.")
        return 0

    total_loaded = 0
    # 1. Silniční síť
    try:
        roads_gdf = gpd.read_file(gpkg_path, layer="SilnicniSit")
        logger.info(f"Loaded {len(roads_gdf)} roads from ZABAGED.")
        save_geodataframe(roads_gdf, "zabaged_silnice", if_exists="append")
        total_loaded += len(roads_gdf)
    except Exception as e:
        logger.warning(f"Layer SilnicniSit not found in GPKG: {e}")

    # 2. Vodní toky
    try:
        water_gdf = gpd.read_file(gpkg_path, layer="VodniTok")
        logger.info(f"Loaded {len(water_gdf)} watercourses from ZABAGED.")
        save_geodataframe(water_gdf, "zabaged_vodni_toky", if_exists="append")
        total_loaded += len(water_gdf)
    except Exception as e:
        logger.warning(f"Layer VodniTok not found in GPKG: {e}")

    return total_loaded
