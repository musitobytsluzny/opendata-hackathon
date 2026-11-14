-- ====================================================================
-- OpenData Geo MCP - Hybrid Spatial-Relational Functions & Views
-- ====================================================================

-- 1. Hlavní prevalidační funkce nad libovolnou geometrií
-- Obohatí prostorový průnik o relační číselníky, legislativní omezení a demografii
CREATE OR REPLACE FUNCTION fn_prevalidate_geometry(p_geom GEOMETRY)
RETURNS JSONB AS $$
DECLARE
    v_target_geom GEOMETRY;
    v_centroid GEOMETRY;
    v_result JSONB;
    v_municipality RECORD;
    v_flood RECORD;
    v_nature RECORD;
    v_road RECORD;
    v_river RECORD;
    v_poi RECORD;
    v_demography RECORD;
    v_environment RECORD;
BEGIN
    v_target_geom := ST_Transform(p_geom, 4326);
    v_centroid := ST_Centroid(v_target_geom);

    -- 1. Zjištění obce a hierarchie přes prostorový průnik (ST_Intersects)
    SELECT 
        o.kod_obce, 
        o.nazev AS obec_nazev, 
        ok.nazev AS okres_nazev, 
        kr.nazev AS kraj_nazev
    INTO v_municipality
    FROM ruian_obce o
    LEFT JOIN okresy ok ON o.kod_okresu = ok.kod_okresu
    LEFT JOIN kraje kr ON ok.kod_kraje = kr.kod_kraje
    WHERE ST_Intersects(o.geom, v_centroid)
    LIMIT 1;

    -- 2. Záplavové riziko (prostorový ST_Intersects spojený s relačním číselníkem rizik)
    SELECT 
        COALESCE(bool_or(z.q_stupen = 'Q100'), FALSE) AS in_q100,
        COALESCE(bool_or(z.q_stupen = 'Q20'), FALSE) AS in_q20,
        COALESCE(bool_or(z.aktivni_zona = TRUE), FALSE) AS in_active_zone,
        string_agg(DISTINCT z.tok_nazev, ', ') AS flood_rivers,
        string_agg(DISTINCT c.stavebni_omezeni, ' | ') AS flood_restrictions,
        (ARRAY_AGG(c.zavaznost ORDER BY c.navratnost_let))[1] AS max_severity
    INTO v_flood
    FROM vuv_zaplavova_uzemi z
    LEFT JOIN ciselnik_povodnove_riziko c ON z.q_stupen = c.kod
    WHERE ST_Intersects(z.geom, v_target_geom);

    -- 3. Ochrana přírody (ST_Intersects spojený s relačním číselníkem ochrany)
    SELECT 
        bool_or(a.id IS NOT NULL) AS in_protected_area,
        string_agg(DISTINCT a.nazev || ' (' || COALESCE(k.nazev, a.kategorie) || ')', '; ') AS protected_areas,
        string_agg(DISTINCT k.stavebni_omezeni, ' | ') AS nature_restrictions,
        MIN(k.stupen_prisnosti) AS max_restriction_level,
        COALESCE(bool_or(a.ochranne_pasmo = TRUE), FALSE) AS in_buffer_zone
    INTO v_nature
    FROM aopk_chranena_uzemi a
    LEFT JOIN ciselnik_kategorie_ochrany k ON a.kategorie_kod = k.kod
    WHERE ST_Intersects(a.geom, v_target_geom);

    -- 4. Dopravní napojení (ZABAGED silnice přes ST_DWithin a ST_Distance)
    SELECT 
        ROUND(MIN(ST_Distance(v_target_geom::geography, s.geom::geography))::numeric, 1) AS distance_m,
        (ARRAY_AGG(s.trida ORDER BY ST_Distance(v_target_geom::geography, s.geom::geography)))[1] AS road_type,
        (ARRAY_AGG(s.cislo_silnice ORDER BY ST_Distance(v_target_geom::geography, s.geom::geography)))[1] AS road_number
    INTO v_road
    FROM zabaged_silnice s
    WHERE ST_DWithin(v_target_geom::geography, s.geom::geography, 5000);

    -- 5. Vodní toky v okolí (ZABAGED)
    SELECT 
        ROUND(MIN(ST_Distance(v_target_geom::geography, t.geom::geography))::numeric, 1) AS distance_m,
        (ARRAY_AGG(t.jmeno ORDER BY ST_Distance(v_target_geom::geography, t.geom::geography)))[1] AS river_name
    INTO v_river
    FROM zabaged_vodni_toky t
    WHERE ST_DWithin(v_target_geom::geography, t.geom::geography, 2000);

    -- 6. Občanská vybavenost (OSM)
    SELECT 
        ROUND(MIN(CASE WHEN amenity IN ('bus_stop', 'platform', 'tram_stop') OR category = 'transport' 
                       THEN ST_Distance(v_centroid::geography, geom::geography) END)::numeric, 1) AS dist_transit_m,
        ROUND(MIN(CASE WHEN amenity IN ('school', 'kindergarten') 
                       THEN ST_Distance(v_centroid::geography, geom::geography) END)::numeric, 1) AS dist_education_m,
        ROUND(MIN(CASE WHEN amenity IN ('hospital', 'clinic', 'doctors', 'pharmacy') 
                       THEN ST_Distance(v_centroid::geography, geom::geography) END)::numeric, 1) AS dist_health_m,
        ROUND(MIN(CASE WHEN amenity IN ('supermarket', 'convenience') OR category = 'shopping' 
                       THEN ST_Distance(v_centroid::geography, geom::geography) END)::numeric, 1) AS dist_grocery_m
    INTO v_poi
    FROM all_facility_poi
    WHERE ST_DWithin(v_centroid::geography, geom::geography, 10000);

    -- 7. Demografie obce (ČSÚ) - získáno relačně podle obce
        SELECT pocet_obyvatel, seniori_65_plus, prirustek_5y_pct,
               ROUND((seniori_65_plus::numeric / NULLIF(pocet_obyvatel, 0) * 100), 1) AS seniori_pct
        INTO v_demography
        FROM csu_demografie_obce
        WHERE kod_obce = v_municipality.kod_obce;

    -- 8. Environmentální zeleň (Sentinel-2 NDVI)
        SELECT avg_ndvi, podil_zelene_pct, zastavena_plocha_pct
        INTO v_environment
        FROM sentinel_ndvi_obce
        WHERE kod_obce = v_municipality.kod_obce;

    -- Sestavení výsledného JSON objektu obohaceného o relační pravidla
    v_result := jsonb_build_object(
        'assessment_kind', 'indicative',
        'data_sources', COALESCE((SELECT jsonb_object_agg(table_name, jsonb_build_object(
            'kind', data_kind, 'rows', row_count, 'loaded_at', loaded_at)) FROM etl_dataset_status), '{}'::jsonb),
        'location_hierarchy', jsonb_build_object(
            'municipality_code', v_municipality.kod_obce,
            'municipality_name', v_municipality.obec_nazev,
            'district_name', v_municipality.okres_nazev,
            'region_name', v_municipality.kraj_nazev
        ),
        'flood_risk', jsonb_build_object(
            'in_q100', COALESCE(v_flood.in_q100, FALSE),
            'in_q20', COALESCE(v_flood.in_q20, FALSE),
            'in_active_zone', COALESCE(v_flood.in_active_zone, FALSE),
            'rivers', v_flood.flood_rivers,
            'severity', COALESCE(v_flood.max_severity, 'BEZ RIZIKA'),
            'legal_restriction', COALESCE(v_flood.flood_restrictions, 'Bez evidovaných záplavových omezení')
        ),
        'nature_protection', jsonb_build_object(
            'in_protected_area', COALESCE(v_nature.in_protected_area, FALSE),
            'areas', v_nature.protected_areas,
            'in_buffer_zone', COALESCE(v_nature.in_buffer_zone, FALSE),
            'restriction_level', v_nature.max_restriction_level,
            'legal_restriction', COALESCE(v_nature.nature_restrictions, 'Bez evidovaných omezení ochrany přírody')
        ),
        'infrastructure', jsonb_build_object(
            'nearest_road_distance_m', v_road.distance_m,
            'road_type', v_road.road_type,
            'road_number', v_road.road_number,
            'nearest_river_distance_m', v_river.distance_m,
            'river_name', v_river.river_name
        ),
        'amenities_distance_m', jsonb_build_object(
            'public_transport', v_poi.dist_transit_m,
            'education', v_poi.dist_education_m,
            'healthcare', v_poi.dist_health_m,
            'grocery', v_poi.dist_grocery_m
        ),
        'demographics', jsonb_build_object(
            'population', v_demography.pocet_obyvatel,
            'trend_5y_pct', v_demography.prirustek_5y_pct,
            'seniors_ratio_pct', v_demography.seniori_pct
        ),
        'environment', jsonb_build_object(
            'ndvi_score', v_environment.avg_ndvi,
            'greenery_pct', v_environment.podil_zelene_pct,
            'built_up_pct', v_environment.zastavena_plocha_pct
        )
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql STABLE;

-- 2. Funkce pro prevalidaci konkrétní parcely (Relační vyhledání + Geometrický audit)
CREATE OR REPLACE FUNCTION fn_prevalidate_parcel(p_kod_ku INTEGER, p_cislo VARCHAR)
RETURNS JSONB AS $$
DECLARE
    v_parcel RECORD;
    v_result JSONB;
BEGIN
    SELECT 
        p.id, 
        p.kod_ku, 
        ku.nazev AS ku_nazev,
        p.cislo_parcely, 
        p.vymera_m2, 
        dp.nazev AS druh_pozemku_nazev,
        dp.patri_do_zpf,
        dp.je_stavebni_plocha,
        dp.stavebni_poznamka,
        p.geom
    INTO v_parcel
    FROM ruian_parcely p
    JOIN ruian_ku ku ON p.kod_ku = ku.kod_ku
    LEFT JOIN ciselnik_druh_pozemku dp ON p.druh_pozemku_id = dp.id
    WHERE p.kod_ku = p_kod_ku AND p.cislo_parcely = p_cislo
    LIMIT 1;

    IF v_parcel.id IS NULL THEN
        RETURN jsonb_build_object(
            'status', 'not_found',
            'message', 'Parcela s daným číslem a k.ú. nebyla nalezena'
        );
    END IF;

    -- Spustíme prostorovou analýzu nad polygonem parcely
    v_result := fn_prevalidate_geometry(v_parcel.geom);

    RETURN v_result || jsonb_build_object(
        'parcel', jsonb_build_object(
            'id', v_parcel.id,
            'kod_ku', v_parcel.kod_ku,
            'ku_nazev', v_parcel.ku_nazev,
            'cislo_parcely', v_parcel.cislo_parcely,
            'vymera_m2', v_parcel.vymera_m2,
            'druh_pozemku', v_parcel.druh_pozemku_nazev,
            'patri_do_zpf', COALESCE(v_parcel.patri_do_zpf, FALSE),
            'je_stavebni_plocha', COALESCE(v_parcel.je_stavebni_plocha, FALSE),
            'legal_notes', v_parcel.stavebni_poznamka
        ),
        'geojson', ST_AsGeoJSON(v_parcel.geom)::jsonb
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. Funkce pro prevalidaci GPS souřadnic
CREATE OR REPLACE FUNCTION fn_prevalidate_point(p_lat DOUBLE PRECISION, p_lon DOUBLE PRECISION)
RETURNS JSONB AS $$
DECLARE
    v_point GEOMETRY;
    v_buffer GEOMETRY;
    v_result JSONB;
BEGIN
    v_point := ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326);
    -- 25m buffer pro průnik s polygony záplav a chráněných území
    v_buffer := ST_Buffer(v_point::geography, 25)::geometry;

    v_result := fn_prevalidate_geometry(v_buffer);

    RETURN v_result || jsonb_build_object(
        'query_point', jsonb_build_object('lat', p_lat, 'lon', p_lon),
        'geojson', ST_AsGeoJSON(v_point)::jsonb
    );
END;
$$ LANGUAGE plpgsql STABLE;
