"""Stream complete cadastral units from ČÚZK, with bounded parallel downloads."""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from etl.db import save_geodataframe, transaction
from etl.downloaders.arcgis import fetch_layer
from etl.downloaders.ruian import SERVICE

logger = logging.getLogger(__name__)


def fetch_and_load_parcels(force_download=False):
    with transaction() as connection:
        units = list(
            connection.execute(text("SELECT kod_ku, kod_obce FROM ruian_ku ORDER BY kod_ku"))
        )
        land_types = dict(
            connection.execute(text("SELECT id, nazev FROM ciselnik_druh_pozemku")).tuples().all()
        )
    if not units:
        raise ValueError("Import RÚIAN municipality and cadastral boundaries first")

    def download(unit):
        code, municipality = unit
        frame = fetch_layer(
            SERVICE,
            5,
            f"parcels-{code}",
            force_download,
            where=f"katastralniuzemi={code}",
            spatial=False,
            page_size=250,
        )
        if frame.empty:
            raise ValueError(f"No parcels returned for cadastral unit {code}")
        frame["id"] = frame["id"].astype("int64").astype(str)
        frame["kod_ku"] = code
        frame["kod_obce"] = municipality
        frame["cislo_parcely"] = frame["cisloparcely"]
        frame["vymera_m2"] = frame["vymeraparcely"]
        frame["druh_pozemku_id"] = frame["druhpozemkukod"].where(
            frame["druhpozemkukod"].isin(land_types)
        )
        frame["druh_pozemku"] = frame["druhpozemkukod"].map(land_types)
        return frame[
            [
                "id",
                "kod_ku",
                "kod_obce",
                "cislo_parcely",
                "vymera_m2",
                "druh_pozemku_id",
                "druh_pozemku",
                "geometry",
            ]
        ]

    total = 0
    # Small waves bound both response memory and concurrent requests to the public source.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, len(units), 4):
            for frame in pool.map(download, units[offset : offset + 4]):
                total += save_geodataframe(frame, "ruian_parcely")
            logger.info(
                "Parcels: %s / %s cadastral units; %s records",
                min(offset + 4, len(units)),
                len(units),
                total,
            )
    return total
