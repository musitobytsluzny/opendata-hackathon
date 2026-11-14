"""ČSÚ MOS annual demographics, using the documented indicator codes."""

import logging

import pandas as pd
from sqlalchemy import text

from etl.config import RAW_DATA_DIR
from etl.db import save_dataframe, transaction
from etl.downloaders.base import download_file

logger = logging.getLogger(__name__)
CSU_MOS_URL = "https://opendata.csu.gov.cz/soubory/od/od_mos01/mos_data_2025.csv"
INDICATORS = {"110900": "pocet_obyvatel", "110930": "deti_0_14", "110990": "seniori_65_plus"}


def fetch_and_load_csu(force_download: bool = False) -> int:
    path = download_file(
        CSU_MOS_URL, RAW_DATA_DIR / "csu_mos_2025.csv", force_download=force_download
    )
    with transaction() as connection:
        municipalities = set(connection.scalars(text("SELECT kod_obce FROM ruian_obce")))
    frame = pd.read_csv(
        path, dtype={"kodukaz": str, "koduzemi": int}, skipinitialspace=True, low_memory=False
    )
    frame.columns = frame.columns.str.strip()
    frame = frame[frame.kodukaz.isin(INDICATORS) & frame.koduzemi.isin(municipalities)].copy()
    frame["hodnota"] = pd.to_numeric(frame.hodnota, errors="coerce")
    frame["metric"] = frame.kodukaz.map(INDICATORS)
    result = (
        frame.pivot(index=["koduzemi", "rok"], columns="metric", values="hodnota")
        .reset_index()
        .rename(columns={"koduzemi": "kod_obce"})
    )
    if (
        set(result.kod_obce) != municipalities
        or result[list(INDICATORS.values())].isna().any().any()
    ):
        raise ValueError("Incomplete ČSÚ demographics; missing values must not become zeros")
    result["produktivni_15_64"] = result.pocet_obyvatel - result.seniori_65_plus - result.deti_0_14
    result["prirustek_5y_pct"] = None  # Requires an independently sourced five-year baseline.
    return save_dataframe(result, "csu_demografie_obce")
