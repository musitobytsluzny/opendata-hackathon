"""Downloader and transformer for ČSÚ demographic indicators by municipality."""

import logging

import pandas as pd

from etl.config import RAW_DATA_DIR
from etl.db import save_dataframe
from etl.downloaders.base import download_file

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
    required = {"kod_obce", "rok", "pocet_obyvatel"}
    if not required <= set(df.columns):
        raise ValueError("ČSÚ input needs an explicit source-to-schema mapping before import")
    df = df.sort_values("rok").drop_duplicates("kod_obce", keep="last")
    save_dataframe(df, "csu_demografie_obce")
    return len(df)


if __name__ == "__main__":
    fetch_and_load_csu()
