"""Complete regional RÚIAN boundaries exported from the official ArcGIS service."""

import geopandas as gpd
import pandas as pd

from etl.db import save_geodataframe
from etl.downloaders.arcgis import fetch_layer
from etl.seed import seed_administrative_hierarchy

SERVICE = "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer"
OKRES_MAP = {
    "3401": "Domažlice",
    "3404": "Klatovy",
    "3405": "Plzeň-město",
    "3406": "Plzeň-jih",
    "3407": "Plzeň-sever",
    "3408": "Rokycany",
    "3410": "Tachov",
}


def load_ruian_from_local_or_remote(force_download=False):
    seed_administrative_hierarchy()
    frame = fetch_layer(
        SERVICE,
        12,
        "ruian-obce",
        force_download,
        where="okres IN (" + ",".join(OKRES_MAP) + ")",
        spatial=False,
    )
    if frame.empty:
        return 0
    frame["kod_obce"] = frame["kod"].astype(int)
    frame["kod_okresu"] = frame["okres"].astype(int).astype(str)
    frame["okres"] = frame.kod_okresu.map(OKRES_MAP)
    total = save_geodataframe(
        frame[["kod_obce", "kod_okresu", "nazev", "okres", "geometry"]], "ruian_obce"
    )
    codes = list(frame.kod_obce)
    areas = []
    for offset in range(0, len(codes), 50):
        area = fetch_layer(
            SERVICE,
            7,
            f"ruian-ku-{offset}",
            force_download,
            where="obec IN (" + ",".join(map(str, codes[offset : offset + 50])) + ")",
            spatial=False,
        )
        if not area.empty:
            areas.append(area)
    if not areas:
        raise ValueError("No cadastral boundaries returned")
    frame = gpd.GeoDataFrame(pd.concat(areas, ignore_index=True), crs="EPSG:4326")
    frame["kod_ku"] = frame.kod.astype(int)
    frame["kod_obce"] = frame.obec.astype(int)
    save_geodataframe(frame[["kod_ku", "kod_obce", "nazev", "geometry"]], "ruian_ku")
    return total
