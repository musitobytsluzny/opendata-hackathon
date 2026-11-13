"""Downloader and transformer for OpenStreetMap Points of Interest (Overpass API)."""

import json
import logging
import urllib.parse

import geopandas as gpd
from shapely.geometry import Point

from etl.config import DEFAULT_BBOX, RAW_DATA_DIR, TARGET_CRS
from etl.db import save_geodataframe
from etl.downloaders.base import download_json

logger = logging.getLogger(__name__)

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"


def build_overpass_query(bbox: tuple) -> str:
    """Build Overpass QL query for essential amenities and transit within bbox."""
    # bbox order in Overpass: (min_lat, min_lon, max_lat, max_lon)
    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"~"hospital|clinic|doctors|pharmacy"]({bbox_str});
      node["amenity"~"school|kindergarten"]({bbox_str});
      node["highway"~"bus_stop"]({bbox_str});
      node["railway"~"station|halt"]({bbox_str});
      node["shop"~"supermarket|convenience"]({bbox_str});
    );
    out body;
    """
    return query.strip()


def fetch_and_load_osm(bbox: tuple = DEFAULT_BBOX, force_download: bool = False) -> int:
    """Fetch POIs from OpenStreetMap via Overpass API (with local caching) and save to PostGIS."""
    logger.info(f"Processing OSM POIs for bbox {bbox}...")
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = RAW_DATA_DIR / "osm_poi.json"

    data = None
    if cache_file.exists() and not force_download:
        logger.info(f"Using cached OSM data from {cache_file}")
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read cached OSM file: {e}")

    if data is None:
        query = build_overpass_query(bbox)
        encoded_query = urllib.parse.urlencode({"data": query})
        full_url = f"{OVERPASS_API_URL}?{encoded_query}"

        try:
            data = download_json(full_url)
            # Save to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"Saved OSM data to cache: {cache_file}")
        except Exception as e:
            logger.warning(
                f"Failed to query Overpass API: {e}. Check network connection or try again later."
            )
            return 0

    elements = data.get("elements", [])
    logger.info(f"Parsing {len(elements)} elements from OSM.")

    records = []
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity")
        highway = tags.get("highway")
        railway = tags.get("railway")
        shop = tags.get("shop")
        name = tags.get("name", "Neznámý název")

        if amenity in ["hospital", "clinic", "doctors", "pharmacy"]:
            category = "healthcare"
        elif amenity in ["school", "kindergarten"]:
            category = "education"
        elif highway == "bus_stop" or railway in ["station", "halt"]:
            category = "transport"
            amenity = "bus_stop" if highway == "bus_stop" else "railway_station"
        elif shop in ["supermarket", "convenience"]:
            category = "shopping"
            amenity = shop
        else:
            category = "other"

        records.append(
            {
                "id": f"osm-{el.get('type', 'node')}-{el.get('id')}",
                "category": category,
                "amenity": amenity or "other",
                "name": name,
                "geom": Point(el["lon"], el["lat"]),
            }
        )

    if not records:
        logger.warning("No OSM records parsed.")
        return 0

    gdf = gpd.GeoDataFrame(records, crs=TARGET_CRS, geometry="geom")
    return save_geodataframe(gdf, "osm_poi", if_exists="append", geom_col="geom")


if __name__ == "__main__":
    fetch_and_load_osm()
