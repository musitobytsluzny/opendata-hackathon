-- ====================================================================
-- OpenData Geo MCP - Hybrid Relational + Spatial Database Schema
-- Architecture: "Spatial-First, Relational-Enriched" (WGS84 EPSG:4326)
-- ====================================================================

-- --------------------------------------------------------------------
-- 1. ČÍSELNÍKY A BYZNYSOVÁ PRAVIDLA (RELATIONAL ENRICHMENT)
-- --------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ciselnik_druh_pozemku (
    id INTEGER PRIMARY KEY,
    kod VARCHAR(20) UNIQUE NOT NULL,
    nazev VARCHAR(100) NOT NULL,
    patri_do_zpf BOOLEAN NOT NULL DEFAULT FALSE,
    je_stavebni_plocha BOOLEAN NOT NULL DEFAULT FALSE,
    stavebni_poznamka VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS ciselnik_povodnove_riziko (
    kod VARCHAR(20) PRIMARY KEY,
    navratnost_let INTEGER NOT NULL,
    zavaznost VARCHAR(20) NOT NULL,
    stavebni_omezeni VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS ciselnik_kategorie_ochrany (
    kod VARCHAR(30) PRIMARY KEY,
    nazev VARCHAR(100) NOT NULL,
    stupen_prisnosti INTEGER NOT NULL,
    stavebni_omezeni VARCHAR(255) NOT NULL
);

-- --------------------------------------------------------------------
-- 2. ÚZEMNÍ HIERARCHIE (KRAJE -> OKRESY -> OBCE -> KÚ)
-- --------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS kraje (
    kod_kraje VARCHAR(10) PRIMARY KEY,
    nazev VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS okresy (
    kod_okresu VARCHAR(10) PRIMARY KEY,
    kod_kraje VARCHAR(10) NOT NULL REFERENCES kraje(kod_kraje),
    nazev VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS ruian_obce (
    kod_obce INTEGER PRIMARY KEY,
    kod_okresu VARCHAR(10) REFERENCES okresy(kod_okresu),
    nazev VARCHAR(255) NOT NULL,
    okres VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);
-- Migration guard if table was created in an earlier flat schema version
ALTER TABLE ruian_obce ADD COLUMN IF NOT EXISTS kod_okresu VARCHAR(10) REFERENCES okresy(kod_okresu);
CREATE INDEX IF NOT EXISTS idx_ruian_obce_geom ON ruian_obce USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ruian_obce_okres ON ruian_obce (kod_okresu);

CREATE TABLE IF NOT EXISTS ruian_ku (
    kod_ku INTEGER PRIMARY KEY,
    kod_obce INTEGER NOT NULL REFERENCES ruian_obce(kod_obce) ON DELETE CASCADE,
    nazev VARCHAR(255) NOT NULL,
    geom GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_ruian_ku_geom ON ruian_ku USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ruian_ku_obec ON ruian_ku (kod_obce);

CREATE TABLE IF NOT EXISTS ruian_parcely (
    id VARCHAR(50) PRIMARY KEY,
    kod_ku INTEGER NOT NULL REFERENCES ruian_ku(kod_ku) ON DELETE CASCADE,
    kod_obce INTEGER REFERENCES ruian_obce(kod_obce) ON DELETE SET NULL,
    cislo_parcely VARCHAR(50) NOT NULL,
    druh_pozemku_id INTEGER REFERENCES ciselnik_druh_pozemku(id),
    druh_pozemku VARCHAR(100),
    zpusob_vyuziti VARCHAR(100),
    vymera_m2 INTEGER NOT NULL,
    geom GEOMETRY(Geometry, 4326) NOT NULL
);
-- Migration guards if table already existed
ALTER TABLE ruian_parcely ADD COLUMN IF NOT EXISTS kod_obce INTEGER REFERENCES ruian_obce(kod_obce) ON DELETE SET NULL;
ALTER TABLE ruian_parcely ADD COLUMN IF NOT EXISTS druh_pozemku_id INTEGER REFERENCES ciselnik_druh_pozemku(id);
CREATE INDEX IF NOT EXISTS idx_ruian_parcely_geom ON ruian_parcely USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ruian_parcely_lookup ON ruian_parcely (kod_ku, cislo_parcely);
CREATE INDEX IF NOT EXISTS idx_ruian_parcely_druh ON ruian_parcely (druh_pozemku_id);

-- --------------------------------------------------------------------
-- 3. PROSTOROVÉ VRSTVY S RELAČNÍMI ČÍSELNÍKY
-- --------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vuv_zaplavova_uzemi (
    id SERIAL PRIMARY KEY,
    q_stupen VARCHAR(20) NOT NULL REFERENCES ciselnik_povodnove_riziko(kod),
    aktivni_zona BOOLEAN DEFAULT FALSE,
    tok_nazev VARCHAR(255),
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vuv_zaplavova_uzemi_geom ON vuv_zaplavova_uzemi USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_vuv_zaplavova_uzemi_q ON vuv_zaplavova_uzemi (q_stupen, aktivni_zona);

CREATE TABLE IF NOT EXISTS aopk_chranena_uzemi (
    id SERIAL PRIMARY KEY,
    kod VARCHAR(50),
    nazev VARCHAR(255) NOT NULL,
    kategorie_kod VARCHAR(30) REFERENCES ciselnik_kategorie_ochrany(kod),
    kategorie VARCHAR(100) NOT NULL,
    ochranne_pasmo BOOLEAN DEFAULT FALSE,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);
-- Migration guard
ALTER TABLE aopk_chranena_uzemi ADD COLUMN IF NOT EXISTS kategorie_kod VARCHAR(30) REFERENCES ciselnik_kategorie_ochrany(kod);
CREATE INDEX IF NOT EXISTS idx_aopk_chranena_uzemi_geom ON aopk_chranena_uzemi USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_aopk_chranena_uzemi_kat ON aopk_chranena_uzemi (kategorie_kod);

CREATE TABLE IF NOT EXISTS zabaged_silnice (
    id SERIAL PRIMARY KEY,
    trida VARCHAR(50),
    cislo_silnice VARCHAR(50),
    povrch VARCHAR(50),
    geom GEOMETRY(MultiLineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_zabaged_silnice_geom ON zabaged_silnice USING GIST (geom);

CREATE TABLE IF NOT EXISTS zabaged_vodni_toky (
    id SERIAL PRIMARY KEY,
    jmeno VARCHAR(255),
    tok_id VARCHAR(50),
    geom GEOMETRY(MultiLineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_zabaged_vodni_toky_geom ON zabaged_vodni_toky USING GIST (geom);

CREATE TABLE IF NOT EXISTS osm_poi (
    id VARCHAR(50) PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    amenity VARCHAR(50),
    name VARCHAR(255),
    geom GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_osm_poi_geom ON osm_poi USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_osm_poi_category ON osm_poi (category, amenity);

-- --------------------------------------------------------------------
-- 4. STATISTICKÉ A ENVIRONMENTÁLNÍ ATRIBUTY OBCÍ
-- --------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS csu_demografie_obce (
    kod_obce INTEGER PRIMARY KEY REFERENCES ruian_obce(kod_obce) ON DELETE CASCADE,
    rok INTEGER NOT NULL,
    pocet_obyvatel INTEGER NOT NULL,
    seniori_65_plus INTEGER DEFAULT 0,
    deti_0_14 INTEGER DEFAULT 0,
    produktivni_15_64 INTEGER DEFAULT 0,
    prirustek_5y_pct NUMERIC(5, 2) DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS sentinel_ndvi_obce (
    kod_obce INTEGER PRIMARY KEY REFERENCES ruian_obce(kod_obce) ON DELETE CASCADE,
    avg_ndvi NUMERIC(4, 3) NOT NULL,
    podil_zelene_pct NUMERIC(5, 2) NOT NULL,
    zastavena_plocha_pct NUMERIC(5, 2)
);

CREATE TABLE IF NOT EXISTS chmu_stanice_voda (
    stanice_kod VARCHAR(50) PRIMARY KEY,
    nazev VARCHAR(255) NOT NULL,
    tok VARCHAR(100),
    spa_aktualni INTEGER DEFAULT 0,
    geom GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chmu_stanice_voda_geom ON chmu_stanice_voda USING GIST (geom);


CREATE TABLE IF NOT EXISTS etl_dataset_status (
    table_name TEXT PRIMARY KEY,
    data_kind TEXT NOT NULL CHECK (data_kind IN ('reference', 'demo', 'external')),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vuv_zaplavova_uzemi_etl ON vuv_zaplavova_uzemi ((COALESCE(q_stupen::text, '')), (COALESCE(aktivni_zona::text, '')), (COALESCE(tok_nazev::text, '')), (md5(ST_AsEWKB(geom)::text)));
CREATE UNIQUE INDEX IF NOT EXISTS uq_aopk_chranena_uzemi_etl ON aopk_chranena_uzemi ((COALESCE(kod::text, '')), (COALESCE(nazev::text, '')), (COALESCE(kategorie::text, '')), (COALESCE(ochranne_pasmo::text, '')), (md5(ST_AsEWKB(geom)::text)));
CREATE UNIQUE INDEX IF NOT EXISTS uq_zabaged_silnice_etl ON zabaged_silnice ((COALESCE(trida::text, '')), (COALESCE(cislo_silnice::text, '')), (COALESCE(povrch::text, '')), (md5(ST_AsEWKB(geom)::text)));
CREATE UNIQUE INDEX IF NOT EXISTS uq_zabaged_vodni_toky_etl ON zabaged_vodni_toky ((COALESCE(jmeno::text, '')), (COALESCE(tok_id::text, '')), (md5(ST_AsEWKB(geom)::text)));
CREATE INDEX IF NOT EXISTS idx_zabaged_silnice_geography ON zabaged_silnice USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_zabaged_vodni_toky_geography ON zabaged_vodni_toky USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_osm_poi_geography ON osm_poi USING GIST ((geom::geography));
