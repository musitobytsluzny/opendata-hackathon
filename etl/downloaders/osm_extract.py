"""Verified regional Geofabrik PBF: repeatable POI import without Overpass availability."""

import hashlib
import json
import logging
import re

import geopandas as gpd
import pandas as pd

from etl.config import DEFAULT_BBOX, RAW_DATA_DIR
from etl.db import save_geodataframe, transaction
from etl.downloaders.base import download_file

URL = "https://download.geofabrik.de/europe/czech-republic/plzensky-latest.osm.pbf"
logger = logging.getLogger(__name__)
AMENITIES = {
    "school": "education",
    "kindergarten": "education",
    "hospital": "healthcare",
    "clinic": "healthcare",
    "doctors": "healthcare",
    "pharmacy": "healthcare",
}
SHOPS = {"supermarket", "convenience"}


def tags_from_hstore(value):
    if not isinstance(value, str):
        return {}
    return {
        json.loads('"' + key + '"', strict=False): json.loads('"' + val + '"', strict=False)
        for key, val in re.findall(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"', value)
    }


def fetch_and_load_osm_extract(bbox=DEFAULT_BBOX, force_download=False):
    path = download_file(URL, RAW_DATA_DIR / "plzensky.osm.pbf", force_download)
    checksum = download_file(URL + ".md5", RAW_DATA_DIR / "plzensky.osm.pbf.md5", force_download)
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "md5").hexdigest()
    expected = checksum.read_text().split()[0]
    if actual != expected:
        raise ValueError(
            "OSM extract checksum mismatch; refresh with --force, never import corrupt data"
        )
    frames = []
    filters = {
        "points": "other_tags LIKE '%\"amenity\"=>%' OR other_tags LIKE '%\"shop\"=>%' OR other_tags LIKE '%\"railway\"=>%' OR highway='bus_stop'",
        "multipolygons": "amenity IN ('school','kindergarten','hospital','clinic','doctors','pharmacy') OR shop IN ('supermarket','convenience')",
    }
    for layer, where in filters.items():
        logger.info("Reading %s POI from verified regional OSM extract", layer)
        frame = gpd.read_file(path, layer=layer, bbox=bbox, where=where)
        records = []
        for _, row in frame.iterrows():
            tags = tags_from_hstore(row.get("other_tags"))
            for key in ("amenity", "shop", "highway", "railway", "name"):
                value = row.get(key)
                if isinstance(value, str) and value:
                    tags[key] = value
            amenity = tags.get("amenity")
            if amenity in AMENITIES:
                category = AMENITIES[amenity]
            elif tags.get("shop") in SHOPS:
                category, amenity = "shopping", tags["shop"]
            elif tags.get("highway") == "bus_stop":
                category, amenity = "transport", "bus_stop"
            elif tags.get("railway") in {"station", "halt"}:
                category, amenity = "transport", "railway_station"
            else:
                continue
            if row.geometry is None or row.geometry.is_empty:
                raise ValueError("OSM POI without geometry")
            way_id = row.get("osm_way_id")
            kind = "node" if layer == "points" else ("way" if pd.notna(way_id) else "relation")
            key = way_id if kind == "way" else row["osm_id"]
            records.append(
                {
                    "id": f"osm-{kind}-{key}",
                    "name": tags.get("name", "Zařízení bez uvedeného názvu"),
                    "category": category,
                    "amenity": amenity,
                    "geom": row.geometry.representative_point(),
                }
            )
        if records:
            frames.append(gpd.GeoDataFrame(records, geometry="geom", crs=frame.crs))
    if not frames:
        raise ValueError("No POI in verified OSM extract")
    with transaction(lock_key="opendata-osm"):
        return save_geodataframe(
            gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geom", crs=4326),
            "osm_poi",
        )


def fetch_and_load_route_features(force_download=False):
    """Map tags along routes, not a safety score or evidence of absent hazards."""
    from sqlalchemy import text

    from etl.config import ETL_DIR

    path = download_file(URL, RAW_DATA_DIR / "plzensky.osm.pbf", force_download)
    checksum = download_file(URL + ".md5", RAW_DATA_DIR / "plzensky.osm.pbf.md5", force_download)
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "md5").hexdigest() != checksum.read_text().split()[0]:
            raise ValueError("OSM route-feature checksum mismatch")
    frames = []
    for layer, where in [
        (
            "points",
            "highway IN ('crossing','traffic_signals','stop','give_way') OR other_tags LIKE '%\"traffic_calming\"=>%'",
        ),
        ("lines", "highway IS NOT NULL AND highway NOT IN ('construction','proposed')"),
    ]:
        frame = gpd.read_file(path, layer=layer, bbox=DEFAULT_BBOX, where=where)
        records = []
        for _, row in frame.iterrows():
            tags = tags_from_hstore(row.get("other_tags"))
            highway = row.get("highway")
            highway = highway if isinstance(highway, str) else tags.get("highway")
            if highway:
                tags["highway"] = highway
            kind = (
                "road_segment"
                if layer == "lines"
                else (
                    "crossing"
                    if highway == "crossing"
                    else "traffic_signals"
                    if highway == "traffic_signals"
                    else "traffic_control"
                )
            )
            records.append(
                {
                    "id": f"osm-{'node' if layer == 'points' else 'way'}-{row['osm_id']}",
                    "kind": kind,
                    "name": row.get("name"),
                    "highway": highway,
                    "tags_json": tags,
                    "geom": row.geometry,
                }
            )
        if records:
            frames.append(gpd.GeoDataFrame(records, geometry="geom", crs=frame.crs))
    if not frames:
        raise ValueError("No route features in OSM source")
    with transaction(lock_key="opendata-route-context") as connection:
        connection.execute(text((ETL_DIR / "sql" / "004_route_context.sql").read_text()))
        return save_geodataframe(
            gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geom", crs=4326),
            "osm_route_features",
        )
