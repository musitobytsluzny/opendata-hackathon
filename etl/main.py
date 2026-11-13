"""One-shot, transactional entry point for development seed / future ETL jobs."""

import logging
import os

import psycopg

logger = logging.getLogger(__name__)


def seed(connection: psycopg.Connection) -> None:
    """Add idempotent inserts/upserts here when seed datasets are available."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'vector')")
        extensions = {row[0] for row in cursor.fetchall()}
        if extensions != {"postgis", "vector"}:
            raise RuntimeError("ETL requires PostGIS and pgvector")
        cursor.execute("SELECT 'users'::regclass, 'profiles'::regclass")
    logger.info("Database is ready; no seed datasets configured yet")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # The context commits on success and rolls back on failure.
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        seed(connection)
    logger.info("ETL completed")


if __name__ == "__main__":
    main()
