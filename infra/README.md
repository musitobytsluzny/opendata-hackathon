# Lokální vývoj

Z kořene repozitáře (Docker Desktop / Docker Engine s Compose):

```sh
make setup
make up
make smoke
```

| Adresa                              | Služba                                                             |
| ----------------------------------- | ------------------------------------------------------------------ |
| http://localhost:8080/              | Vite / React, včetně hot reloadu přes WebSocket                    |
| http://localhost:8080/api/docs      | API Swagger; API prefix nginx odstraňuje, ASGI root_path je `/api` |
| http://localhost:8080/api/health/db | Kontrola připojení a obou DB extensions                            |
| http://localhost:8080/mcp/health    | MCP healthcheck                                                    |
| http://localhost:8080/mcp/sse       | MCP SSE transport; zprávy na `/mcp/messages/`                      |
| localhost:5432                      | PostgreSQL 17, databáze a uživatel `opendata`                      |

Jediná konfigurace je v kořenovém `.env` (vzor `.env.example`). `make setup`
existující konfiguraci nepřepisuje. `COMPOSE_FILE` umožňuje používat
`docker compose` přímo z kořene; Makefile předává cestu i env soubor explicitně.
`make smoke` zjistí publikovaný HTTP port automaticky. Při přímém spuštění
`python3 infra/smoke.py` lze nastavit `BASE_URL=http://localhost:8090`.
Porty nginx i DB jsou publikované pouze na loopback. API, MCP a Vite mají porty
přístupné jen uvnitř Compose sítě; názvy `api`, `mcp`, `web`, `db` jsou interní DNS.

## Databáze

Image vychází z pgvector 0.8.2 pro PostgreSQL 17 a doplňuje PostGIS 3 z PGDG balíčků.
Skript `db/init/001-extensions.sql` povoluje `postgis` a `vector` při prvním
vytvoření databáze. Data zůstávají v pojmenovaném volume `db_data` i po `down`.
Jednorázová služba `api-init` vytvoří tabulky uživatelů a profilů pomocí existujícího
`api/create_tables.py` před startem API. Je idempotentní a nemaže existující data.
`api/create_tables.py` spouští Alembic migrace. Existující schéma z původního
`create_all` se jednorázově převezme jako baseline a doplní role bez mazání účtů.
Prázdná databáze dostane celé schéma. Další změny přidávej jako nové revize v
`api/migrations/versions/`.

Pořadí startu je `db → api-init → etl → api → mcp`, nginx čeká na zdravé aplikace.
`etl/main.py` je jednorázový krok pro vytvoření prostorového schématu. Výchozí
start používá `--schema`, bez downloadů a syntetických dat. `make seed` explicitně
spustí demo seed v jedné transakci. Chyba ETL zablokuje start API. Podrobnosti
a rozsah reálných importérů jsou v [ETL README](../etl/README.md).
ETL nepoužívá `/docker-entrypoint-initdb.d`, takže lze spustit i nad existující DB.

```sh
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c '\dx'
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c "SELECT ST_AsText(ST_Point(14.42, 50.08)), '[1,2,3]'::vector <-> '[1,2,4]'::vector;"
```

Init skripty se na existujícím volume neopakují. Pokud extensions chybí, lze je
doplnit bez mazání dat:

```sh
docker compose -f infra/compose.dev.yml exec db psql -U opendata -d opendata -c 'CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;'
```

`POSTGRES_*` nastavují databázi při první inicializaci. Šablona `.env` skládá
`DATABASE_URL` ze stejných proměnných; pro speciální znaky v URL použij URL encoding.
Hostname `db` funguje uvnitř Dockeru. Při spouštění Python skriptů přímo na hostiteli
přepiš `DATABASE_URL` na připojení přes `localhost` a publikovaný DB port.
API a MCP načítají kořenový `.env`; proměnné procesu mají přednost.

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
{
  "username": "developer",
  "password": "local-password",
  "profile": { "firstname": "Dev", "lastname": "User" }
}
```

API vydává JWT s `sub`, `username`, `iat`, `exp`. `JWT_SECRET_KEY` v Compose má
výchozí hodnotu pouze pro lokální vývoj. Mock lze zapnout přes
`VITE_USE_MOCK_AUTH=true` (`username` / `password`). Uživatelský CRUD chrání RBAC
podle pravidel v [API README](../api/README.md). MCP už míří na interní API,
jeho ukázkové dataset tools proto do implementace endpointů vrací chyby.
MCP prefix nginx zachovává a SSE má vypnuté bufferování. `/shared` je připojený
read-only do Python kontejnerů.

```sh
docker compose -f infra/compose.dev.yml ps
docker compose -f infra/compose.dev.yml logs -f
docker compose -f infra/compose.dev.yml down
```

Jde pouze o vývojový stack s výchozím lokálním heslem, bez TLS a produkčního buildu.

## Produkce na VPS přes Coolify

Produkční stack je samostatný soubor `compose.prod.yml`; vývojový Compose
nepoužívej pro veřejný deploy. Obsahuje statický web a jedinou veřejnou gateway,
API a MCP bez hostitelských portů, Postgres s persistentním volume a jednorázové
inicializační kroky. Veřejné Swagger/OpenAPI endpointy jsou vypnuté, mock
autentizace je při buildu zakázaná a kontejnery API/MCP neběží s reloadem.

### Coolify

1. Vytvoř Docker Compose resource z Git repozitáře. Nastav **Base Directory**
   `infra` a **Compose Location** `compose.prod.yml`. Build kontexty `..` v
   Compose souboru míří zpět do kořene repozitáře.
2. Přidej doménu ke službě **gateway** na interním portu `8080`. Zapni TLS/
   automatické HTTPS v Coolify; backendový Nginx zůstává za proxy na interní HTTP.
3. Proměnné z `production.env.example` nastav v Coolify jako šifrované proměnné
   resource. Produkční `.env` ani JSON service accountu necommituj.
4. Vygeneruj nové tajné hodnoty, nikoli vývojové defaulty:

   ```sh
   openssl rand -hex 32  # POSTGRES_PASSWORD
   openssl rand -hex 48  # JWT_SECRET_KEY
   ```

   Heslo databáze použij stejné v `POSTGRES_PASSWORD` i `DATABASE_URL`. Hexadecimální
   tvar nevyžaduje URL-encoding.

5. Nastav `GOOGLE_CLOUD_PROJECT`. Pro přihlášení k Vertex AI:
   - Pokud aplikace běží na Google Cloud VM, připoj jí service account s nejmenší
     potřebnou rolí. ADC použije metadata server; další klíč ani soubor není třeba.
   - Na běžném VPS preferuj Workload Identity Federation, pokud VPS nebo jiná
     runtime identita poskytuje OIDC/SAML tokeny. Credential configuration lze
     nastavit jako šifrovanou proměnnou `GOOGLE_ADC_JSON` v Coolify. WIF vyžaduje
     skutečného externího poskytovatele identity; Coolify sám takovou identitu
     automaticky nevytváří.
   - Pokud žádná připojená ani federovaná identita není dostupná, service-account
     JSON klíč je fallback, ne doporučená volba Googlu. Ulož ho pouze do šifrované
     proměnné `GOOGLE_ADC_JSON`; nikdy ho necommituj ani neposílej v chatu a účtu
     přiděl jen roli `Vertex AI User`.
6. Deploy. `db` automaticky ověří extensions, `api-init` aplikuje migrace a `etl`
   vytvoří prostorové schéma. API se spustí i bez Google credentials, ale volání
   Vertex AI bude fungovat až po konfiguraci ADC. Healthcheck databáze ověření
   Google autentizace nenahrazuje.

Google doporučuje ADC a federovanou identitu před dlouhodobými service-account
klíči: [ADC](https://cloud.google.com/docs/authentication/application-default-credentials),
[Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
a [správa service-account klíčů](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys).

Do Coolify vystav pouze `gateway:8080`. Databáze, API a MCP nemají publikované
porty; MCP endpoint není routovaný zvenku. `db_data` a `etl_data` jsou pojmenované
Docker volumes a přežívají běžné redeploye, ale **nejsou zálohou**.

### Data a provoz

První deploy vytvoří schéma, nikoli datové sady. Po deploy spusť jednorázový import
z kořene repozitáře na VPS (nebo ekvivalentním Coolify terminálem), se stejnými
proměnnými produkčního resource:

```sh
docker compose --env-file .env.production -f infra/compose.prod.yml \
  run --rm --no-deps etl python -m etl.main --all --keep-going
```

Import načítá veřejné zdroje, může trvat a některé zdroje mohou být nedostupné;
`--keep-going` zachová úspěšné vrstvy a neúspěchy vypíše. Neprovádí seed syntetických
dat ani nemaže existující tabulky. Zdraví ověř přes `https://<doména>/health` a
`https://<doména>/api/health/db`; Swagger a MCP zůstávají neveřejné.

Naplánuj pravidelné zálohy databáze mimo VPS a ověř obnovu. Například dump:

```sh
docker compose --env-file .env.production -f infra/compose.prod.yml exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > opendata-$(date +%F).dump
```

Ukládej zálohu šifrovaně mimo server, nastav retenční politiku a chraň také
credentials pro Vertex AI. Před nasazením můžeš syntaxi Compose ověřit lokálně
bez spuštění služeb:

```sh
docker compose --env-file .env.production -f infra/compose.prod.yml config --quiet
docker compose --env-file .env.production -f infra/compose.prod.yml build
```
