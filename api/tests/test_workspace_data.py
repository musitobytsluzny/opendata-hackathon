"""Real PostGIS measurements in disposable schemas; routing is deterministic and offline."""

import unittest
import uuid
from unittest.mock import patch

import httpx
from app.database.connection import engine, settings
from app.services import geo_data
from app.services import workspace_data as workspace
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.schema = "workspace_test_" + uuid.uuid4().hex
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.db = create_engine(
            make_url(settings.database_url).set(drivername="postgresql+psycopg"),
            connect_args={"options": f"-csearch_path={self.schema},public"},
        )
        self.engine_patch = patch.object(geo_data, "engine", self.db)
        self.engine_patch.start()
        self.addCleanup(self.cleanup)
        with self.db.begin() as connection:
            for statement in [
                "CREATE TABLE etl_dataset_status(table_name text, data_kind text, row_count int, loaded_at timestamptz DEFAULT now())",
                "CREATE TABLE okresy(kod_okresu text,nazev text)",
                "CREATE TABLE ruian_obce(kod_obce int,kod_okresu text,nazev text,geom geometry(Geometry,4326))",
                "CREATE TABLE csu_demografie_obce(kod_obce int,pocet_obyvatel int,seniori_65_plus int,deti_0_14 int)",
                "CREATE TABLE osm_poi(id text,name text,category text,geom geometry(Point,4326))",
                "INSERT INTO okresy VALUES('test','Klatovy')",
                "INSERT INTO ruian_obce VALUES(1,'test','Žlutá',ST_SetSRID(ST_Point(13,49),4326)),(2,'test','Sever',ST_SetSRID(ST_Point(13,50),4326))",
                "INSERT INTO csu_demografie_obce VALUES(1,100,20,10),(2,300,90,30)",
                "INSERT INTO osm_poi VALUES('near','Lékárna','healthcare',ST_SetSRID(ST_Point(13.001,49),4326)),('far','Daleko','healthcare',ST_SetSRID(ST_Point(13.1,49),4326))",
            ]:
                connection.execute(text(statement))

    def cleanup(self):
        self.engine_patch.stop()
        self.db.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def test_search_is_accent_insensitive_and_literal(self):
        found = workspace.search_places("zluta")["result"]
        self.assertEqual(found["rows"][0]["id"], "obec:1")
        self.assertFalse(workspace.search_places("%_")["result"]["rows"])
        with self.assertRaises(HTTPException):
            workspace.place_geometry("users:1")

    def test_distance_is_geodesic_not_an_estimate(self):
        result = workspace.measure_distance("obec:1", "obec:2")["result"]
        distance = result["rows"][0]["distance_m"]
        self.assertGreater(distance, 111000)
        self.assertLess(distance, 112000)
        self.assertTrue(result["features"][-1]["properties"]["measurement"])
        self.assertIn("km", result["features"][-1]["properties"]["label"])

    def test_nearby_radius_and_ranking_use_measured_distance(self):
        rows = workspace.nearby_places("obec:1", "healthcare", 100, 10)["result"]["rows"]
        self.assertEqual([row["id"] for row in rows], ["poi:near"])
        self.assertGreater(rows[0]["distance_m"], 70)
        self.assertLess(rows[0]["distance_m"], 80)

    def test_municipality_rank_uses_real_values_and_district_filter(self):
        rows = workspace.municipality_statistics("seniors_pct", "Klatovy", 1)["result"]["rows"]
        self.assertEqual(rows[0]["id"], "obec:2")
        self.assertEqual(rows[0]["value"], 30)
        self.assertFalse(
            workspace.municipality_statistics("population", "missing")["result"]["rows"]
        )

    def test_route_failure_does_not_fall_back_to_a_guessed_distance(self):
        real_client = httpx.Client

        def failed(request):
            return httpx.Response(503)

        with patch.object(
            workspace.httpx,
            "Client",
            side_effect=lambda **kwargs: real_client(
                **kwargs, transport=httpx.MockTransport(failed)
            ),
        ):
            with self.assertRaises(HTTPException) as error:
                workspace.find_route("obec:1", "obec:2")
        self.assertEqual(error.exception.status_code, 503)

    def test_route_has_computed_distance_geometry_and_driving_provenance(self):
        real_client = httpx.Client

        def handler(request):
            self.assertIn("/driving/13,49;13,50", str(request.url))
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 150000,
                            "duration": 7200,
                            "geometry": {"type": "LineString", "coordinates": [[13, 49], [13, 50]]},
                        }
                    ],
                },
            )

        with patch.object(
            workspace.httpx,
            "Client",
            side_effect=lambda **kwargs: real_client(
                **kwargs, transport=httpx.MockTransport(handler)
            ),
        ):
            result = workspace.find_route("obec:1", "obec:2")["result"]
        self.assertEqual(result["rows"][0]["distance_km"], 150)
        self.assertEqual(result["rows"][0]["duration_min"], 120)
        self.assertEqual(result["features"][-1]["geometry"]["type"], "LineString")
        self.assertIn("automobilový", result["note"])

    def test_click_on_parcel_boundary_preserves_ambiguity(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE ruian_parcely(id text,cislo_parcely text,kod_ku int,vymera_m2 int,druh_pozemku text,geom geometry(Polygon,4326))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ruian_parcely VALUES('a','12',1,100,'Orná půda',ST_MakeEnvelope(13,49,13.01,49.01,4326)),('b','13',1,200,'Zahrada',ST_MakeEnvelope(13.01,49,13.02,49.01,4326))"
                )
            )
        result = workspace.parcel_at_point(49.005, 13.01)["result"]
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(len(result["features"]), 2)
        self.assertEqual({row["area_m2"] for row in result["rows"]}, {100, 200})

    def test_graphic_layer_reports_truncation_and_returns_actual_polygons(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE vuv_zaplavova_uzemi(id int,tok_nazev text,geom geometry(Polygon,4326))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO vuv_zaplavova_uzemi VALUES(1,'A',ST_MakeEnvelope(13,49,13.001,49.001,4326)),(2,'B',ST_MakeEnvelope(13.001,49,13.002,49.001,4326))"
                )
            )
        result = workspace.load_map_layer("flood", "obec:1", 500, 1)["result"]
        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["geometry"]["type"], "Polygon")
        self.assertIn("omezený na 1", result["note"])

    def test_area_is_computed_from_boundaries_without_demographic_data(self):
        with self.db.begin() as connection:
            connection.execute(text("DELETE FROM csu_demografie_obce"))
            connection.execute(
                text(
                    "UPDATE ruian_obce SET geom=ST_MakeEnvelope(13,49,13.01,49.01,4326) WHERE kod_obce=1"
                )
            )
        data = workspace.municipality_statistics("area_m2", limit=1)["result"]
        self.assertEqual(data["rows"][0]["id"], "obec:1")
        self.assertGreater(data["rows"][0]["value"], 700000)
        self.assertLess(data["rows"][0]["value"], 900000)
        self.assertTrue(data["columns"][-1]["additive"])
        self.assertEqual(data["columns"][-1]["unit"], "m²")
