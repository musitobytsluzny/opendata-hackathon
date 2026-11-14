# ETL: prostorová a relační data

PR přidává schéma pro RÚIAN, povodně, chráněná území, infrastrukturu, POI,
demografii a NDVI. SQL funkce `fn_prevalidate_parcel`, `fn_prevalidate_point`
a `fn_prevalidate_geometry` vrací orientační prostorový report. Nejde o ověřené
právní rozhodnutí ani kompletní pokrytí datových zdrojů.

## Docker a jedna konfigurace

Používá se pouze kořenový `.env`, zejména `DATABASE_URL`. Hostname `db` se
automaticky nepřepisuje na localhost. Pořadí startu je
`db → api-init (Alembic + RBAC) → etl --schema → api → mcp`.
Standardní start nespouští externí stahování ani nevkládá syntetické statistiky.

```sh
make up
make seed # explicitní syntetická demo data, bez stahování
make test-etl
```

`make seed` lze opakovat bez duplicit a bez mazání API účtů. Data jsou označená
jako `demo` v `etl_dataset_status`; prostorové reporty obsahují `data_sources`.
Demo a externí data se v jedné vrstvě nesměšují. Pro reálná data použij jinou DB
nebo vědomě vyčisti jen ETL vrstvy pomocí explicitního `--reset`.

```sh
docker compose run --rm etl python -m etl.main --schema
docker compose run --rm etl python -m etl.main --dataset osm
docker compose run --rm etl python -m etl.main --dataset ruian
```

Pro `--all` i jednotlivé importy se zachovávají existující řádky a FK. Všechny
DB změny daného běhu jsou jedna transakce, chyba je vrátí zpět a ukončí proces
nenulovým kódem. Souběžné běhy serializuje transakční advisory lock. Neúspěšný
externí import se nikdy automaticky nenahrazuje vymyšlenými hodnotami.

`--reset` je destruktivní, explicitní volba pouze pro ETL tabulky; při běžném
startu, seedu ani `--all` se nespouští. Nemění `users`, `profiles` ani Alembic.

## Kompletní regionální pipeline

```sh
docker compose run --rm --no-deps etl python -m etl.main --all --keep-going
```

`--keep-going` potvrdí každou vrstvu samostatně a pokračuje i po chybě jiného
zdroje. `etl/data/pipeline-report.json` zaznamenává výsledek každé vrstvy;
jakákoliv chyba stále znamená nenulový návratový kód. Bez tohoto přepínače
zůstává `--all` atomické. Schéma se při běžném importu připraví krátkou
samostatnou transakcí, aby dlouhé stahování neblokovalo čtení API.

## Rozsah importérů

- RÚIAN: všech 501 obcí a jejich katastrální území v Plzeňském kraji z oficiálního
  ArcGIS ČÚZK. Používá skutečné kódy sedmi okresů, nikoliv pořadová čísla.
- Parcely (`--dataset parcels`): kompletní export každého načteného katastrálního
  území z ČÚZK, nejvýše čtyři souběžné downloady. Počet prvků se porovnává
  se zdrojovou službou; překročení limitu nebo neúplný export způsobí chybu.
- ČSÚ: roční MOS 2025, obyvatelé k 31. 12., děti 0–14 a senioři 65+;
  kontroluje pokrytí všech načtených obcí. Chybějící hodnoty se nenahrazují nulou.
  Pětiletý přírůstek je bez srovnávacího roku NULL.
- VÚV: Q5, Q20, Q100, Q500 a aktivní záplavové zóny z oficiální služby ISVS voda.
  Aktivní zóna má samostatný příznak a nepřiřazuje se jí odhadnutá periodicita.
- AOPK: maloplošná i velkoplošná chráněná území, ochranná pásma a smluvní ochrana.
- ZABAGED: automatické stažení silnic, neevidovaných silnic, staveb a vodních toků
  z oficiálního ArcGIS ČÚZK; lokální GeoPackage již není podmínkou.
- OSM: zdravotnictví, školy, doprava a obchody z Overpass API.
- ČHMÚ: nejnovější dostupný katalog vodoměrných stanic. Aktuální SPA je NULL,
  protože samotný katalog neobsahuje aktuální stav vody.
- Sentinel: zatím pouze schéma, reálný výpočet NDVI není součástí pipeline.

Hranice obcí a parcel vymezují celý kraj. Prostorové vrstvy infrastruktury,
POI a ochrany se stahují v obálce 12.35–13.95° E, 48.85–50.20° N, která kraj
pokrývá s přesahem. Nejde o celorepublikové pokrytí. ArcGIS stránkování ověřuje
počty a cache rozlišuje službu i dotaz, takže změna rozsahu nepoužije stará data.

Chybějící CRS se nehádá; zdroj musí dodat CRS nebo ho importér explicitně určí.
Zápisy probíhají do existujících tabulek s omezeními a indexy; `replace` je zakázané.
Lokální vstupy/cache v `etl/data/` a výstupy v `etl/output/` se necommitují.
Testy používají izolovaná PostgreSQL schémata, bez síťových downloadů.

Občanskou vybavenost nyní doplňují `--dataset facilities` (ČÚZK školy,
zdravotnictví, železnice a statusy obcí) a `--dataset pmdp` (skutečné zastávky
GTFS PMDP). Mají oddělenou provenienci v `facility_poi`; společný pohled
`all_facility_poi` umožňuje dotazovat OSM, ČÚZK a PMDP. Podrobnosti a pokrytí:
[KartogramMCP](../mcp/README.md#skutečné-podklady-pro-občanskou-vybavenost).
