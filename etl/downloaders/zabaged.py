"""Load documented road and watercourse layers from a local GeoPackage."""

from pathlib import Path

import geopandas as gpd

from etl.db import save_geodataframe, standardize_gdf


def process_local_zabaged_gpkg(gpkg_path: Path) -> int:
    if not gpkg_path.exists():
        raise FileNotFoundError(f"Supply the local ZABAGED GeoPackage: {gpkg_path}")
    total = 0
    for layer, table, columns in (
        ("SilnicniSit", "zabaged_silnice", ["trida", "cislo_silnice", "povrch", "geom"]),
        ("VodniTok", "zabaged_vodni_toky", ["jmeno", "tok_id", "geom"]),
    ):
        frame = standardize_gdf(gpd.read_file(gpkg_path, layer=layer))
        frame = frame[[column for column in columns if column in frame.columns]]
        total += save_geodataframe(frame, table)
    return total
