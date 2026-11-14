# KartogramMCP: data, výpočty a zobrazení

Chat používá malé operace, které lze skládat. Hodnoty, geometrie i výpočty pocházejí
ze služby API; model vybírá operace a píše vysvětlení. Nástroje nepřijímají SQL.
Datové nástroje předávají vlastní bearer token uživatele do API.

| Operace             | Nástroje                                                                            |
| ------------------- | ----------------------------------------------------------------------------------- |
| Zdroje a statistiky | `dataset_catalog`, `district_statistics`, `municipality_statistics`                 |
| Identifikace míst   | `search_places`, `place_geometry`, `search_amenities`                               |
| Okolí a měření      | `nearby_places`, `measure_distance`, `find_route`                                   |
| Parcely a prověření | `parcel_at_point`, `prevalidate_parcel`, `prevalidate_point`, `prevalidate_address` |
| Grafické podklady   | `load_map_layer`                                                                    |
| Práce s výsledkem   | `filter_result`, `compare_results`, `summarize_result`                              |
| Zobrazení           | `show_map`, `show_table`, `show_chart`, `set_map_layer`                             |

`search_places` rozlišuje obce (`obec`), katastry (`ku`), zařízení (`poi`) a parcely
(`parcela`). Další operace používají skutečné identifikátory z vyhledávání,
nikoliv souřadnice odhadnuté modelem. Více shod vyžaduje upřesnění.

`measure_distance` počítá geodetickou vzdálenost mezi body míst přes PostGIS/WGS84.
U obce nebo katastru jde o vnitřní bod území. `nearby_places` pracuje se stejným
měřením; pořadí a radius se neopírají o jazykový odhad. Výsledky zahrnují jen načtené POI.

`find_route` používá veřejnou službu [OSRM](https://project-osrm.org/docs/v5.24.0/api/)
s automobilem: skutečnou geometrii silniční trasy, její délku a modelový čas bez
živé dopravy. Nevrací pěší ani cyklistickou trasu. Při výpadku vrací chybu,
nikoliv odhad vzdálenosti nebo času. Přichycení koncových bodů je omezené na 1 km.

`load_map_layer` načítá záplavová území, ochranu přírody, silnice, vodní toky nebo
parcely kolem známého místa. Výběr je omezený rádiem a počtem prvků; případné
zkrácení je součástí výsledku. Nejde o bezešvou celorepublikovou dlaždicovou službu.

## Ověřené výsledky a UI

Chat host přidělí datovému výsledku neprůhledné `result_id`. Prezentační nástroje
vracejí deklarativní pokyny s tímto ID. Host je ověří a teprve potom přidá do
odpovědi `artifacts` nebo `layer_actions`. Samotný MCP server nekreslí uživatelské UI.

Tabulka, graf i mapa sdílejí stejné řádky a geometrie; model jim neposílá vlastní
číselné hodnoty. Graf vyžaduje skutečný číselný sloupec. Řazení, porovnání a souhrny
provádí server. Porovnání vyžaduje shodná pole a jednotky. Souhrn omezeného výběru
se nesmí vydávat za souhrn celé databáze. Prázdné hodnoty zůstávají prázdné.

Výsledky jsou omezené velikostí a ukládají se do paměti procesu na 15 minut,
s vazbou na ID uživatele a maximálně 128 záznamy. Frontend posílá nejvýše 8 referencí
z předchozích odpovědí. Po restartu/vypršení nebo při přepnutí workeru musí agent data
načíst znovu. Obsah uložený v prohlížeči není důvěryhodným podkladem pro výpočty.

V mapě je možné současně zobrazit až 12 výsledkových vrstev. Každá má vlastní
barvu a viditelnost. Uživatel i agent mohou měnit viditelnost; vypnutí nemaže data.
Měření a trasy mají popisky vzdálenosti přímo na mapě.

V nabídce **Mapa a vrstvy** lze zapnout výběr parcely nebo výběr dvou parcel pro
porovnání. Kliknutí používá skutečné souřadnice mapy, dotazuje lokální katastr a při
chybějících datech ČÚZK. Shody na hranici nejsou automaticky redukované na první
parcelu. Prověření a porovnání se spouští tlačítkem do chatu. Posouzení zůstává
orientační a závisí na pokrytí podkladových vrstev.

`show_chart` používá ve výchozím stavu `kind=auto`: sloupce pro kategoriální srovnání,
spojnici pro seřazené časové údaje. Výslovně lze zvolit `pie`, pokud sloupec obsahuje
sčitatelné nezáporné hodnoty a výběr má 2–12 položek. Podíly odpovídají součtu výběru,
nikoliv automaticky celému kraji. Procentní ukazatele a indexy se neskládají do koláče.
`municipality_statistics(metric="area_m2")` počítá rozlohu správního území obce pomocí
PostGIS `ST_Area(geom::geography)`; nejde o rozlohu samotné zástavby.

## Sousední města, alternativy a každodenní život

- `nearest_municipalities`: skutečně nejbližší načtené obce, bez předem zadaných
  kandidátů. `cities_only=true` filtruje status RÚIAN 3/4/5; vesnice nejsou vydávané
  za města. Měří se mezi vnitřními body správních území a výchozí obec se vynechává.
- `alternative_municipalities`: blízké obce s počtem obyvatel v explicitním
  procentním rozmezí od výchozí obce. Jde o demografickou podobnost, nikoliv skóre
  kvality života, cen nemovitostí či bezpečnosti.
- `nearby_facilities`: školy, ZŠ, SŠ, VŠ, školky, nemocnice, zdravotnictví, lékárny,
  veřejná doprava, železnice a potraviny. Nemocnice se nezaměňuje za ordinaci;
  školky se odlišují od škol podle atributu ČÚZK. MHD vybírá nejbližší nástupiště
  pro každou pojmenovanou zastávku, ne několik kopií téže zastávky.
- `accessibility_summary`: nejbližší zařízení v šesti každodenních kategoriích.
  Chybějící nález zůstává NULL. Obsahuje výchozí místo, takže dva přehledy lze
  porovnat přes `compare_results`.
- `facility_alternatives`: další zařízení stejného podporovaného typu/kategorie;
  vylučuje původní zařízení i ostatní nástupiště téže zastávky.
- `rank_driving_candidates`: jedna skutečná matice OSRM pro 1–8 kandidátů. Porovnává
  délku nejrychlejší automobilové trasy a modelový čas bez živé dopravy. Pořadí
  platí jen pro kandidáty, ne pro všechny možné cíle v databázi.

Všechny výsledky lze rovnou zobrazit na mapě a v tabulce; číselné sloupce i v grafu.
Vzdušné měření není jízdní ani pěší vzdálenost. Bod obce nemusí být jejím náměstím.

## Skutečné podklady pro občanskou vybavenost

```sh
docker compose run --rm --no-deps etl python -m etl.main --dataset facilities
docker compose run --rm --no-deps etl python -m etl.main --dataset pmdp
```

Import `facilities` načítá školy, zdravotnictví a železnici z oficiálního
[ZABAGED ČÚZK](https://ags.cuzk.gov.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer)
a statusy obcí z [RÚIAN](https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/12).
Import `pmdp` čte jen zastávky z oficiálního
[GTFS PMDP](https://opendata.plzen.eu/public/opendata/detail/187), licence CC BY 4.0.
Neimportuje odjezdy ani frekvenci spojů.

Nová tabulka `facility_poi` uchovává vydavatele a zdrojové URL; údaje ČÚZK a PMDP se
neoznačují jako OpenStreetMap. Pohled `all_facility_poi` je spojuje s existujícím OSM.
Nové importy mají vlastní transakční zámek a potvrzují se atomicky; dlouhý parcelní
import je neblokuje. Opakovaný import upsertuje stabilní identifikátory.

Pokrytí obcí a jejich statusů odpovídá Plzeňskému kraji, grafické podklady ČÚZK jeho
obálce s přesahem, PMDP pouze Plzni a obsluhovanému okolí. MHD mimo tato data se
nepředstírá. Dostupnost lékáren a obchodů závisí na skutečně načtených OSM datech;
prázdný nález není důkaz neexistence. Data nepotvrzují ordinační dobu, kapacitu škol,
aktuální provoz, dostupnou péči ani odjezdy spojů.
