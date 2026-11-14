"""AOPK regional protected areas from the current official ArcGIS service."""

import geopandas as gpd
import pandas as pd

from etl.db import save_geodataframe
from etl.downloaders.arcgis import fetch_layer

SERVICE = "https://gis.nature.cz/arcgis/rest/services/UzemniOchrana/ChranUzemi/MapServer"


def fetch_and_load_aopk(force_download=False):
    frames = []
    for layer, category, buffer in [
        (0, "Maloplošné chráněné území", False),
        (1, "Ochranné pásmo MZCHÚ", True),
        (3, "Velkoplošné chráněné území", False),
        (4, "Smluvně chráněné území", False),
    ]:
        frame = fetch_layer(SERVICE, layer, f"aopk-{layer}", force_download)
        if frame.empty:
            continue
        names = {str(c).lower(): c for c in frame.columns}
        name = next((names[k] for k in ["nazev", "nazev_zchu", "nazev_uzemi"] if k in names), None)
        code = next((names[k] for k in ["kod", "kod_zchu", "objectid"] if k in names), None)
        if code is None:
            raise ValueError("Missing AOPK feature identifier")
        frame["kod"] = str(layer) + ":" + frame[code].astype(str)
        frame["nazev"] = frame[name] if name else category
        frame["kategorie"] = category
        frame["ochranne_pasmo"] = buffer
        frames.append(frame[["kod", "nazev", "kategorie", "ochranne_pasmo", "geometry"]])
    if not frames:
        return 0
    return save_geodataframe(
        gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326"),
        "aopk_chranena_uzemi",
    )
