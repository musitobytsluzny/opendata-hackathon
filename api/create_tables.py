"""Apply migrations, adopting the previous create_all schema without deleting data."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.database.connection import engine
from sqlalchemy import inspect

config = Config(str(Path(__file__).with_name("alembic.ini")))
schema = inspect(engine)
if not schema.has_table("alembic_version"):
    legacy = {
        "users": {"id", "username", "password_hash"},
        "profiles": {"id", "user_id", "firstname", "lastname"},
    }
    present = {table for table in legacy if schema.has_table(table)}
    if present:
        if present != set(legacy) or any(
            {column["name"] for column in schema.get_columns(table)} != columns
            for table, columns in legacy.items()
        ):
            raise RuntimeError("Unrecognized legacy schema; migrate it explicitly before startup")
        command.stamp(config, "0001_initial")
command.upgrade(config, "head")
print("Database migrations applied")
