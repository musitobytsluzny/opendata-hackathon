"""Transactional ETL CLI. Imports never silently fall back to demo data."""

import argparse
import json
import logging
from datetime import datetime, timezone

from etl.config import DATA_DIR
from etl.db import transaction
from etl.downloaders.aopk import fetch_and_load_aopk
from etl.downloaders.chmu import fetch_and_load_chmu
from etl.downloaders.csu import fetch_and_load_csu
from etl.downloaders.facilities import fetch_and_load_facilities, load_pmdp_stops
from etl.downloaders.osm import fetch_and_load_osm
from etl.downloaders.parcels import fetch_and_load_parcels
from etl.downloaders.ruian import load_ruian_from_local_or_remote
from etl.downloaders.vuv import fetch_and_load_vuv
from etl.downloaders.zabaged import fetch_and_load_zabaged
from etl.seed import drop_tables, run_seed, seed_administrative_hierarchy, seed_lookups, seed_schema

logger = logging.getLogger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--seed", action="store_true", help="Load synthetic demo fixtures explicitly"
    )
    actions.add_argument(
        "--schema", action="store_true", help="Apply schema/functions without data or downloads"
    )
    actions.add_argument(
        "--dataset",
        choices=[
            "ruian",
            "csu",
            "vuv",
            "aopk",
            "zabaged",
            "osm",
            "chmu",
            "parcels",
            "facilities",
            "pmdp",
        ],
    )
    actions.add_argument(
        "--all", action="store_true", help="Import real data without truncating existing tables"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Explicitly drop ETL-owned tables before this operation",
    )
    parser.add_argument("--force", action="store_true", help="Refresh cached downloads")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="With --all, commit each dataset separately and report failures",
    )
    args = parser.parse_args(argv)
    if args.keep_going and not args.all:
        parser.error("--keep-going requires --all")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.keep_going:
        return run_pipeline(force=args.force, reset=args.reset)
    if args.dataset in {"facilities", "pmdp"} and not args.reset:
        loader = fetch_and_load_facilities if args.dataset == "facilities" else load_pmdp_stops
        return loader(force_download=args.force)
    # Release DDL locks before long network downloads / geometry imports.
    # Explicit reset stays atomic with its import.
    if not args.reset:
        with transaction():
            seed_schema()
    with transaction(kind="demo" if args.seed else "external"):
        if args.reset:
            drop_tables()
            seed_schema()
        if args.schema:
            return
        if args.seed:
            run_seed()
            return
        seed_lookups()
        seed_administrative_hierarchy()
        loaders = {
            "ruian": load_ruian_from_local_or_remote,
            "csu": fetch_and_load_csu,
            "vuv": fetch_and_load_vuv,
            "aopk": fetch_and_load_aopk,
            "zabaged": fetch_and_load_zabaged,
            "osm": fetch_and_load_osm,
            "chmu": fetch_and_load_chmu,
            "facilities": fetch_and_load_facilities,
            "pmdp": load_pmdp_stops,
            "parcels": fetch_and_load_parcels,
        }
        for name, loader in loaders.items():
            if args.all or args.dataset == name:
                count = loader(force_download=args.force)
                if count <= 0:
                    raise RuntimeError(
                        f"{name}: no records imported; rolling back, no demo fallback"
                    )
                logger.info("Imported %s: %s rows", name, count)


DATASETS = (
    "ruian",
    "csu",
    "vuv",
    "aopk",
    "zabaged",
    "osm",
    "chmu",
    "facilities",
    "pmdp",
    "parcels",
)


def run_pipeline(force=False, reset=False):
    """Keep successful layers when a different public source is unavailable."""
    if reset:
        main(["--schema", "--reset"])
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "datasets": {}}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "pipeline-report.json"
    failures = []
    for name in DATASETS:
        try:
            main(["--dataset", name] + (["--force"] if force else []))
            report["datasets"][name] = {"status": "completed"}
        except Exception as error:
            logger.exception("Dataset %s failed; previously committed datasets are preserved", name)
            failures.append(name)
            report["datasets"][name] = {"status": "failed", "error": str(error)}
        report["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    if failures:
        raise RuntimeError("Pipeline incomplete: " + ", ".join(failures) + f"; see {path}")
