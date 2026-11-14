"""Official civic POI and municipality status, separately attributable from OSM."""

import csv
import io
import logging
import zipfile

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from sqlalchemy import text

from etl.config import DEFAULT_BBOX, ETL_DIR, RAW_DATA_DIR
from etl.db import save_dataframe, save_geodataframe, transaction
from etl.downloaders.arcgis import fetch_layer
from etl.downloaders.base import download_file
from etl.downloaders.ruian import OKRES_MAP
from etl.downloaders.ruian import SERVICE as RUIAN
from etl.downloaders.zabaged import SERVICE

logger = logging.getLogger(__name__)
STATUS = {
    1: "Vojenský újezd",
    2: "Obec",
    3: "Město",
    4: "Statutární město",
    5: "Hlavní město",
    6: "Městys",
}


def fetch_and_load_facilities(force_download=False):
    # Download first; hold no database locks while querying public sources.
    frames = []
    for layer, category, amenity in [
        (47, "education", "school"),
        (48, "education", "educational_facility"),
        (50, "healthcare", "hospital"),
        (51, "healthcare", "healthcare"),
        (58, "transport", "railway_station"),
    ]:
        frame = fetch_layer(SERVICE, layer, f"civic-{layer}", force_download)
        if frame.empty:
            continue
        frame["id"] = f"zabaged-{layer}-" + frame["fid_zbg"].astype(str)
        names = frame["nazev"] if "nazev" in frame else pd.Series(None, index=frame.index)
        # No station name is exposed by layer 58: don't invent one.
        frame["name"] = names.fillna(
            "Železniční stanice / zastávka" if layer == 58 else "Zařízení bez uvedeného názvu"
        )
        frame["category"], frame["amenity"] = category, amenity
        if layer == 47:
            levels = frame["vzdelani_p"].fillna("").str.casefold()
            for phrase, subtype in [
                ("mateřsk", "kindergarten"),
                ("základní", "primary_school"),
                ("střední", "secondary_school"),
                ("vysoká", "university"),
                ("vyšší odborná", "college"),
            ]:
                frame.loc[levels.str.contains(phrase, regex=False), "amenity"] = subtype
        frame["search_text"] = frame["name"].map(institution_aliases)
        frame["publisher"] = "ČÚZK · ZABAGED"
        frame["source_url"] = f"{SERVICE}/{layer}"
        frames.append(
            frame[
                [
                    "id",
                    "name",
                    "category",
                    "amenity",
                    "publisher",
                    "source_url",
                    "search_text",
                    "geometry",
                ]
            ]
        )
    status = fetch_layer(
        RUIAN,
        12,
        "municipality-status",
        force_download,
        where="okres IN (" + ",".join(OKRES_MAP) + ")",
        spatial=False,
    )
    status["kod_obce"] = status["kod"].astype(int)
    status["status_kod"] = status["statuskod"].astype(int)
    status["status_name"] = status.status_kod.map(STATUS)
    if not frames or status.status_name.isna().any():
        raise ValueError("Incomplete official civic data")
    with transaction(lock_key="opendata-facilities") as connection:
        connection.execute(text((ETL_DIR / "sql" / "003_facilities.sql").read_text()))
        count = save_geodataframe(
            gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326), "facility_poi"
        )
        save_dataframe(status[["kod_obce", "status_kod", "status_name"]], "municipality_status")
    return count


PMDP_URL = "https://jizdnirady.pmdp.cz/jr/gtfs"


def load_pmdp_stops(force_download=False):
    path = download_file(PMDP_URL, RAW_DATA_DIR / "pmdp-gtfs.zip", force_download)
    with zipfile.ZipFile(path) as archive:
        # Only read stops, never materialise the large stop_times schedule.
        if archive.getinfo("stops.txt").file_size > 20_000_000:
            raise ValueError("Unexpectedly large GTFS station file")
        rows = list(
            csv.DictReader(io.TextIOWrapper(archive.open("stops.txt"), encoding="utf-8-sig"))
        )
    xmin, ymin, xmax, ymax = DEFAULT_BBOX
    records = []
    for row in rows:
        if row.get("location_type", "0") not in ("", "0", "1"):
            continue
        lon, lat = float(row["stop_lon"]), float(row["stop_lat"])
        if not xmin <= lon <= xmax or not ymin <= lat <= ymax:
            continue
        # Prefer parent stations where present, avoiding several platform hits per stop.
        if row.get("parent_station"):
            continue
        records.append(
            {
                "id": "pmdp-" + row["stop_id"],
                "name": row["stop_name"],
                "category": "transport",
                "amenity": "public_transport_stop",
                "publisher": "PMDP · GTFS (CC BY 4.0)",
                "source_url": PMDP_URL,
                "geom": Point(lon, lat),
            }
        )
    if not records:
        raise ValueError("No PMDP stops with real coordinates")
    with transaction(lock_key="opendata-facilities") as connection:
        connection.execute(text((ETL_DIR / "sql" / "003_facilities.sql").read_text()))
        return save_geodataframe(
            gpd.GeoDataFrame(records, geometry="geom", crs=4326), "facility_poi"
        )


def institution_aliases(name):
    """Search aliases derived mechanically from official names, not guessed addresses."""
    import unicodedata

    folded = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(name).casefold())
        if not unicodedata.combining(c)
    )
    aliases = []
    for phrase, abbreviation in [
        ("vyssi odborna skola", "vos"),
        ("stredni prumyslova skola elektrotechnicka", "spse"),
        ("stredni prumyslova skola", "sps"),
        ("zakladni skola", "zs"),
        ("materska skola", "ms"),
    ]:
        if phrase in folded:
            aliases.append(abbreviation)
    return " ".join(aliases)
