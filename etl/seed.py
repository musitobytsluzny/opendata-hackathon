"""Seed script for OpenData Geo MCP.

Populates PostgreSQL/PostGIS with realistic foundational datasets for Plzeň and surroundings
using a hybrid relational-spatial model (lookups, administrative hierarchy, parcels, and spatial layers).
"""

import logging

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from sqlalchemy import text

from etl.config import ETL_DIR, TARGET_CRS
from etl.db import (
    TABLES,
    execute_sql,
    execute_sql_file,
    save_dataframe,
    save_geodataframe,
    transaction,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def seed_schema():
    """Apply schema and prevalidation functions."""
    logger.info("Applying database schemas and spatial functions...")
    with transaction():
        execute_sql_file(ETL_DIR / "sql" / "001_schema.sql")
        execute_sql_file(ETL_DIR / "sql" / "003_facilities.sql")
        execute_sql_file(ETL_DIR / "sql" / "002_views.sql")


def drop_tables():
    """Safely drop all tables with CASCADE for a clean schema reset."""
    logger.info("Dropping existing tables for a clean schema migration...")
    execute_sql("DROP VIEW IF EXISTS all_facility_poi")
    execute_sql(f"DROP TABLE IF EXISTS {', '.join(TABLES)}, etl_dataset_status")


def truncate_tables():
    """Explicit reset only; never called by ordinary imports."""
    execute_sql(f"TRUNCATE {', '.join(TABLES)}, etl_dataset_status RESTART IDENTITY")


def seed_lookups():
    """Seed normalized lookup tables with business rules."""
    logger.info("Seeding relational lookups (ciselniky)...")

    # 1. Druhy pozemků
    druhy_pozemku = [
        {
            "id": 2,
            "kod": "ORNA_PUDA",
            "nazev": "Orná půda",
            "patri_do_zpf": True,
            "je_stavebni_plocha": False,
            "stavebni_poznamka": "Nutné vynětí ze ZPF s poplatkem a souhlasem OŽP",
        },
        {
            "id": 7,
            "kod": "TTP",
            "nazev": "Trvalý travní porost",
            "patri_do_zpf": True,
            "je_stavebni_plocha": False,
            "stavebni_poznamka": "Nutné vynětí ze ZPF, regulace odtoku vody",
        },
        {
            "id": 13,
            "kod": "ZASTAVENA_PLOCHA",
            "nazev": "Zastavěná plocha a nádvoří",
            "patri_do_zpf": False,
            "je_stavebni_plocha": True,
            "stavebni_poznamka": "Určeno k zástavbě, stavba povolena dle územního plánu",
        },
        {
            "id": 14,
            "kod": "OSTATNI_PLOCHA",
            "nazev": "Ostatní plocha",
            "patri_do_zpf": False,
            "je_stavebni_plocha": True,
            "stavebni_poznamka": "Využití dle specifického způsobu (komerce, sport, zeleň)",
        },
    ]
    save_dataframe(pd.DataFrame(druhy_pozemku), "ciselnik_druh_pozemku")

    # 2. Povodňová rizika
    povodnova_rizika = [
        {
            "kod": "Q5",
            "navratnost_let": 5,
            "zavaznost": "KRITICKÉ",
            "stavebni_omezeni": "Extrémní riziko záplavy každých 5 let. Zákaz umisťování obytných budov.",
        },
        {
            "kod": "Q20",
            "navratnost_let": 20,
            "zavaznost": "VYSOKÉ",
            "stavebni_omezeni": "Vysoké povodňové riziko. Stavba možná jen s náročnými technickými opatřeními.",
        },
        {
            "kod": "Q100",
            "navratnost_let": 100,
            "zavaznost": "STŘEDNÍ",
            "stavebni_omezeni": "Stoletá voda. Vyžaduje stanovisko správce toku a vodoprávního úřadu.",
        },
        {
            "kod": "Q500",
            "navratnost_let": 500,
            "zavaznost": "NÍZKÉ",
            "stavebni_omezeni": "Zbytkové riziko pětisetleté vody.",
        },
    ]
    save_dataframe(pd.DataFrame(povodnova_rizika), "ciselnik_povodnove_riziko")

    # 3. Kategorie ochrany přírody
    kategorie_ochrany = [
        {
            "kod": "NP",
            "nazev": "Národní park",
            "stupen_prisnosti": 1,
            "stavebni_omezeni": "Přísný zákaz výstavby mimo schválené zastavitelné území obcí.",
        },
        {
            "kod": "NPR",
            "nazev": "Národní přírodní rezervace",
            "stupen_prisnosti": 1,
            "stavebni_omezeni": "Úplný zákaz stavební činnosti.",
        },
        {
            "kod": "CHKO",
            "nazev": "Chráněná krajinná oblast",
            "stupen_prisnosti": 2,
            "stavebni_omezeni": "Regulace výšky, sklonu střech a vzhledu staveb. Souhlas Správy CHKO.",
        },
        {
            "kod": "PRIRODNI_PARK",
            "nazev": "Přírodní park",
            "stupen_prisnosti": 3,
            "stavebni_omezeni": "Ochrana krajinného rázu, stavby musí respektovat ráz zástavby.",
        },
        {
            "kod": "PP",
            "nazev": "Přírodní památka",
            "stupen_prisnosti": 2,
            "stavebni_omezeni": "Zákaz činností měnících dochovaný stav památky.",
        },
    ]
    save_dataframe(pd.DataFrame(kategorie_ochrany), "ciselnik_kategorie_ochrany")


def seed_administrative_hierarchy():
    """Seed Kraje, Okresy, and Katastrální území."""
    logger.info("Seeding administrative hierarchy (kraje, okresy, ku)...")

    # Kraje
    save_dataframe(pd.DataFrame([{"kod_kraje": "43", "nazev": "Plzeňský kraj"}]), "kraje")

    # Okresy
    okresy_data = [
        {"kod_okresu": "3401", "kod_kraje": "43", "nazev": "Domažlice"},
        {"kod_okresu": "3404", "kod_kraje": "43", "nazev": "Klatovy"},
        {"kod_okresu": "3406", "kod_kraje": "43", "nazev": "Plzeň-jih"},
        {"kod_okresu": "3407", "kod_kraje": "43", "nazev": "Plzeň-sever"},
        {"kod_okresu": "3405", "kod_kraje": "43", "nazev": "Plzeň-město"},
        {"kod_okresu": "3408", "kod_kraje": "43", "nazev": "Rokycany"},
        {"kod_okresu": "3410", "kod_kraje": "43", "nazev": "Tachov"},
    ]
    save_dataframe(pd.DataFrame(okresy_data), "okresy")


def seed_ruian_obce():
    """Seed fallback municipalities if real RÚIAN isn't downloaded yet."""
    logger.info("Seeding ruian_obce...")
    data = [
        {
            "kod_obce": 554791,
            "kod_okresu": "3405",
            "nazev": "Plzeň",
            "okres": "Plzeň-město",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.30, 49.70),
                            (13.45, 49.70),
                            (13.45, 49.80),
                            (13.30, 49.80),
                            (13.30, 49.70),
                        ]
                    )
                ]
            ),
        },
        {
            "kod_obce": 555771,
            "kod_okresu": "3404",
            "nazev": "Klatovy",
            "okres": "Klatovy",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.25, 49.35),
                            (13.35, 49.35),
                            (13.35, 49.43),
                            (13.25, 49.43),
                            (13.25, 49.35),
                        ]
                    )
                ]
            ),
        },
        {
            "kod_obce": 559717,
            "kod_okresu": "3408",
            "nazev": "Rokycany",
            "okres": "Rokycany",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.55, 49.70),
                            (13.65, 49.70),
                            (13.65, 49.78),
                            (13.55, 49.78),
                            (13.55, 49.70),
                        ]
                    )
                ]
            ),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "ruian_obce", if_exists="append", geom_col="geom")


def seed_ruian_ku():
    """Seed katastrální území (KÚ) linked to municipalities."""
    logger.info("Seeding ruian_ku...")
    data = [
        {
            "kod_ku": 722618,
            "kod_obce": 554791,
            "nazev": "Bolevec",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.350, 49.765),
                            (13.390, 49.765),
                            (13.390, 49.800),
                            (13.350, 49.800),
                            (13.350, 49.765),
                        ]
                    )
                ]
            ),
        },
        {
            "kod_ku": 722740,
            "kod_obce": 554791,
            "nazev": "Plzeň",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.360, 49.735),
                            (13.410, 49.735),
                            (13.410, 49.765),
                            (13.360, 49.765),
                            (13.360, 49.735),
                        ]
                    )
                ]
            ),
        },
        {
            "kod_ku": 666017,
            "kod_obce": 555771,
            "nazev": "Klatovy",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.270, 49.370),
                            (13.330, 49.370),
                            (13.330, 49.410),
                            (13.270, 49.410),
                            (13.270, 49.370),
                        ]
                    )
                ]
            ),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "ruian_ku", if_exists="append", geom_col="geom")


def seed_ruian_parcely():
    """Seed parcels with relational FKs to KÚ, Obec and Druh pozemku."""
    logger.info("Seeding ruian_parcely...")
    data = [
        {
            "id": "722618-1234/2",
            "kod_ku": 722618,
            "kod_obce": 554791,
            "cislo_parcely": "1234/2",
            "druh_pozemku_id": 7,  # TTP (ZPF=True, Stavební=False)
            "druh_pozemku": "trvalý travní porost",
            "zpusob_vyuziti": "zemědělský půdní fond",
            "vymera_m2": 2450,
            "geom": Polygon(
                [
                    (13.3750, 49.7750),
                    (13.3765, 49.7750),
                    (13.3765, 49.7762),
                    (13.3750, 49.7762),
                    (13.3750, 49.7750),
                ]
            ),
        },
        {
            "id": "722618-567/1",
            "kod_ku": 722618,
            "kod_obce": 554791,
            "cislo_parcely": "567/1",
            "druh_pozemku_id": 13,  # Zastavěná plocha (Stavební=True)
            "druh_pozemku": "zastavěná plocha a nádvoří",
            "zpusob_vyuziti": "bydlení",
            "vymera_m2": 820,
            "geom": Polygon(
                [
                    (13.3680, 49.7820),
                    (13.3695, 49.7820),
                    (13.3695, 49.7830),
                    (13.3680, 49.7830),
                    (13.3680, 49.7820),
                ]
            ),
        },
        {
            "id": "722740-890/3",
            "kod_ku": 722740,
            "kod_obce": 554791,
            "cislo_parcely": "890/3",
            "druh_pozemku_id": 14,  # Ostatní plocha
            "druh_pozemku": "ostatní plocha",
            "zpusob_vyuziti": "komerční výstavba",
            "vymera_m2": 4500,
            "geom": Polygon(
                [
                    (13.3820, 49.7420),
                    (13.3840, 49.7420),
                    (13.3840, 49.7435),
                    (13.3820, 49.7435),
                    (13.3820, 49.7420),
                ]
            ),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "ruian_parcely", if_exists="append", geom_col="geom")


def seed_vuv_zaplavy():
    """Seed flood zones referencing ciselnik_povodnove_riziko."""
    logger.info("Seeding vuv_zaplavova_uzemi...")
    data = [
        {
            "q_stupen": "Q100",
            "aktivni_zona": False,
            "tok_nazev": "Berounka",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.3700, 49.7700),
                            (13.3900, 49.7700),
                            (13.3900, 49.7800),
                            (13.3700, 49.7800),
                            (13.3700, 49.7700),
                        ]
                    )
                ]
            ),
        },
        {
            "q_stupen": "Q20",
            "aktivni_zona": False,
            "tok_nazev": "Berounka",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.3720, 49.7720),
                            (13.3880, 49.7720),
                            (13.3880, 49.7780),
                            (13.3720, 49.7780),
                            (13.3720, 49.7720),
                        ]
                    )
                ]
            ),
        },
        {
            "q_stupen": "Q100",
            "aktivni_zona": True,
            "tok_nazev": "Radbuza",
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.3800, 49.7400),
                            (13.3860, 49.7400),
                            (13.3860, 49.7450),
                            (13.3800, 49.7450),
                            (13.3800, 49.7400),
                        ]
                    )
                ]
            ),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "vuv_zaplavova_uzemi", if_exists="append", geom_col="geom")


def seed_aopk_nature():
    """Seed nature protection referencing ciselnik_kategorie_ochrany."""
    logger.info("Seeding aopk_chranena_uzemi...")
    data = [
        {
            "kod": "PP-BEROUNKA",
            "nazev": "Přírodní park Horní Berounka",
            "kategorie_kod": "PRIRODNI_PARK",
            "kategorie": "Přírodní park",
            "ochranne_pasmo": False,
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.3720, 49.7740),
                            (13.4200, 49.7740),
                            (13.4200, 49.8200),
                            (13.3720, 49.8200),
                            (13.3720, 49.7740),
                        ]
                    )
                ]
            ),
        },
        {
            "kod": "NPP-BOLEVEC",
            "nazev": "Bolevecké rybníky",
            "kategorie_kod": "PP",
            "kategorie": "Přírodní památka",
            "ochranne_pasmo": True,
            "geom": MultiPolygon(
                [
                    Polygon(
                        [
                            (13.3600, 49.7850),
                            (13.3800, 49.7850),
                            (13.3800, 49.8000),
                            (13.3600, 49.8000),
                            (13.3600, 49.7850),
                        ]
                    )
                ]
            ),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "aopk_chranena_uzemi", if_exists="append", geom_col="geom")


def seed_zabaged():
    """Seed road networks and rivers."""
    logger.info("Seeding zabaged...")
    roads_data = [
        {
            "trida": "silnice I. třídy",
            "cislo_silnice": "I/20",
            "povrch": "asfalt",
            "geom": MultiLineString(
                [LineString([(13.3740, 49.7600), (13.3755, 49.7755), (13.3760, 49.7900)])]
            ),
        },
        {
            "trida": "místní komunikace",
            "cislo_silnice": "Bolevecká",
            "povrch": "asfalt",
            "geom": MultiLineString(
                [LineString([(13.3670, 49.7815), (13.3700, 49.7825), (13.3750, 49.7830)])]
            ),
        },
    ]
    roads_gdf = gpd.GeoDataFrame(roads_data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(roads_gdf, "zabaged_silnice", if_exists="append", geom_col="geom")

    rivers_data = [
        {
            "jmeno": "Berounka",
            "tok_id": "TOK-001",
            "geom": MultiLineString(
                [LineString([(13.3800, 49.7600), (13.3850, 49.7750), (13.4000, 49.7900)])]
            ),
        },
        {
            "jmeno": "Radbuza",
            "tok_id": "TOK-002",
            "geom": MultiLineString(
                [LineString([(13.3700, 49.7300), (13.3830, 49.7425), (13.3880, 49.7550)])]
            ),
        },
    ]
    rivers_gdf = gpd.GeoDataFrame(rivers_data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(rivers_gdf, "zabaged_vodni_toky", if_exists="append", geom_col="geom")


def seed_osm_poi():
    """Seed POIs."""
    logger.info("Seeding osm_poi...")
    data = [
        {
            "id": "osm-bus-01",
            "category": "transport",
            "amenity": "bus_stop",
            "name": "Bolevec, žel. zastávka",
            "geom": Point(13.3748, 49.7752),
        },
        {
            "id": "osm-school-01",
            "category": "education",
            "amenity": "school",
            "name": "Základní škola Bolevecká",
            "geom": Point(13.3710, 49.7780),
        },
        {
            "id": "osm-health-01",
            "category": "healthcare",
            "amenity": "hospital",
            "name": "Fakultní nemocnice Plzeň - Lochotín",
            "geom": Point(13.3550, 49.7640),
        },
        {
            "id": "osm-shop-01",
            "category": "shopping",
            "amenity": "supermarket",
            "name": "Albert Supermarket Bolevec",
            "geom": Point(13.3720, 49.7770),
        },
    ]
    gdf = gpd.GeoDataFrame(data, crs=TARGET_CRS, geometry="geom")
    save_geodataframe(gdf, "osm_poi", if_exists="append", geom_col="geom")


def seed_csu_and_sentinel():
    """Seed demographic and environmental statistics for municipalities."""
    logger.info("Seeding csu_demografie_obce and sentinel_ndvi_obce...")

    with transaction() as conn:
        res = conn.execute(text("SELECT kod_obce FROM ruian_obce"))
        existing_codes = [r[0] for r in res.fetchall()]

    if not existing_codes:
        raise ValueError("Municipalities must be imported before demographics")

    csu_rows = []
    sentinel_rows = []

    for kod in existing_codes:
        if kod == 554791:  # Plzeň
            pop, seniors, kids, trend, ndvi, green, built = (
                181200,
                37150,
                26800,
                2.8,
                0.58,
                52.4,
                34.2,
            )
        elif kod == 555771:  # Klatovy
            pop, seniors, kids, trend, ndvi, green, built = (
                22140,
                5120,
                3100,
                -0.5,
                0.67,
                68.1,
                21.0,
            )
        elif kod == 559717:  # Rokycany
            pop, seniors, kids, trend, ndvi, green, built = 14380, 3210, 2080, 1.2, 0.61, 58.9, 27.5
        else:
            base_pop = 500 + ((kod * 17) % 4500)
            seniors = int(base_pop * 0.19)
            kids = int(base_pop * 0.15)
            pop = base_pop
            trend = round(-2.0 + ((kod % 100) / 20.0), 1)
            ndvi = round(0.55 + ((kod % 30) / 100.0), 2)
            green = round(60.0 + ((kod % 25) - 10), 1)
            built = round(100.0 - green - 15.0, 1)

        prod = pop - seniors - kids
        csu_rows.append(
            {
                "kod_obce": kod,
                "rok": 2024,
                "pocet_obyvatel": pop,
                "seniori_65_plus": seniors,
                "deti_0_14": kids,
                "produktivni_15_64": prod,
                "prirustek_5y_pct": trend,
            }
        )
        sentinel_rows.append(
            {
                "kod_obce": kod,
                "avg_ndvi": ndvi,
                "podil_zelene_pct": green,
                "zastavena_plocha_pct": built,
            }
        )

    csu_df = pd.DataFrame(csu_rows)
    save_dataframe(csu_df, "csu_demografie_obce")

    sentinel_df = pd.DataFrame(sentinel_rows)
    save_dataframe(sentinel_df, "sentinel_ndvi_obce")
    logger.info(f"Populated demographics and Sentinel NDVI for {len(csu_rows)} municipalities.")


def run_seed(reset: bool = False):
    """Run explicitly synthetic fixtures in one transaction; preserve existing rows."""
    with transaction(kind="demo"):
        print("🌱 Starting Hybrid Seed for OpenData Geo MCP...")
        if reset:
            drop_tables()
        seed_schema()
        seed_lookups()
        seed_administrative_hierarchy()
        seed_ruian_obce()
        seed_ruian_ku()
        seed_ruian_parcely()
        seed_vuv_zaplavy()
        seed_aopk_nature()
        seed_zabaged()
        seed_osm_poi()
        seed_csu_and_sentinel()
        print("✅ Hybrid Seed completed successfully!")


if __name__ == "__main__":
    run_seed()
