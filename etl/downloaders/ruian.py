"""Downloader and parser for RÚIAN municipality boundaries and parcels."""

import logging

import geopandas as gpd

from etl.config import CZECH_NATIONAL_CRS, RAW_DATA_DIR, TARGET_CRS
from etl.db import save_geodataframe
from etl.downloaders.base import download_file, unzip_file
from etl.seed import seed_administrative_hierarchy

logger = logging.getLogger(__name__)

RUIAN_STAT_URL = "https://services.cuzk.cz/shp/stat/epsg-5514/1.zip"

OKRES_MAP = {
    "3401": "Domažlice",
    "3402": "Klatovy",
    "3403": "Plzeň-jih",
    "3404": "Plzeň-sever",
    "3405": "Plzeň-město",
    "3406": "Rokycany",
    "3407": "Tachov",
}


def load_ruian_from_local_or_remote(force_download: bool = False) -> int:
    """Fetch RÚIAN administrative hierarchy (Kraje, Okresy, Obce, KÚ, Parcely) and load to PostGIS."""
    logger.info("Processing RÚIAN administrative hierarchy...")
    zip_path = RAW_DATA_DIR / "ruian_stat.zip"

    # 1. Ensure Kraje and Okresy exist for FK integrity
    seed_administrative_hierarchy()

    try:
        download_file(RUIAN_STAT_URL, zip_path, force_download=force_download)
        extract_dir = unzip_file(zip_path, extract_to=RAW_DATA_DIR / "ruian_stat")

        # 2. Obce (OBCE_P.shp)
        shp_candidates = list(extract_dir.rglob("*OBCE*.shp"))

        if not shp_candidates:
            logger.warning("No SHP files found in RÚIAN archive.")
            return 0

        shp_file = shp_candidates[0]
        logger.info(f"Reading shapefile: {shp_file}")
        gdf = gpd.read_file(shp_file, encoding="cp1250")
        logger.info(f"Loaded {len(gdf)} total municipalities from RÚIAN.")

        # Filter to Plzeň Region (VÚSC 43)
        if "VUSC_KOD" in gdf.columns:
            gdf = gdf[gdf["VUSC_KOD"].astype(str) == "43"].copy()
            logger.info(f"Filtered {len(gdf)} municipalities in Plzeň Region (VÚSC 43).")

        if "VUSC_KOD" not in gdf.columns:
            raise ValueError("RÚIAN response needs a region identifier before importing")

        gdf["kod_obce"] = gdf["KOD"].astype(int)
        gdf["kod_okresu"] = gdf["OKRES_KOD"].astype("Int64").astype(str)
        gdf["nazev"] = gdf["NAZEV"].astype(str)
        gdf["okres"] = gdf["kod_okresu"].map(OKRES_MAP).fillna("Plzeňský kraj")

        gdf = gdf[["kod_obce", "kod_okresu", "nazev", "okres", "geometry"]]

        if gdf.crs is None:
            gdf.set_crs(CZECH_NATIONAL_CRS, inplace=True)
        gdf = gdf.to_crs(TARGET_CRS)

        total_saved = save_geodataframe(gdf, "ruian_obce", if_exists="append", geom_col="geom")

        # 3. Katastrální území (KATUZE_P.shp)
        ku_candidates = list(extract_dir.rglob("*KATUZE*.shp"))
        if ku_candidates:
            logger.info(f"Reading KÚ shapefile: {ku_candidates[0]}")
            ku_gdf = gpd.read_file(ku_candidates[0], encoding="cp1250")
            if "VUSC_KOD" in ku_gdf.columns:
                ku_gdf = ku_gdf[ku_gdf["VUSC_KOD"].astype(str) == "43"].copy()

            ku_gdf["kod_ku"] = ku_gdf["KOD"].astype(int)
            ku_gdf["kod_obce"] = ku_gdf["OBEC_KOD"].astype(int)
            ku_gdf["nazev"] = ku_gdf["NAZEV"].astype(str)
            ku_gdf = ku_gdf[["kod_ku", "kod_obce", "nazev", "geometry"]]

            if ku_gdf.crs is None:
                ku_gdf.set_crs(CZECH_NATIONAL_CRS, inplace=True)
            ku_gdf = ku_gdf.to_crs(TARGET_CRS)

            logger.info(f"Saving {len(ku_gdf)} cadastral areas (KÚ) for Plzeň Region...")
            save_geodataframe(ku_gdf, "ruian_ku", if_exists="append", geom_col="geom")

        # 4. Parcely (linked with lookups and KÚ)
        # Parcels require an actual source; never synthesize parcel records here.

        return total_saved
    except Exception as e:
        logger.warning(f"Could not download or process remote RÚIAN: {e}")
        return 0


if __name__ == "__main__":
    load_ruian_from_local_or_remote()
