"""ETL configuration for OpenData Geo MCP.

Handles database connection parameters, spatial references, and target regions.
"""
import os
import socket
from pathlib import Path
from dotenv import load_dotenv

# Base paths
ETL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ETL_DIR.parent
DATA_DIR = ETL_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Ensure data directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load env variables from infra/.env or project root .env
for env_candidate in [PROJECT_ROOT / "infra" / ".env", PROJECT_ROOT / ".env", ETL_DIR / ".env"]:
    if env_candidate.exists():
        load_dotenv(env_candidate)
        break

# Database settings
POSTGRES_USER = os.getenv("POSTGRES_USER", "opendata")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "opendata_dev")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "opendata")

raw_db_url = os.getenv(
    "DATABASE_URL",
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# 1. Host resolution: if host 'db' is unreachable (running on Mac host outside Docker network), fallback to localhost
if "@db:" in raw_db_url or "@db/" in raw_db_url:
    try:
        socket.gethostbyname("db")
    except socket.gaierror:
        raw_db_url = raw_db_url.replace("@db:", "@localhost:").replace("@db/", "@localhost/")

# 2. Driver dialect selection: ensure SQLAlchemy uses available driver (psycopg2 or psycopg)
def normalize_driver(url: str) -> str:
    # If explicit driver is already provided (e.g. postgresql+psycopg2://), keep it
    if "://" in url and not url.startswith("postgresql://"):
        return url

    # Check which driver is installed
    try:
        import psycopg2  # noqa: F401
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    except ImportError:
        pass

    try:
        import psycopg  # noqa: F401
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    except ImportError:
        pass

    # Default fallback
    return url.replace("postgresql://", "postgresql+psycopg2://", 1)

DATABASE_URL = normalize_driver(raw_db_url)

# Spatial settings
TARGET_CRS = "EPSG:4326"  # WGS84 standard for GeoJSON & web mapping
CZECH_NATIONAL_CRS = "EPSG:5514"  # S-JTSK / Krovak East North

# Target Region: Plzeňský kraj & Plzeň-město Bounding Box (WGS84 lon/lat)
# BBOX: [min_lon, min_lat, max_lon, max_lat]
PILOT_BBOX = {
    "plzen_kraj": (12.45, 48.95, 13.95, 50.15),
    "plzen_mesto": (13.25, 49.65, 13.55, 49.85)
}
DEFAULT_BBOX = PILOT_BBOX["plzen_kraj"]
