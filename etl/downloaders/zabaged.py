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


SERVICE = "https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer"


def fetch_and_load_zabaged(force_download=False):
    """Export official ZABAGED roads and streams for the configured regional envelope."""
    from etl.downloaders.arcgis import fetch_layer

    total = 0
    for layer in (79, 80, 81, 93):
        frame = fetch_layer(SERVICE, layer, f"zabaged-{layer}", force_download)
        if frame.empty:
            continue
        if layer == 93:
            frame["tok_id"] = frame["idvt"].astype("string")
            columns = ["jmeno", "tok_id", "geometry"]
            table = "zabaged_vodni_toky"
        else:
            frame["trida"] = (
                frame["typsil_p"]
                if layer == 79
                else ("neevidovaná" if layer == 80 else "ve výstavbě")
            )
            frame["cislo_silnice"] = frame["silnice"] if "silnice" in frame else None
            frame["povrch"] = None
            columns = ["trida", "cislo_silnice", "povrch", "geometry"]
            table = "zabaged_silnice"
        total += save_geodataframe(frame[columns], table)
    return total
