CREATE TABLE IF NOT EXISTS osm_route_features (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT,
    highway TEXT,
    tags_json JSONB NOT NULL,
    geom geometry(Geometry,4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_osm_route_features_geography ON osm_route_features USING gist ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_osm_route_features_kind ON osm_route_features(kind);
