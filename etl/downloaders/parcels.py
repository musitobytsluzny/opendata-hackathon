"""Stream complete cadastral units from ČÚZK, with bounded parallel downloads."""

import json
import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import text

from etl.config import DATA_DIR
from etl.db import save_geodataframe, transaction
from etl.downloaders.arcgis import fetch_layer
from etl.downloaders.base import download_json
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
            count = download_json(
                SERVICE
                + "/5/query?"
                + urllib.parse.urlencode(
                    {"where": f"katastralniuzemi={code}", "returnCountOnly": "true", "f": "json"}
                )
            )
            if count.get("count") != 0:
                raise ValueError(f"Incomplete parcel export for cadastral unit {code}")
            return code, None
        frame["id"] = frame["id"].astype("int64").astype(str)
        frame["kod_ku"] = code
        frame["kod_obce"] = municipality
        frame["cislo_parcely"] = frame["cisloparcely"]
        frame["vymera_m2"] = frame["vymeraparcely"]
        frame["druh_pozemku_id"] = frame["druhpozemkukod"].where(
            frame["druhpozemkukod"].isin(land_types)
        )
        frame["druh_pozemku"] = frame["druhpozemkukod"].map(land_types)
        return code, frame[
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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DATA_DIR / "parcels-progress.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"units": {}}
    pending = []
    total = 0
    with transaction() as connection:
        for unit in units:
            previous = manifest["units"].get(str(unit.kod_ku), {})
            if not force_download and previous.get("status") == "completed":
                count = connection.scalar(
                    text("SELECT count(*) FROM ruian_parcely WHERE kod_ku=:code"),
                    {"code": unit.kod_ku},
                )
                if count == previous.get("rows"):
                    total += count
                    continue
            pending.append(unit)
    # Each complete cadastral export commits independently when invoked as --dataset parcels.
    # An empty official source is explicitly reported as a coverage gap, never synthetic data.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, len(pending), 4):
            for code, frame in pool.map(download, pending[offset : offset + 4]):
                if frame is None:
                    manifest["units"][str(code)] = {"status": "source_empty", "rows": 0}
                else:
                    count = save_geodataframe(frame, "ruian_parcely")
                    total += count
                    manifest["units"][str(code)] = {"status": "completed", "rows": count}
                manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                temporary = manifest_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(manifest, indent=2) + "\n")
                temporary.replace(manifest_path)
            logger.info(
                "Parcels: %s / %s pending cadastral units; %s records",
                min(offset + 4, len(pending)),
                len(pending),
                total,
            )
    return total
