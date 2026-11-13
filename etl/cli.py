"""Transactional ETL CLI. Imports never silently fall back to demo data."""

import argparse
import logging

from etl.config import RAW_DATA_DIR
from etl.db import transaction
from etl.downloaders.aopk import fetch_and_load_aopk
from etl.downloaders.csu import fetch_and_load_csu
from etl.downloaders.osm import fetch_and_load_osm
from etl.downloaders.ruian import load_ruian_from_local_or_remote
from etl.downloaders.vuv import fetch_and_load_vuv
from etl.downloaders.zabaged import process_local_zabaged_gpkg
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
    actions.add_argument("--dataset", choices=["ruian", "csu", "vuv", "aopk", "zabaged", "osm"])
    actions.add_argument(
        "--all", action="store_true", help="Import real data without truncating existing tables"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Explicitly drop ETL-owned tables before this operation",
    )
    parser.add_argument("--force", action="store_true", help="Refresh cached downloads")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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
            "zabaged": lambda **_: process_local_zabaged_gpkg(RAW_DATA_DIR / "zabaged.gpkg"),
            "osm": fetch_and_load_osm,
        }
        for name, loader in loaders.items():
            if args.all or args.dataset == name:
                count = loader(force_download=args.force)
                if count <= 0:
                    raise RuntimeError(
                        f"{name}: no records imported; rolling back, no demo fallback"
                    )
                logger.info("Imported %s: %s rows", name, count)
