"""Downloader and transformer for VÚV flood zones (Q5, Q20, Q100, active zones)."""

import logging

import geopandas as gpd

from etl.config import RAW_DATA_DIR
from etl.db import save_geodataframe
from etl.downloaders.base import download_file, unzip_file

logger = logging.getLogger(__name__)

# VÚV HEIS záplavová území ČR (SHP archiv)
VUV_ZAPLAVY_URL = "https://heis.vuv.cz/data/webmap/datovesady/isvs/ZaplavUzemi/zaplav_uzemi_shp.zip"


def fetch_and_load_vuv(force_download: bool = False) -> int:
    """Download and process VÚV flood zones."""
    logger.info("Processing VÚV flood zones...")
    zip_path = RAW_DATA_DIR / "vuv_zaplavy.zip"

    try:
        download_file(VUV_ZAPLAVY_URL, zip_path, force_download=force_download)
        extract_dir = unzip_file(zip_path)
        shp_files = list(extract_dir.glob("*.shp"))
        if not shp_files:
            logger.warning("No SHP files found in VÚV archive.")
            return 0

        gdf = gpd.read_file(shp_files[0])
        logger.info(f"Loaded {len(gdf)} flood zone polygons.")

        # Standardize columns
        gdf["q_stupen"] = gdf.get("PERIODICIT", "Q100")
        gdf["q_stupen"] = (
            gdf["q_stupen"].astype(str).str.upper().str.replace(r"\.0$", "", regex=True)
        )
        gdf["q_stupen"] = gdf["q_stupen"].map(
            lambda value: value if value.startswith("Q") else "Q" + value
        )
        if not gdf["q_stupen"].isin(["Q5", "Q20", "Q100", "Q500"]).all():
            raise ValueError("Unknown flood recurrence values; map the source schema explicitly")
        gdf["aktivni_zona"] = (
            gdf["TYP"].fillna("").str.lower().str.contains("aktiv") if "TYP" in gdf else False
        )
        gdf["tok_nazev"] = gdf.get("NAZEV_TOKU", "Neznámý tok")

        gdf = gdf[["q_stupen", "aktivni_zona", "tok_nazev", "geometry"]]
        return save_geodataframe(gdf, "vuv_zaplavova_uzemi", if_exists="append")
    except Exception as e:
        logger.warning(f"Could not download or process remote VÚV flood data: {e}")
        return 0


if __name__ == "__main__":
    fetch_and_load_vuv()
