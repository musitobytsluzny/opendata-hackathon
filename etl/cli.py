"""Command-line interface for OpenData Geo ETL pipeline.

Usage:
    python -m etl.cli --seed               # Load schema and foundational seed data (instant demo)
    python -m etl.cli --reset              # Clean drop and recreate all tables and views
    python -m etl.cli --schema             # Initialize PostgreSQL tables and spatial views
    python -m etl.cli --dataset aopk       # Fetch and load AOPK protected areas
    python -m etl.cli --dataset osm        # Fetch and load OSM amenities for Plzeň region
    python -m etl.cli --dataset csu        # Fetch and load ČSÚ demographic indicators
    python -m etl.cli --dataset vuv        # Fetch and load VÚV flood zones
    python -m etl.cli --dataset ruian      # Fetch and load RÚIAN municipality boundaries
    python -m etl.cli --all                # Run full hybrid ETL pipeline
    python -m etl.cli --all --reset        # Clean drop old tables and run full ETL pipeline
"""
import argparse
import sys
import logging

from etl.seed import (
    run_seed,
    seed_schema,
    drop_tables,
    truncate_tables,
    seed_lookups,
    seed_administrative_hierarchy,
    seed_ruian_obce,
    seed_ruian_ku,
    seed_ruian_parcely,
    seed_vuv_zaplavy,
    seed_aopk_nature,
    seed_zabaged,
    seed_osm_poi,
    seed_csu_and_sentinel
)
from etl.downloaders.aopk import fetch_and_load_aopk
from etl.downloaders.osm import fetch_and_load_osm
from etl.downloaders.csu import fetch_and_load_csu
from etl.downloaders.vuv import fetch_and_load_vuv
from etl.downloaders.ruian import load_ruian_from_local_or_remote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etl")


def main():
    parser = argparse.ArgumentParser(description="OpenData Geo MCP - Hybrid Spatial-Relational ETL Pipeline")
    parser.add_argument("--seed", action="store_true", help="Apply schema and load foundational seed data")
    parser.add_argument("--reset", action="store_true", help="Drop existing tables before running schema/import")
    parser.add_argument("--schema", action="store_true", help="Apply SQL schema and spatial functions only")
    parser.add_argument("--dataset", choices=["ruian", "csu", "vuv", "aopk", "osm"], help="Run specific dataset ETL")
    parser.add_argument("--all", action="store_true", help="Run full ETL for all datasets")
    parser.add_argument("--force", action="store_true", help="Force redownload even if cached")

    args = parser.parse_args()

    if not any([args.seed, args.reset, args.schema, args.dataset, args.all]):
        parser.print_help()
        sys.exit(1)

    # 1. Reset tables if requested
    if args.reset:
        drop_tables()

    # 2. Always ensure database schema and spatial functions exist
    try:
        seed_schema()
    except Exception as e:
        logger.error(f"Failed to connect to database or apply schema: {e}")
        logger.error("Please make sure PostgreSQL is running (e.g. via Docker Compose).")
        sys.exit(1)

    # 3. Pure seed mode
    if args.seed:
        run_seed(reset=False)
        logger.info("Hybrid seed operation completed.")
        return

    # 4. Clean slate for full ETL run to avoid duplicate key conflicts
    if args.all and not args.reset:
        truncate_tables()

    # 5. Always ensure lookups and top-level hierarchy exist for FK integrity
    seed_lookups()
    seed_administrative_hierarchy()

    # 6. Datasets execution in foreign-key safe order:
    # ruian (obce + ku + parcely) -> csu (demografie + sentinel) -> vuv (zaplavy) -> aopk (ochrana) -> zabaged -> osm
    if args.dataset == "ruian" or args.all:
        logger.info("--- Processing RÚIAN (Municipalities, KÚ & Parcels) ---")
        loaded = 0
        try:
            loaded = load_ruian_from_local_or_remote(force_download=args.force)
        except Exception as e:
            logger.warning(f"Remote RÚIAN download failed: {e}")
        if loaded == 0:
            logger.info("Applying foundational RÚIAN municipalities and KÚ for Plzeň...")
            seed_ruian_obce()
            seed_ruian_ku()
            seed_ruian_parcely()

    if args.dataset == "csu" or args.all:
        logger.info("--- Processing ČSÚ Demographics & Sentinel NDVI ---")
        loaded = 0
        try:
            loaded = fetch_and_load_csu(force_download=args.force)
        except Exception as e:
            logger.warning(f"Remote ČSÚ download failed: {e}")
        if loaded == 0:
            logger.info("Applying foundational ČSÚ demographics and Sentinel-2 NDVI metrics...")
            seed_csu_and_sentinel()

    if args.dataset == "vuv" or args.all:
        logger.info("--- Processing VÚV Flood Zones ---")
        loaded = 0
        try:
            loaded = fetch_and_load_vuv(force_download=args.force)
        except Exception as e:
            logger.warning(f"Remote VÚV download failed: {e}")
        if loaded == 0:
            logger.info("Applying foundational VÚV flood zones for Plzeň (Berounka, Radbuza Q100/Q20)...")
            seed_vuv_zaplavy()

    if args.dataset == "aopk" or args.all:
        logger.info("--- Processing AOPK Nature Protection ---")
        loaded = 0
        try:
            loaded = fetch_and_load_aopk(force_download=args.force)
        except Exception as e:
            logger.warning(f"Remote AOPK download failed: {e}")
        if loaded == 0:
            logger.info("Applying foundational AOPK protected areas (Horní Berounka, Bolevecké rybníky)...")
            seed_aopk_nature()

    if args.all:
        logger.info("--- Processing ZABAGED Infrastructure ---")
        seed_zabaged()

    if args.dataset == "osm" or args.all:
        logger.info("--- Processing OSM Amenities & Transit ---")
        loaded = 0
        try:
            loaded = fetch_and_load_osm(force_download=args.force)
        except Exception as e:
            logger.warning(f"Remote OSM query failed: {e}")
        if loaded == 0:
            logger.info("Applying foundational OSM POIs (healthcare, schools, transit, grocery)...")
            seed_osm_poi()

    logger.info("🎉 Hybrid Spatial-Relational ETL pipeline completed successfully!")


if __name__ == "__main__":
    main()
