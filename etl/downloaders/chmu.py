"""ČHMÚ station catalogue. Metadata do not imply a current flood alert."""

import json
import re
import urllib.request

import geopandas as gpd
from shapely.geometry import Point

from etl.config import DEFAULT_BBOX, RAW_DATA_DIR
from etl.db import save_geodataframe
from etl.downloaders.base import download_file

DIRECTORY = "https://opendata.chmi.cz/hydrology/recent/metadata/"


def fetch_and_load_chmu(force_download=False):
    with urllib.request.urlopen(DIRECTORY, timeout=90) as response:
        listing = response.read().decode("utf-8")
    files = sorted(set(re.findall(r"meta1-\d{8}\.json", listing)))
    if not files:
        raise ValueError("ČHMÚ station metadata not found")
    path = download_file(DIRECTORY + files[-1], RAW_DATA_DIR / files[-1], force_download)
    collection = json.loads(path.read_text())["data"]["data"]
    headers = collection["header"].split(",")
    xmin, ymin, xmax, ymax = DEFAULT_BBOX
    records = []
    for values in collection["values"]:
        row = dict(zip(headers, values, strict=True))
        lat, lon = row["GEOGR1"], row["GEOGR2"]
        if lat is None or lon is None or not (xmin <= lon <= xmax and ymin <= lat <= ymax):
            continue
        records.append(
            {
                "stanice_kod": row["DBC"],
                "nazev": row["STATION_NAME"],
                "tok": row["STREAM_NAME"],
                "spa_aktualni": None,
                "geom": Point(lon, lat),
            }
        )
    if not records:
        return 0
    return save_geodataframe(
        gpd.GeoDataFrame(records, geometry="geom", crs=4326), "chmu_stanice_voda"
    )
