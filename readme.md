# Kartogram

React/Vite, FastAPI, MCP a PostgreSQL s PostGIS a pgvector za nginxem.
Jednorázové ETL připravuje místo pro import / seed dat.

## Spuštění

Vyžaduje Docker s Compose a `make`. Z kořene repozitáře:

```sh
make setup # vytvoří jediný lokální .env, pokud ještě neexistuje
make up
make smoke
```

Web: http://localhost:8080/, API: http://localhost:8080/api/docs,
MCP SSE: http://localhost:8080/mcp/sse.

Veškerá konfigurace je v kořenovém `.env`, vzorem je `.env.example`.
Compose předává každé službě jen její proměnné; do webu patří pouze veřejné `VITE_*`.
Lokální `.env` se necommituje ani nekopíruje do Docker images.

## Práce s repozitářem

```sh
make check  # Python lint + format, web lint + format, build webu, validace Compose
make format # opraví formát a bezpečně opravitelné Python lint chyby
make seed   # znovu spustí etl/main.py nad připravenou DB
make logs
make ps
make down   # zachová DB data
```

Kontroly běží v Dockeru bez potřeby lokálních instalací linterů. `make smoke`
vyžaduje Python 3 na hostiteli. CI spouští stejné kontroly a integrační smoke test.
Při startu webu se podle otisku `package.json` a `package-lock.json` automaticky
synchronizují závislosti v Docker volume. Po jejich změně stačí
`docker compose restart web`.

Python používá Ruff (`pyproject.toml`, `requirements-dev.txt`), web Oxlint
(`web/.oxlintrc.json`) a textové soubory Prettier (`.prettierrc.json`).
`.editorconfig` sjednocuje odsazení a konce řádků.

Podrobnosti: [infrastruktura](infra/README.md), [ETL](etl/README.md).

## LLM

Gemini AI Studio se nastavuje přes `GEMINI_API_KEY` v kořenovém `.env`.
Po `make up` ověř přístup pomocí `make check-gemini`. Web nikdy nedostává API klíč.
Podrobnosti o MCP nástrojích, datech a limitech jsou v [API README](api/README.md).

## Frontend

Kartogram zachovává mapové rozhraní; datový asistent v chatu se jmenuje KartogramMCP.
Odpovědi podporují Markdown a tabulky, kopírování, CSV export i navazující dotazy.
Enter odešle dotaz, Shift+Enter vloží nový řádek. Tlačítko zastavení ukončí čekání
v prohlížeči; již spuštěné zpracování na serveru může doběhnout.

Chat lze sbalit tlačítkem minimalizace nebo klávesou Esc; plovoucí vstup otevře
klávesa `/`. Na mobilu lze tažením horního úchytu měnit výšku konverzace.
Historie (`Ctrl/⌘ K`) podporuje hledání i ve zprávách, vlastní názvy, připnutí,
export Markdownu a vrácení smazané konverzace. Rozepsané dotazy a vybraná
konverzace se ukládají pro každý účet v tomto prohlížeči.

Úprava staršího dotazu vytvoří novou konverzaci s kontextem před tímto dotazem;
původní zůstane zachovaná. Při čtení starších zpráv nová odpověď neposouvá chat:
k nejnovější se vrátíte tlačítkem. Tabulky lze řadit podle okresu nebo hodnoty.
Legenda mapy ukazuje rozsah a pokrytí; chybějící údaje odlišuje od nuly.

Šířku chatu lze měnit tažením pravého okraje, šipkami po jeho zaměření nebo tlačítkem
rozšíření. Home/End nastaví minimální/maximální šířku. Nastavení se ukládá v prohlížeči:
ztmavení států mimo ČR, intenzita, názvy měst, hodnoty, mapový podklad, automatické
centrování/posouvání, velikost textu a omezení animací.

Mapový worker je samostatný lokální asset; hranice a výsledky nečekají na vzdálené
snímky. Přehled používá satelitní podklad, ortofoto se automaticky přidává od zoomu 11
nebo lze zapnout ručně. Hranice ČR a jejich původ: [zdroje geometrie](web/src/assets/geo/SOURCES.md).

Prohlížečové regresní testy běží nad produkčním sestavením, s testovacími API odpověďmi
a záměrně vypnutými vzdálenými dlaždicemi:

```sh
cd web
npm ci
npx playwright install chromium
npm run test:e2e
```
