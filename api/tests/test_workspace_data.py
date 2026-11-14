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
                "CREATE TABLE facility_poi(id text,name text,category text,amenity text,publisher text,source_url text,geom geometry(Point,4326))",
                "CREATE TABLE municipality_status(kod_obce int,status_kod int,status_name text)",
                "CREATE VIEW all_facility_poi AS SELECT 'poi:'||id AS place_id,name,category,'pharmacy'::text AS amenity,'OpenStreetMap'::text AS publisher,'https://www.openstreetmap.org/'::text AS source_url,geom,name AS search_text FROM osm_poi UNION ALL SELECT 'facility:'||id,name,category,amenity,publisher,source_url,geom,name FROM facility_poi",
                "INSERT INTO okresy VALUES('test','Klatovy')",
                "INSERT INTO ruian_obce VALUES(1,'test','Žlutá',ST_SetSRID(ST_Point(13,49),4326)),(2,'test','Sever',ST_SetSRID(ST_Point(13,50),4326))",
                "INSERT INTO csu_demografie_obce VALUES(1,100,20,10),(2,300,90,30)",
                "INSERT INTO osm_poi VALUES('near','Lékárna','healthcare',ST_SetSRID(ST_Point(13.001,49),4326)),('far','Daleko','healthcare',ST_SetSRID(ST_Point(13.1,49),4326))",
            ]:
                connection.execute(text(statement))

    def test_foot_context_checks_middle_of_route_and_preserves_unknowns(self):
        from app.services import route_context

        with self.db.begin() as connection:
            for statement in [
                "INSERT INTO ruian_obce VALUES(3,'test','Škola',ST_SetSRID(ST_Point(13.01,49),4326))",
                "CREATE TABLE vuv_zaplavova_uzemi(id text,q_stupen text,aktivni_zona bool,geom geometry(Geometry,4326))",
                "INSERT INTO vuv_zaplavova_uzemi VALUES('middle','Q100',true,ST_MakeEnvelope(13.004,48.9999,13.006,49.0001,4326))",
                "INSERT INTO etl_dataset_status(table_name,data_kind,row_count) VALUES('vuv_zaplavova_uzemi','external',1),('osm_route_features','external',1)",
                "CREATE TABLE osm_route_features(id text,kind text,highway text,tags_json jsonb,geom geometry(Geometry,4326))",
                "INSERT INTO osm_route_features VALUES('road','road_segment','residential','{}',ST_GeomFromText('LINESTRING(13.004 49,13.006 49)',4326))",
            ]:
                connection.execute(text(statement))
        route = {
            "distance": 800,
            "duration": 600,
            "geometry": {"type": "LineString", "coordinates": [[13, 49], [13.01, 49]]},
        }
        with patch.object(route_context, "foot_route", return_value=route):
            answer = route_context.analyse_route_context("obec:1", "obec:3")
        rows = {r["check"]: r for r in answer["result"]["rows"]}
        self.assertEqual(rows["Aktivní záplavové zóny"]["mapped_count"], 1)
        self.assertIsNone(rows["Mapované vodní toky"]["mapped_count"])
        self.assertEqual(rows["Úseky bez údaje o chodníku"]["mapped_count"], 1)
        self.assertEqual(rows["Úseky se značkou sidewalk=no/none"]["mapped_count"], 0)
        self.assertEqual(answer["route"]["mode"], "foot")
        self.assertEqual(answer["result"]["view"], "map")
        self.assertIn("není důkaz chybějícího chodníku", answer["result"]["note"])
        self.assertTrue(
            any(f["id"] == "route-context:flood:middle" for f in answer["result"]["features"])
        )

    def test_foot_provider_uses_foot_profile_and_never_driving_fallback(self):
        from app.services import route_context

        real_client = httpx.Client
        requests = []

        def failed(request):
            requests.append(str(request.url))
            return httpx.Response(503)

        with patch.object(
            route_context.httpx,
            "Client",
            side_effect=lambda **kw: real_client(**kw, transport=httpx.MockTransport(failed)),
        ):
            with self.assertRaises(HTTPException) as error:
                route_context.foot_route("13,49;13.01,49", -1)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(len(requests), 1)
        self.assertIn("/routed-foot/route/v1/foot/", requests[0])

    def test_amenity_municipality_is_spatial_not_a_word_in_institution_name(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ruian_obce SET nazev='Žihle',geom=ST_MakeEnvelope(13,48.99,13.01,49.01,4326) WHERE kod_obce=1"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('inside','Masarykova základní škola v Žihli','education','primary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.001,49),4326)),('outside','Základní škola Žihle','education','primary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.1,49),4326))"
                )
            )
        answer = geo_data.search_amenities("základní škola", obec="Žihle")
        self.assertEqual([row["id"] for row in answer["result"]["rows"]], ["facility:inside"])

    def test_amenity_category_filters_results_and_unknown_categories_stay_empty(self):
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('school','Základní škola','education','primary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.001,49),4326)),('clinic','Základní škola','healthcare','doctors','OpenStreetMap','https://osm.org/',ST_SetSRID(ST_Point(13.002,49),4326))"
                )
            )
        schools = geo_data.search_amenities("základní škola", kategorie="školství")
        self.assertEqual([row["id"] for row in schools["result"]["rows"]], ["facility:school"])
        sports = geo_data.search_amenities("sportoviště", kategorie="sportoviště")
        self.assertEqual(sports["result"]["rows"], [])
        self.assertIn("není v načtených datech podporována", sports["result"]["note"])

    def test_balanced_parcels_measures_both_distances_and_enforces_scope(self):
        from app.services.balanced_parcels import balanced_parcels

        with self.db.begin() as connection:
            for statement in [
                "UPDATE ruian_obce SET geom=ST_SetSRID(ST_Point(13.02,49),4326) WHERE kod_obce=2",
                "CREATE TABLE ruian_parcely(id text,cislo_parcely text,kod_ku int,vymera_m2 float,druh_pozemku text,geom geometry(Polygon,4326))",
                "INSERT INTO ruian_parcely VALUES('balanced','1',1,100,'zahrada',ST_MakeEnvelope(13.0099,48.9999,13.0101,49.0001,4326)),('unequal','2',1,100,'zahrada',ST_MakeEnvelope(13.001,48.9999,13.0012,49.0001,4326)),('outside','3',1,100,'zahrada',ST_MakeEnvelope(13.0099,49.1,13.0101,49.1002,4326))",
            ]:
                connection.execute(text(statement))
        answer = balanced_parcels("obec:1", "obec:2", 2000, 25, 5)
        rows = answer["result"]["rows"]
        self.assertEqual([r["id"] for r in rows], ["parcela:balanced", "parcela:unequal"])
        self.assertTrue(rows[0]["within_tolerance"])
        self.assertFalse(rows[1]["within_tolerance"])
        self.assertGreater(rows[0]["distance_a_m"], 700)
        self.assertLess(rows[0]["difference_m"], 0.01)
        self.assertEqual(answer["search"]["searched_parcels"], 2)
        self.assertFalse(answer["search"]["global_optimum"])
        self.assertEqual(answer["result"]["features"][-1]["geometry"]["type"], "Polygon")
        whole = balanced_parcels("obec:1", "obec:2", search_all=True)
        self.assertEqual(whole["search"]["searched_parcels"], 3)
        self.assertEqual(whole["search"]["scope"], "loaded_parcels")
        self.assertIsNone(whole["search"]["radius_m"])
        self.assertIn("parcela:outside", [row["id"] for row in whole["result"]["rows"]])
        exact = balanced_parcels("obec:1", "obec:2", 2000, 0, 5)
        self.assertTrue(
            all(not r["within_tolerance"] for r in exact["result"]["rows"] if r["difference_m"] > 0)
        )
        with self.assertRaises(HTTPException):
            balanced_parcels("obec:1", "obec:1")

    def test_map_layers_clip_long_features_to_requested_area(self):
        import json

        with self.db.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE zabaged_vodni_toky(id text,jmeno text,geom geometry(Geometry,4326))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO zabaged_vodni_toky VALUES('long','Tok',ST_GeomFromText('LINESTRING(12 49,14 49)',4326))"
                )
            )
        answer = workspace.load_map_layer("water", "obec:1", 500, 10)["result"]
        self.assertLess(len(json.dumps(answer)), 5000)
        self.assertIn("oříznuté", answer["note"])
        for lon, _ in answer["features"][0]["geometry"]["coordinates"]:
            self.assertGreater(lon, 12.99)
            self.assertLess(lon, 13.01)

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

    def test_nearest_cities_use_official_status_and_exclude_origin(self):
        from app.services import life_data

        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ruian_obce VALUES(3,'test','Blízká vesnice',ST_SetSRID(ST_Point(13.01,49),4326)),(4,'test','Blízké město',ST_SetSRID(ST_Point(13.02,49),4326))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO municipality_status VALUES(1,3,'Město'),(2,3,'Město'),(3,2,'Obec'),(4,3,'Město')"
                )
            )
            connection.execute(
                text("INSERT INTO csu_demografie_obce VALUES(3,50,10,5),(4,110,10,5)")
            )
        cities = life_data.nearest_municipalities("obec:1", 3, 200000, True)["result"]["rows"]
        self.assertEqual([r["id"] for r in cities], ["obec:4", "obec:2"])
        villages = life_data.nearest_municipalities("obec:1", 1, 200000)["result"]["rows"]
        self.assertEqual(villages[0]["id"], "obec:3")
        similar = life_data.nearest_municipalities("obec:1", 5, 200000, False, 20)["result"]["rows"]
        self.assertEqual([r["id"] for r in similar], ["obec:4"])

    def test_hospitals_are_not_replaced_by_closer_doctors_and_missing_services_are_null(self):
        from app.services import life_data

        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('doctor','Ordinace','healthcare','doctors','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.0001,49),4326)),('hospital','Nemocnice','healthcare','hospital','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.002,49),4326)),('school','Škola','education','school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.003,49),4326))"
                )
            )
        hospitals = life_data.nearby_facilities("obec:1", "hospital", 1000, 5)["result"]
        self.assertEqual([r["id"] for r in hospitals["rows"]], ["facility:hospital"])
        self.assertEqual(hospitals["rows"][0]["publisher"], "ČÚZK")
        with geo_data.read_connection() as connection:
            self.assertEqual(
                workspace.resolve(connection, "facility:hospital")["name"], "Nemocnice"
            )
        summary = life_data.accessibility_summary("obec:1", 1000)["result"]["rows"]
        kindergarten = next(row for row in summary if row["service"] == "Mateřské školy")
        self.assertIsNone(kindergarten["distance_m"])
        self.assertIsNone(kindergarten["name"])
        school = next(row for row in summary if row["service"] == "Školy")
        self.assertEqual(school["name"], "Škola")
        self.assertFalse(
            life_data.facility_alternatives("facility:hospital", 1000, 5)["result"]["rows"]
        )
        nearby = workspace.search_places("Nemocnice", "poi")["result"]["rows"]
        self.assertEqual(nearby[0]["id"], "facility:hospital")

    def test_driving_candidates_are_ranked_by_actual_route_not_straight_line(self):
        from app.services import life_data

        real_client = httpx.Client

        def handler(request):
            self.assertIn("/table/v1/driving/", str(request.url))
            return httpx.Response(
                200, json={"code": "Ok", "distances": [[40000, 10000]], "durations": [[100, 600]]}
            )

        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ruian_obce VALUES(3,'test','Třetí',ST_SetSRID(ST_Point(13.02,49),4326))"
                )
            )
        with patch.object(
            life_data.httpx,
            "Client",
            side_effect=lambda **kwargs: real_client(
                **kwargs, transport=httpx.MockTransport(handler)
            ),
        ):
            answer = life_data.rank_driving_candidates("obec:1", ["obec:2", "obec:3"])["result"]
            timed = life_data.rank_driving_candidates("obec:1", ["obec:2", "obec:3"], "duration")
        self.assertEqual(timed["result"]["rows"][0]["id"], "obec:2")
        self.assertEqual(timed["ordering"], "duration")
        self.assertIn("času jízdy", timed["result"]["note"])
        self.assertEqual(answer["rows"][0]["id"], "obec:3")
        self.assertEqual(answer["rows"][0]["distance_km"], 10)
        self.assertIn("Pouze zadaní kandidáti", answer["note"])

    def test_public_transport_returns_distinct_stops_not_repeated_platforms(self):
        from app.services import life_data

        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('a','Náměstí','transport','public_transport_stop','PMDP','https://pmdp.cz/',ST_SetSRID(ST_Point(13.001,49),4326)),('b','Náměstí','transport','public_transport_stop','PMDP','https://pmdp.cz/',ST_SetSRID(ST_Point(13.002,49),4326)),('c','Škola','transport','public_transport_stop','PMDP','https://pmdp.cz/',ST_SetSRID(ST_Point(13.003,49),4326))"
                )
            )
        rows = life_data.nearby_facilities("obec:1", "public_transport", 1000, 3)["result"]["rows"]
        self.assertEqual([r["name"] for r in rows], ["Náměstí", "Škola"])
        alternatives = life_data.facility_alternatives("facility:a", 1000, 3)["result"]["rows"]
        self.assertEqual([r["name"] for r in alternatives], ["Škola"])

    def test_school_acronym_search_returns_geometry_and_deduplicates_same_campus(self):
        from app.services.geo_data import search_amenities

        name = (
            "Vyšší odborná škola a Střední průmyslová škola elektrotechnická, Plzeň, Koterovská 85"
        )
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('college',:name,'education','college','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13,49),4326)),('secondary',:name,'education','secondary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.00005,49),4326))"
                ),
                {"name": name},
            )
        found = workspace.search_places("VOŠ a SPŠE Plzeň", "poi")["result"]
        self.assertEqual(len(found["rows"]), 1)
        self.assertTrue(found["rows"][0]["id"].startswith("facility:"))
        self.assertEqual(found["features"][0]["geometry"]["type"], "Point")
        self.assertEqual(search_amenities("VOŠ a SPŠE Plzeň")["result"]["view"], "map")
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('remote',:name,'education','secondary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.03,49),4326))"
                ),
                {"name": name},
            )
        self.assertEqual(
            len(workspace.search_places("VOŠ a SPŠE Plzeň", "poi")["result"]["rows"]), 2
        )

    def test_nearby_schools_exclude_origin_across_sources_but_keep_other_nearby_institutions(self):
        from app.services.life_data import nearby_facilities

        name = (
            "Vyšší odborná škola a Střední průmyslová škola elektrotechnická, Plzeň, Koterovská 85"
        )
        with self.db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO facility_poi VALUES('origin',:name,'education','secondary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13,49),4326)),('university','Metropolitní univerzita Praha, Univerzitní středisko','education','university','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.001,49),4326)),('easy','Základní škola Easy Start','education','primary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.003,49),4326)),('twenty','20. základní škola Plzeň, Brojova 13','education','primary_school','ČÚZK','https://cuzk.gov.cz/',ST_SetSRID(ST_Point(13.006,49),4326))"
                ),
                {"name": name},
            )
            connection.execute(
                text(
                    "INSERT INTO osm_poi VALUES('own','VOŠ a SPŠE Plzeň','education',ST_SetSRID(ST_Point(13.0015,49),4326)),('twenty','20. Základní škola','education',ST_SetSRID(ST_Point(13.0061,49),4326))"
                )
            )
            # The fixture view labels legacy rows as pharmacies; reflect these two actual school types.
            connection.execute(
                text(
                    "CREATE OR REPLACE VIEW all_facility_poi AS SELECT 'poi:'||id AS place_id,name,category,CASE WHEN category='education' THEN 'school' ELSE 'pharmacy' END::text AS amenity,'OpenStreetMap'::text AS publisher,'https://www.openstreetmap.org/'::text AS source_url,geom,name AS search_text FROM osm_poi UNION ALL SELECT 'facility:'||id,name,category,amenity,publisher,source_url,geom,name FROM facility_poi"
                )
            )
        rows = nearby_facilities("facility:origin", "school", 5000, 3)["result"]["rows"]
        self.assertEqual(
            [row["id"] for row in rows], ["facility:university", "facility:easy", "facility:twenty"]
        )
