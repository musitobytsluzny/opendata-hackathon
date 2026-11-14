# Kartogram: ověření demonstračních otázek

Živé ověření 14. 11. 2026 přes nakonfigurované Gemini, skutečné MCP, PostGIS a veřejné zdroje. Vybraný úspěšný průchod existuje pro všech **17 scénářů**; protokol spojuje jednotlivá ověření a opakované běhy po opravách. Nejde o jeden bezchybný běh ani záruku každé budoucí odpovědi. Úplné texty úspěšných odpovědí, časy, volání nástrojů a přehled neúspěšných průchodů jsou v [JSON protokolu](demo-validation.json).

## Otázky v pořadí pro demonstraci

1. **school-find** — Najdi školu VOŠ a SPŠE Plzeň.
2. **school-map** — Ukaž ji na mapě.
3. **school-neighbours** — Top 3 nejbližší školy k této škole, původní školu vynech.
4. **01-population** — Kterých pět obcí Plzeňského kraje má nejvíc obyvatel? Vyber vhodný graf.
5. **02-area** — A teď podle rozlohy v m². Ukaž koláčový graf.
6. **03-cities** — Najdi tři nejbližší města k Žihli a ukaž je na mapě.
7. **04-driving** — Seřaď tato města podle skutečné vzdálenosti autem ze Žihle. Přidej modelový čas jízdy.
8. **05-alternatives** — Najdi v okolí Žihle alternativní obce s podobným počtem obyvatel, v rozmezí ±30 %.
9. **06-address** — Najdi parcelu na adrese Žihle 294, 331 65. Přibliž ji a ukaž její hranici.
10. **07-life** — Jaké každodenní služby jsou kolem této parcely? Ukaž nejbližší školu, školku, nemocnici a veřejnou dopravu. Chybějící údaje označ.
11. **08-schools-driving** — Najdi tři nejbližší základní školy. Porovnej jejich dojezd autem od této parcely.
12. **08b-school-route-context** — Jsou cestou z parcely na adrese Žihle 294 do nejbližší základní školy ve stejné obci nějaká nebezpečí, která by mohla čekat děti? Ověř skutečnou pěší trasu a ukaž mapové nálezy i chybějící údaje.
13. **09-layers** — Zobraz kolem této parcely záplavová území a chráněná území v okruhu dvou kilometrů.
14. **10-hide** — Skryj chráněná území a nech zobrazenou parcelu a záplavové oblasti.
15. **11-compare** — Porovnej dvě parcely, které jsem právě vybral v mapě, podle výměry, druhu pozemku a evidovaných prostorových omezení. Výměry zobraz vhodným grafem.
16. **12-compare-schools** — Kolem každé z těchto dvou parcel najdi nejbližší základní školu a porovnej dostupnost autem.
17. **13-conclusion** — Shrň poslední porovnání pro rodinu s malými dětmi. Odděl naměřená fakta, možné kompromisy a údaje, které ještě potřebujeme zjistit.

U bodu 15 (11-compare) je třeba vybrat dvě různé parcely v mapě. Audit použil skutečné parcely 110/2 a 33 v KÚ Žihle, vnitřní body jejich geometrií a autentizovaný endpoint výběru kliknutím. Gesta a předání souřadnic v prohlížeči samostatně ověřuje Playwright.

## Co bylo opraveno

- VOŠ/SPŠE/ZŠ/MŠ se vyhledávají přes skutečné názvy a generované aliasy; obec omezuje výběr prostorově. Původní kampus se vynechává napříč zdroji.
- PSČ s mezerou i bez mezery se filtruje jako číslo. Výpadek adresní služby není zpráva, že adresa neexistuje.
- Porovnání parcel vyžaduje prostorové prověření každé parcely. Dojezdy se počítají ve směru od každé parcely ke škole.
- Chat zachovává i reference nezobrazených nástrojů. Závěrečný rodinný souhrn skládá výměry, průniky a směry tras přímo z ověřených dat.
- Pěší trasa a mapové jevy mají vlastní výpočet koridoru a text sestavený z dat. Kontrola pouze koncových bodů nestačí.

## Načtená data

| Vrstva              | Počet řádků |
| ------------------- | ----------: |
| aopk_chranena_uzemi |         935 |
| chmu_stanice_voda   |          79 |
| csu_demografie_obce |         501 |
| facility_poi        |       3 346 |
| municipality_status |         501 |
| osm_poi             |       4 849 |
| osm_route_features  |     145 806 |
| ruian_ku            |       1 395 |
| ruian_obce          |         501 |
| ruian_parcely       |   1 685 998 |
| vuv_zaplavova_uzemi |         633 |
| zabaged_silnice     |      14 081 |
| zabaged_vodni_toky  |      75 832 |

Parcely: zpracováno 1 395 katastrů, 1 393 s parcelami. Zdroj potvrdil nulový export pro KÚ 692484, 719293; jde o evidované mezery v pokrytí, nikoliv potvrzení neexistence pozemků. `parcels-progress.json` umožňuje navázání importu.

## Hranice tvrzení

- Počet mapových prvků v koridoru není počet nebezpečí ani skutečných křížení. Tok není automaticky hrozba, 2D průnik neověřuje most ani mimoúrovňové křížení.
- Chybějící údaj o chodníku neznamená chybějící chodník; `sidewalk=no` není zákaz chůze. Nulové nálezy nepotvrzují bezpečnost cesty pro dítě.
- Neověřujeme aktuální dopravu, rozhled, funkčnost zařízení, kapacity škol, kriminalitu, počasí ani přesné vstupy. OSRM vrací modelové časy. Konce pěší trasy mohou být přichyceny do 150 m, automobilové do 1 km.
- Výměra parcely není velikost zahrady. Katastrální druh pozemku ani nezjištěný průnik s vrstvou nepotvrzuje stavební povolení nebo přípustnost záměru.
- OSM/ČÚZK/PMDP mají vlastní pokrytí a duplicity se odstraňují konzervativně; nejde o úplný katalog služeb. NDVI má pouze schéma, reálný výpočet není načtený.
- Veřejné routingové/datové služby mohou vypadnout a Gemini může omezit kvótu; některé průchody proto vyžadovaly opakování. Výsledky s NULL se nesmějí měnit na nuly.

## Opakování

Nejprve spusť stack a importy dle [ETL dokumentace](../etl/README.md). Potom `make validate-demo`. Běh používá skutečnou kvótu Gemini, dočasný účet a veřejné služby; není součástí CI. Výstup je `api/demo-validation.json`, bez klíčů, tokenů a geometrií.

Automatické kontroly: **55 API + 16 ETL + 2 MCP + 17 prohlížečových testů**, frontendový build a smoke test přes nginx. Python linter a frontendový linter/formát musí před commitem projít.

Doplňkový scénář: [hledání parcel stejně daleko od dvou institucí](balanced-parcels-validation.json). Živě ověřeno nad všemi 1 685 998 načtenými parcelami; samostatný SQL běh trval 4,158 s. Měří se vzdušná vzdálenost od vnitřních bodů, nikoli dojezd nebo geodetická přesnost podkladů.
