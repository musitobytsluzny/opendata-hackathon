"""Downloader and transformer for AOPK protected areas (nature protection)."""

import logging
import urllib.parse

import geopandas as gpd
import pandas as pd

from etl.config import DEFAULT_BBOX, RAW_DATA_DIR, TARGET_CRS
from etl.db import save_geodataframe, standardize_gdf
from etl.downloaders.base import download_file

logger = logging.getLogger(__name__)

# AOPK ArcGIS REST endpointy
AOPK_SERVICES = [
    {
        "name": "MZCHÚ",
        "url": "https://gis.nature.cz/arcgis/rest/services/UOP/ZCHU/MapServer/0/query",
        "kategorie": "Maloplošné chráněné území",
        "out_file": "aopk_mzchu.geojson",
    },
    {
        "name": "VZCHÚ",
        "url": "https://gis.nature.cz/arcgis/rest/services/UOP/ZCHU/MapServer/1/query",
        "kategorie": "Velkoplošné chráněné území (CHKO/NP)",
        "out_file": "aopk_vzchu.geojson",
    },
]


def fetch_and_load_aopk(force_download: bool = False) -> int:
    """Fetch AOPK protected areas and load into PostGIS."""
    logger.info("Fetching AOPK protected areas...")

    total_records = 0
    gdfs = []
    failed = []

    for svc in AOPK_SERVICES:
        out_path = RAW_DATA_DIR / svc["out_file"]
        # Standard ArcGIS REST query parameters
        params = {"where": "1=1", "outFields": "*", "returnGeometry": "true", "f": "geojson"}
        full_url = f"{svc['url']}?{urllib.parse.urlencode(params)}"

        try:
            download_file(full_url, out_path, force_download=force_download)
            gdf = gpd.read_file(out_path)
            if not gdf.empty:
                gdf["kategorie"] = svc["kategorie"]
                gdf["ochranne_pasmo"] = False
                name_col = next(
                    (c for c in ["NAZEV", "nazev", "KAT_NAZEV"] if c in gdf.columns), None
                )
                gdf["nazev"] = gdf[name_col] if name_col else svc["name"]
                code_col = next((c for c in ["KOD", "kod", "OBJECTID"] if c in gdf.columns), None)
                if code_col is None:
                    raise ValueError("AOPK response has no stable feature identifier")
                gdf["kod"] = gdf[code_col].astype(str) if code_col else None

                gdf = gdf[["kod", "nazev", "kategorie", "ochranne_pasmo", "geometry"]]
                gdfs.append(standardize_gdf(gdf))
        except Exception as e:
            failed.append(svc["name"])
            logger.warning(f"Could not fetch AOPK {svc['name']}: {e}. Skipping remote fetch.")

    if failed:
        raise RuntimeError(f"Incomplete AOPK import: {failed}")
    if gdfs:
        combined_gdf = gpd.GeoDataFrame(
            pd.concat(gdfs, ignore_index=True), geometry="geom", crs=TARGET_CRS
        )
        min_lon, min_lat, max_lon, max_lat = DEFAULT_BBOX
        combined_gdf = combined_gdf.cx[min_lon:max_lon, min_lat:max_lat]
        total_records = save_geodataframe(combined_gdf, "aopk_chranena_uzemi", if_exists="append")

    return total_records


if __name__ == "__main__":
    fetch_and_load_aopk()
