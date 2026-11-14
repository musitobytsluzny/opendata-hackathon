"""Complete ArcGIS exports by explicit object IDs with bounded cached pages."""

import hashlib
import json
import logging
import urllib.parse

import geopandas as gpd

from etl.config import DEFAULT_BBOX, RAW_DATA_DIR, TARGET_CRS
from etl.downloaders.base import download_json, download_json_file

logger = logging.getLogger(__name__)


def fetch_layer(
    service: str,
    layer: int,
    name: str,
    force: bool = False,
    where: str = "1=1",
    spatial: bool = True,
    page_size: int = 100,
) -> gpd.GeoDataFrame:
    url = f"{service}/{layer}/query"
    query = {
        "where": where,
        "geometry": ",".join(map(str, DEFAULT_BBOX)),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "returnIdsOnly": "true",
        "f": "json",
    }
    if not spatial:
        for key in ("geometry", "geometryType", "inSR", "spatialRel"):
            query.pop(key, None)
    signature = hashlib.sha256(
        (url + str(page_size) + json.dumps(query, sort_keys=True)).encode()
    ).hexdigest()[:12]
    directory = RAW_DATA_DIR / "arcgis" / signature
    cache = directory / (name + "-ids.json")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and not force:
        ids = json.loads(cache.read_text())
    else:
        data = download_json(url + "?" + urllib.parse.urlencode(query))
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        ids = sorted(data.get("objectIds") or [])
        cache.write_text(json.dumps(ids))
    features = []
    for offset in range(0, len(ids), page_size):
        page = directory / f"{name}-{offset}.geojson"
        params = {
            "objectIds": ",".join(map(str, ids[offset : offset + page_size])),
            "outFields": "*",
            "outSR": 4326,
            "returnGeometry": "true",
            "f": "geojson",
        }
        data = download_json_file(url + "?" + urllib.parse.urlencode(params), page, force)
        if "error" in data or data.get("exceededTransferLimit"):
            raise RuntimeError(f"Incomplete ArcGIS page: {name}/{offset}")
        batch = data.get("features", [])
        if len(batch) != len(ids[offset : offset + page_size]):
            page.unlink(missing_ok=True)
            raise RuntimeError(f"Incomplete feature count: {name}/{offset}")
        features.extend(batch)
        logger.info("%s: %s / %s features", name, len(features), len(ids))
    return (
        gpd.GeoDataFrame.from_features(features, crs=TARGET_CRS)
        if features
        else gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)
    )
