"""Run migration paths in isolated, temporary PostgreSQL schemas."""

import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from app.database.connection import engine, settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "migration_test_" + uuid.uuid4().hex
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        url = make_url(settings.database_url).set(drivername="postgresql+psycopg")
        self.url = url.update_query_dict({"options": f"-csearch_path={self.schema}"})
        self.db = create_engine(self.url)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.db.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def migrate(self):
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "create_tables.py")],
            env={**os.environ, "DATABASE_URL": self.url.render_as_string(hide_password=False)},
            check=True,
            capture_output=True,
            text=True,
        )

    def test_fresh_database_and_repeated_start(self):
        self.migrate()
        self.migrate()
        with self.db.begin() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT version_num FROM alembic_version")),
                "0002_user_roles",
            )
            connection.execute(
                text("INSERT INTO users (username, password_hash) VALUES ('test', 'hash')")
            )
            self.assertEqual(connection.scalar(text("SELECT role FROM users")), "user")
        with self.assertRaises(IntegrityError), self.db.begin() as connection:
            connection.execute(text("UPDATE users SET role='owner'"))

    def test_legacy_database_preserves_accounts_and_profiles(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, "
                    "password_hash VARCHAR(255) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE profiles (id SERIAL PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL "
                    "REFERENCES users(id), firstname VARCHAR(100) NOT NULL, lastname VARCHAR(100) NOT NULL)"
                )
            )
            connection.execute(text("INSERT INTO users VALUES (1, 'legacy', 'existing-hash')"))
            connection.execute(text("INSERT INTO profiles VALUES (1, 1, 'Legacy', 'Profile')"))
        self.migrate()
        self.migrate()
        with self.db.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT u.username, u.password_hash, u.role, p.firstname FROM users u "
                    "JOIN profiles p ON p.user_id=u.id"
                )
            ).one()
            self.assertEqual(tuple(row), ("legacy", "existing-hash", "user", "Legacy"))
