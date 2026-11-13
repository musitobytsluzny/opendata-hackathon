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

## Rozsah importérů

- RÚIAN: obce a dostupná katastrální území. Skutečný zdroj parcel zatím chybí;
  parcely se při reálném importu nesyntetizují.
- AOPK, OSM a VÚV: importéry zdrojových vrstev; nesoulad CRS/schématu nebo FK
  způsobí rollback. Konkrétní dostupnost vzdálených služeb není garantovaná.
- ČSÚ: vyžaduje normalizovaná pole `kod_obce`, `rok`, `pocet_obyvatel`; mapping
  konkrétního externího CSV se musí doplnit, jinak import bezpečně selže.
- ZABAGED: lokální `etl/data/raw/zabaged.gpkg` s vrstvami SilnicniSit a VodniTok.
- ČHMÚ a Sentinel: schéma a syntetické ukázky; živé importéry nejsou implementované.

Chybějící CRS se nehádá; zdroj musí dodat CRS nebo ho importér explicitně určí.
Zápisy probíhají do existujících tabulek s omezeními a indexy; `replace` je zakázané.
Lokální vstupy/cache v `etl/data/` a výstupy v `etl/output/` se necommitují.
Testy používají izolovaná PostgreSQL schémata, bez síťových downloadů.
