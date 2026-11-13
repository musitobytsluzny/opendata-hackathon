"""ETL integration tests in disposable schemas; no external downloads."""

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Point, Polygon
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from etl import cli, db, seed
from etl.downloaders.vuv import fetch_and_load_vuv


class IntegrityTests(unittest.TestCase):
    def test_vuv_import_maps_recurrence_and_missing_optional_type(self):
        seed.seed_lookups()
        frame = gpd.GeoDataFrame(
            [
                {
                    "PERIODICIT": 100,
                    "NAZEV_TOKU": "Fixture river",
                    "geometry": Polygon([(13, 49), (14, 49), (14, 50), (13, 49)]),
                }
            ],
            geometry="geometry",
            crs=4326,
        )
        with tempfile.TemporaryDirectory() as directory:
            shape = Path(directory) / "fixture.shp"
            shape.touch()
            with (
                patch("etl.downloaders.vuv.download_file"),
                patch("etl.downloaders.vuv.unzip_file", return_value=Path(directory)),
                patch("etl.downloaders.vuv.gpd.read_file", return_value=frame),
            ):
                self.assertEqual(fetch_and_load_vuv(), 1)
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT q_stupen, aktivni_zona, GeometryType(geom) FROM vuv_zaplavova_uzemi")
            ).one()
            self.assertEqual(tuple(row), ("Q100", False, "MULTIPOLYGON"))

    def setUp(self):
        self.schema = "etl_test_" + uuid.uuid4().hex
        self.admin = create_engine(db.DATABASE_URL)
        with self.admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            self.accounts = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM public.users), (SELECT count(*) FROM public.profiles)"
                )
            ).one()
        self.engine = create_engine(
            db.DATABASE_URL, connect_args={"options": f"-csearch_path={self.schema},public"}
        )
        self.engine_patch = patch.object(db, "_engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.cleanup)
        seed.seed_schema()

    def cleanup(self):
        self.engine_patch.stop()
        self.engine.dispose()
        with self.admin.begin() as connection:
            accounts = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM public.users), (SELECT count(*) FROM public.profiles)"
                )
            ).one()
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.admin.dispose()
        self.assertEqual(tuple(accounts), tuple(self.accounts), "ETL changed API accounts")

    def counts(self):
        with self.engine.connect() as connection:
            return {
                table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
                for table in db.TABLES
            }

    def test_seed_is_repeatable_with_valid_geometry_and_foreign_keys(self):
        seed.run_seed()
        first = self.counts()
        seed.run_seed()
        self.assertEqual(first, self.counts())
        self.assertEqual(first["ruian_parcely"], 3)
        self.assertEqual(first["osm_poi"], 4)
        with self.engine.connect() as connection:
            for table in ("ruian_obce", "ruian_ku", "ruian_parcely", "osm_poi"):
                invalid = connection.scalar(
                    text(
                        f"SELECT count(*) FROM {table} WHERE NOT ST_IsValid(geom) OR ST_SRID(geom) <> 4326"
                    )
                )
                self.assertEqual(invalid, 0)
            kinds = (
                connection.execute(text("SELECT DISTINCT data_kind FROM etl_dataset_status"))
                .scalars()
                .all()
            )
            self.assertEqual(set(kinds), {"reference", "demo"})
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(text("UPDATE ruian_parcely SET kod_ku=-1"))

    def test_prevalidation_known_parcel_and_location_without_data(self):
        seed.run_seed()
        with self.engine.connect() as connection:
            parcel = connection.scalar(text("SELECT fn_prevalidate_parcel(722618, '1234/2')"))
            self.assertEqual(parcel["parcel"]["id"], "722618-1234/2")
            self.assertTrue(parcel["flood_risk"]["in_q20"])
            self.assertTrue(parcel["nature_protection"]["in_protected_area"])
            self.assertEqual(parcel["data_sources"]["ruian_parcely"]["kind"], "demo")
            outside = connection.scalar(text("SELECT fn_prevalidate_point(0, 0)"))
            self.assertIsNone(outside["location_hierarchy"]["municipality_code"])
            self.assertIsNone(outside["demographics"]["population"])
            missing = connection.scalar(text("SELECT fn_prevalidate_parcel(1, 'missing')"))
            self.assertEqual(missing["status"], "not_found")

    def test_failure_rolls_back_complete_seed(self):
        with patch.object(seed, "seed_osm_poi", side_effect=RuntimeError("injected failure")):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                seed.run_seed()
        self.assertTrue(all(count == 0 for count in self.counts().values()))

    def test_all_does_not_truncate_or_fall_back_to_demo_on_failure(self):
        seed.run_seed()
        original = self.counts()
        with patch.object(cli, "load_ruian_from_local_or_remote", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "no demo fallback"):
                cli.main(["--all"])
        self.assertEqual(original, self.counts())

    def test_demo_and_external_data_are_not_mixed(self):
        seed.run_seed()
        gdf = gpd.GeoDataFrame(
            [{"id": "real-poi", "category": "education", "geom": Point(13.4, 49.7)}],
            geometry="geom",
            crs=4326,
        )
        with self.assertRaisesRegex(ValueError, "Refusing to mix"):
            db.save_geodataframe(gdf, "osm_poi")

    def test_crs_required_and_polygon_promoted_to_multipolygon(self):
        polygon = Polygon([(13, 49), (14, 49), (14, 50), (13, 49)])
        source = gpd.GeoDataFrame(
            [{"kod_obce": 123456, "nazev": "Fixture", "GEOMETRY": polygon}], geometry="GEOMETRY"
        )
        with self.assertRaisesRegex(ValueError, "Missing CRS"):
            db.standardize_gdf(source)
        source = source.set_crs(4326)
        db.save_geodataframe(source, "ruian_obce")
        db.save_geodataframe(source, "ruian_obce")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT GeometryType(geom) FROM ruian_obce")), "MULTIPOLYGON"
            )
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM ruian_obce")), 1)

    def test_replace_and_api_table_writes_are_rejected(self):
        source = gpd.GeoDataFrame([{"geom": Point(13, 49)}], geometry="geom", crs=4326)
        with self.assertRaises(ValueError):
            db.save_geodataframe(source, "osm_poi", if_exists="replace")
        with self.assertRaisesRegex(ValueError, "Not an ETL-managed table"):
            db.save_dataframe(source, "users")
