CREATE TABLE IF NOT EXISTS facility_poi (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    amenity TEXT NOT NULL,
    publisher TEXT NOT NULL,
    source_url TEXT NOT NULL,
    geom geometry(Point,4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facility_poi_geography ON facility_poi USING gist ((geom::geography));
CREATE TABLE IF NOT EXISTS municipality_status (
    kod_obce INTEGER PRIMARY KEY REFERENCES ruian_obce(kod_obce),
    status_kod INTEGER NOT NULL CHECK(status_kod BETWEEN 1 AND 6),
    status_name TEXT NOT NULL
);
CREATE OR REPLACE VIEW all_facility_poi AS
SELECT 'poi:' || id AS place_id,name,category,amenity,'OpenStreetMap'::text AS publisher,
       'https://www.openstreetmap.org/'::text AS source_url,geom FROM osm_poi
UNION ALL
SELECT 'facility:' || id,name,category,amenity,publisher,source_url,geom FROM facility_poi;
