# OpenData Geo ETL - Real Estate Prevalidation

ETL pipeline pro extrakci, transformaci a nahrání geografických a statistických dat do PostgreSQL/PostGIS za účelem **prevalidace realitních a developerských projektů** pomocí AI Agenta (přes MCP server).

## Pilotní rozsah (MVP)
* **Geografické území:** Plzeňský kraj & Plzeň-město (BBOX: 12.45, 48.95 až 13.95, 50.15)
* **Cílový souřadnicový systém:** WGS84 (`EPSG:4326`)
* **Prostorový index:** GiST nad sloupcem `geom` u všech prostorových tabulek

---

## 8 Integrovaných datasetů

| # | Dataset | Zdroj | Formát | Tabulka v PostGIS | Účel pro realitní prevalidaci |
|---|---|---|---|---|---|
| 1 | **RÚIAN & Parcely** | ČÚZK | SHP / CSV | `ruian_obce`<br>`ruian_parcely` | Geometrie parcely, výměra, druh pozemku (orná půda, ZPF vs. zastavitelná plocha). |
| 2 | **Záplavová území** | VÚV TGM | SHP | `vuv_zaplavova_uzemi` | Stopka pro výstavbu: zóny Q100, Q20 a zejména **Aktivní zóna** (zákonný zákaz staveb). |
| 3 | **Ochrana přírody** | AOPK ČR | GeoJSON | `aopk_chranena_uzemi` | Územní limity: CHKO, přírodní parky, NPR, PR, PP, Natura 2000. |
| 4 | **Dopravní infrastruktura** | ZABAGED | GPKG / SHP | `zabaged_silnice`<br>`zabaged_vodni_toky` | Vzdálenost a napojení na veřejnou komunikaci (bez cesty nelze stavět), vodní toky. |
| 5 | **Občanská vybavenost (POI)** | OpenStreetMap | Overpass API | `osm_poi` | Atraktivita lokality: vzdálenost k zastávce MHD, škole, školce, lékaři, obchodu. |
| 6 | **Demografie obcí** | ČSÚ | CSV | `csu_demografie_obce` | Potenciál obce: vývoj počtu obyvatel (5letý růst/pokles), podíl seniorů a dětí. |
| 7 | **Hydrologické profily** | ČHMÚ | JSON / CSV | `chmu_stanice_voda` | Monitorovací body a dlouhodobé hydrologické zatížení toků v okolí. |
| 8 | **Vegetační index (NDVI)** | Sentinel-2 | Agregace | `sentinel_ndvi_obce` | Environmentální kvalita: zelenost lokality, riziko přehřívání, zastavěnost. |

---

## Rychlé spuštění

### 1. Inicializace databáze a pilotních dat (Doporučeno pro okamžité demo)
Aplikuje SQL schéma, prostorové indexy a nahraje kompletní testovací sadu pro Plzeňsko:

```bash
python -m etl.cli --seed
```

### 2. Aplikace pouze SQL schématu a prostorových funkcí
```bash
python -m etl.cli --schema
```

### 3. Stahování vybraných datasetů z externích zdrojů
```bash
# Stáhnout chráněná území z AOPK (GeoJSON)
python -m etl.cli --dataset aopk

# Stáhnout body zájmu (POI) pro Plzeňsko z OpenStreetMap (Overpass API)
python -m etl.cli --dataset osm

# Stáhnout demografii ČSÚ
python -m etl.cli --dataset csu

# Stáhnout záplavová území VÚV
python -m etl.cli --dataset vuv
```

---

## Analytické SQL funkce pro MCP a API

V databázi jsou připraveny bleskové prostorové funkce:
* `fn_prevalidate_parcel(kod_ku, cislo_parcely)`: Vrátí kompletní JSON audit dané parcely.
* `fn_prevalidate_point(lat, lon)`: Vrátí kompletní JSON audit pro GPS bod a jeho okolí.
* `fn_prevalidate_geometry(geom)`: Základní prostorová analytická funkce.
