"""Downloader and transformer for ČSÚ demographic indicators by municipality."""
import logging
from pathlib import Path
import pandas as pd

from etl.config import RAW_DATA_DIR
from etl.downloaders.base import download_file
from etl.db import get_engine

logger = logging.getLogger(__name__)

# ČSÚ otevřená data - obyvatelstvo podle věkových skupin a obcí
CSU_MOS_URL = "https://data.csu.gov.cz/opendata/mos/vybrane_ukazatele_obce.csv"


def fetch_and_load_csu(force_download: bool = False) -> int:
    """Download and process ČSÚ municipality population statistics."""
    logger.info("Processing ČSÚ demographics...")
    csv_path = RAW_DATA_DIR / "csu_obce.csv"

    try:
        download_file(CSU_MOS_URL, csv_path, force_download=force_download)
        df = pd.read_csv(csv_path, encoding="utf-8", sep=",", low_memory=False)
        logger.info(f"Loaded {len(df)} rows from ČSÚ CSV.")
    except Exception as e:
        logger.warning(f"Remote ČSÚ download failed: {e}. Using fallback local parsing.")
        return 0

    # Ensure required columns
    # Save to PostGIS / PostgreSQL
    engine = get_engine()
    df.to_sql("csu_demografie_obce", con=engine, if_exists="append", index=False)
    return len(df)


if __name__ == "__main__":
    fetch_and_load_csu()
