"""DB-backed grounding tests in isolated schemas, never modifying loaded ETL data."""

import unittest
import uuid
from unittest.mock import patch

from app.database.connection import engine, settings
from app.services import geo_data
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


class GeoDataTests(unittest.TestCase):
    def setUp(self):
        self.schema = "llm_test_" + uuid.uuid4().hex
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.db = create_engine(
            make_url(settings.database_url).set(drivername="postgresql+psycopg"),
            connect_args={"options": f"-csearch_path={self.schema},public"},
        )
        self.patch = patch.object(geo_data, "engine", self.db)
        self.patch.start()
        self.addCleanup(self.cleanup)
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE etl_dataset_status (table_name text, data_kind text, row_count int, loaded_at timestamptz DEFAULT now())"
                )
            )
            connection.execute(text("CREATE TABLE okresy (kod_okresu text, nazev text)"))
            connection.execute(text("CREATE TABLE ruian_obce (kod_obce int, kod_okresu text)"))
            connection.execute(text("CREATE TABLE ruian_ku (kod_ku int, nazev text)"))
            connection.execute(
                text(
                    "CREATE TABLE ruian_parcely (id text, kod_ku int, cislo_parcely text, druh_pozemku text, vymera_m2 int)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE csu_demografie_obce (kod_obce int, rok int, pocet_obyvatel int, seniori_65_plus int, deti_0_14 int)"
                )
            )
            connection.execute(
                text("""
                    CREATE FUNCTION fn_prevalidate_parcel(integer, text)
                    RETURNS jsonb LANGUAGE sql AS $$
                        SELECT jsonb_build_object('status', 'not_found')
                    $$
                """)
            )

    def cleanup(self):
        self.patch.stop()
        self.db.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def test_empty_data_does_not_produce_fake_map(self):
        self.assertIsNone(geo_data.statistics("population")["map"])

    def test_map_values_and_sample_flag_come_from_database(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO etl_dataset_status(table_name,data_kind,row_count) VALUES ('ruian_obce','demo',2),('csu_demografie_obce','demo',2)"
                )
            )
            connection.execute(text("INSERT INTO okresy VALUES ('test','Plzeň-město')"))
            connection.execute(text("INSERT INTO ruian_obce VALUES (1,'test'),(2,'test')"))
            connection.execute(
                text("INSERT INTO csu_demografie_obce VALUES (1,2024,100,20,10),(2,2024,300,30,60)")
            )
        result = geo_data.statistics("population")
        self.assertEqual(result["map"]["rows"], [{"okres": "CZ0323000000", "value": 400.0}])
        self.assertTrue(result["sample"])
        self.assertEqual(geo_data.statistics("seniors_pct")["map"]["rows"][0]["value"], 12.5)
        self.assertIn("2 obcí", result["map"]["source"]["name"])

    def test_queries_are_read_only_and_no_raw_sql_is_accepted(self):
        with self.assertRaises(DBAPIError), geo_data.read_connection() as connection:
            connection.execute(text("INSERT INTO ruian_obce VALUES(1,'test')"))
        with self.assertRaises(ValueError):
            geo_data.statistics("population); DROP TABLE users; --")

    def test_bare_parent_parcel_number_returns_existing_subparcels(self):
        with self.db.begin() as connection:
            connection.execute(text("INSERT INTO ruian_ku VALUES (722120, 'Bolevec')"))
            connection.execute(
                text(
                    "INSERT INTO ruian_parcely VALUES ('1', 722120, '438/1', 'zahrada', 500), ('2', 722120, '438/2', 'zahrada', 700)"
                )
            )
        result = geo_data.prevalidate_parcel("438", kod_ku=722120)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(
            [candidate["cislo_parcely"] for candidate in result["candidates"]], ["438/1", "438/2"]
        )
        self.assertIn("Upřesněte celé číslo parcely", result["message"])
