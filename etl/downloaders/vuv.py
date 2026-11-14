"""VÚV official regional flood polygons; all recurrence layers and active zones."""

import geopandas as gpd
import pandas as pd

from etl.db import save_geodataframe
from etl.downloaders.arcgis import fetch_layer

SERVICE = "https://ags2.vuv.cz/arcgis/rest/services/isvs_voda/isvs_voda/MapServer"


def fetch_and_load_vuv(force_download=False):
    frames = []
    for layer, recurrence, active in [
        (15, "Q5", False),
        (14, "Q20", False),
        (13, "Q100", False),
        (12, "Q500", False),
        (11, None, True),
    ]:
        frame = fetch_layer(SERVICE, layer, f"vuv-{layer}", force_download)
        if frame.empty:
            continue
        frame["q_stupen"] = recurrence
        frame["aktivni_zona"] = active
        frame["tok_nazev"] = frame["NAZ_TOK"] if "NAZ_TOK" in frame else None
        frames.append(frame[["q_stupen", "aktivni_zona", "tok_nazev", "geometry"]])
    if not frames:
        return 0
    return save_geodataframe(
        gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326"),
        "vuv_zaplavova_uzemi",
    )
