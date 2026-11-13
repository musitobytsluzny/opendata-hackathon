# OpenData

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
Při změně závislostí webu spusť `docker compose exec web npm ci` a restartuj web.

Python používá Ruff (`pyproject.toml`, `requirements-dev.txt`), web Oxlint
(`web/.oxlintrc.json`) a textové soubory Prettier (`.prettierrc.json`).
`.editorconfig` sjednocuje odsazení a konce řádků.

Podrobnosti: [infrastruktura](infra/README.md), [ETL](etl/README.md).
