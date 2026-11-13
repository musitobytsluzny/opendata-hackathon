# Lokální vývoj

Z kořene repozitáře (Docker Desktop / Docker Engine s Compose):

```sh
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/compose.dev.yml up -d --build --wait
python3 infra/smoke.py
```

| Adresa | Služba |
| --- | --- |
| http://localhost:8080/ | Vite / React, včetně hot reloadu přes WebSocket |
| http://localhost:8080/api/docs | API Swagger; API prefix nginx odstraňuje, ASGI root_path je `/api` |
| http://localhost:8080/api/health/db | Kontrola připojení a obou DB extensions |
| http://localhost:8080/mcp/health | MCP healthcheck |
| http://localhost:8080/mcp/sse | MCP SSE transport; zprávy na `/mcp/messages/` |
| localhost:5432 | PostgreSQL 17, databáze a uživatel `opendata` |

Všechny příkazy níže lze doplnit `--env-file infra/.env`, pokud měníš výchozí hodnoty.
Při změně `HTTP_PORT` nastav pro smoke test např. `BASE_URL=http://localhost:8090`.
Porty nginx i DB jsou publikované pouze na loopback. API, MCP a Vite mají porty
přístupné jen uvnitř Compose sítě; názvy `api`, `mcp`, `web`, `db` jsou interní DNS.

## Databáze

Image vychází z pgvector 0.8.2 pro PostgreSQL 17 a doplňuje PostGIS 3 z PGDG balíčků.
Skript `db/init/001-extensions.sql` povoluje `postgis` a `vector` při prvním
vytvoření databáze. Data zůstávají v pojmenovaném volume `db_data` i po `down`.
Jednorázová služba `api-init` vytvoří tabulky uživatelů a profilů pomocí existujícího
`api/create_tables.py` před startem API. Je idempotentní a nemaže existující data.
Změny existujícího schématu budou vyžadovat Alembic migrace; ty zatím nejsou připravené.

```sh
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c '\dx'
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c "SELECT ST_AsText(ST_Point(14.42, 50.08)), '[1,2,3]'::vector <-> '[1,2,4]'::vector;"
```

Init skripty se na existujícím volume neopakují. Pokud extensions chybí, lze je
doplnit bez mazání dat:

```sh
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c 'CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;'
```

`POSTGRES_*` nastavují databázi při první inicializaci. Při změně přihlašovacích
údajů uprav také `DATABASE_URL`; pro speciální znaky použij URL encoding.

## Vývoj aplikací

Zdrojové adresáře jsou bind mounty. Vite a oba Uvicorn servery automaticky načítají
změny. Závislosti Pythonu vyžadují rebuild. Node závislosti mají vlastní volume;
po změně npm lockfile proveď:

```sh
docker compose -f infra/compose.dev.yml exec web npm ci
docker compose -f infra/compose.dev.yml restart web
```

Web používá relativní `/api`, takže není potřeba CORS. Výchozí login volá skutečné
API a čte `access_token`. Uživatel se zakládá přes `POST /api/users/` ve Swaggeru,
například tělem:

```json
{"username": "developer", "password": "local-password", "profile": {"firstname": "Dev", "lastname": "User"}}
```

API vydává JWT s `sub`, `username`, `iat`, `exp`. `JWT_SECRET_KEY` v Compose má
výchozí hodnotu pouze pro lokální vývoj. Mock lze zapnout přes
`VITE_USE_MOCK_AUTH=true` (`username` / `password`). Uživatelský CRUD zatím nemá
kontrolu oprávnění; ta je další práce na API. MCP už míří na interní API,
jeho ukázkové dataset tools proto do implementace endpointů vrací chyby.
MCP prefix nginx zachovává a SSE má vypnuté bufferování. `/shared` je připojený
read-only do Python kontejnerů.

```sh
docker compose -f infra/compose.dev.yml ps
docker compose -f infra/compose.dev.yml logs -f
docker compose -f infra/compose.dev.yml down
```

Jde pouze o vývojový stack s výchozím lokálním heslem, bez TLS a produkčního buildu.
