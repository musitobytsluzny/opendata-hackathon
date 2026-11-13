"""ETL configuration from the single root .env or process environment."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ETL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ETL_DIR.parent
DATA_DIR = ETL_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Do not silently redirect an unresolved Docker hostname to another database.
DATABASE_URL = make_url(os.environ["DATABASE_URL"]).set(drivername="postgresql+psycopg")
TARGET_CRS = "EPSG:4326"
CZECH_NATIONAL_CRS = "EPSG:5514"
PILOT_BBOX = {
    "plzen_kraj": (12.45, 48.95, 13.95, 50.15),
    "plzen_mesto": (13.25, 49.65, 13.55, 49.85),
}
DEFAULT_BBOX = PILOT_BBOX["plzen_kraj"]
