# API: autentizace a oprávnění

Každý požadavek načte uživatele a jeho aktuální roli z databáze. Role není převzatá
z JWT: povýšení či odebrání práv platí hned i se stejným tokenem. Smazaný účet má 401. Chybějící/neplatné přihlášení vrací 401, nedostatečná práva 403.

| Endpoint                     | Bez přihlášení | user               | admin               |
| ---------------------------- | -------------- | ------------------ | ------------------- |
| POST /users/ (registrace)    | ano, vždy user | ano, vždy user     | ano, vždy user      |
| POST /auth/login             | ano            | ano                | ano                 |
| GET /auth/me                 | 401            | vlastní účet       | vlastní účet        |
| GET /users/                  | 401            | 403                | všichni uživatelé   |
| GET/PATCH/DELETE /users/{id} | 401            | pouze vlastní účet | libovolný účet      |
| PATCH /users/{id}/role       | 401            | 403                | přiřadit user/admin |
| POST /chat/ask               | 401            | ano                | ano                 |

Chat používá Gemini přes bezpečný MCP tool loop; konfigurace a limity jsou níže.
Healthchecky a OpenAPI dokumentace zůstávají veřejné pro vývojovou infrastrukturu.

Registrace a běžná editace role nepřijímají; pokus přidat `role` do těla vrátí 422.
Povolené hodnoty omezuje i DB constraint. Existující i noví uživatelé dostávají
výchozí roli `user`. Žádný účet se nestává administrátorem automaticky.

## První administrátor

Zaregistruj účet přes UI a z důvěryhodného shellu v kořeni repozitáře spusť:

```sh
docker compose exec api python manage_admin.py UZIVATELSKE_JMENO
```

Příkaz vyžaduje existující účet, heslo ani JWT nemění. Další správu rolí může
administrátor dělat přes Swagger s vlastním Bearer tokenem. Povýšení není
součástí ETL a neexistuje veřejný bootstrap endpoint.

## Migrace a testy

`make up` aplikuje migrace přes službu `api-init` před ETL a startem API.
Úprava modelů sama schéma nemění; přidej Alembic revizi. Původní tabulky se při
prvním přechodu převezmou bez mazání dat; neznámé částečné schéma zastaví start.

```sh
make test-api
make smoke
```

RBAC testy volají běžící API a odstraní pouze své vlastní fixture účty. Migrační
testy používají náhodně pojmenovaná PostgreSQL schémata a po doběhu je smažou.
Spouštěj je na vývojové databázi, nikoliv na produkci.

## Gemini a MCP

Výchozí režim je Gemini Developer API: do kořenového `.env` vlož `GEMINI_API_KEY`
a případně `GEMINI_MODEL`. Klíč se předává pouze kontejneru API, ne webu, MCP,
ETL ani `api-init`; není součástí Docker buildu, Git historie ani
odpovědí/logovaných chyb.

```sh
make up
make check-gemini # explicitní malé živé volání; používá kvótu účtu
```

Pro Google Cloud Vertex AI s ADC místo Developer API klíče:

1. Zapni Vertex AI API v Google Cloud projektu s aktivním billingem a uděl
   přihlašovací identitě roli `Vertex AI User`.
2. Na hostiteli spusť `gcloud auth application-default login`.
3. V `.env` nastav `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` a
   `GOOGLE_ADC_HOST_PATH` na absolutní cestu k hostitelskému souboru
   `application_default_credentials.json` (typicky
   `/Users/<uživatel>/.config/gcloud/application_default_credentials.json`).
4. Spusť `make up-cloud`. Tento Compose override nastaví Vertex režim, klíč
   Developer API do kontejneru nepředá a připojí ADC soubor jen pro čtení.
   Ověření živým požadavkem: `make check-gemini-cloud`.

Výchozí `make up` zůstává v režimu Developer API. Model musí být dostupný
v nastavené lokaci Google Cloud. Nikdy nekopíruj ADC soubor do repozitáře.

Tok je web → autentizované `POST /api/chat/ask` → Gemini → MCP → chráněné
`/api/data/*` → PostGIS. Každý MCP požadavek předá vlastní uživatelský JWT,
nepoužívá sdílenou identitu uživatelů a token se neposílá Googlu.
Google dostává otázku, nejvýše deset textových zpráv historie a omezené výsledky
čtecích nástrojů. Uživatelské účty, hesla ani seznam uživatelů nejsou nástroji dostupné.

Povolené nástroje: katalog načtených datasetů, okresní agregace dostupných obcí,
orientační kontrola konkrétního bodu a parcely. Model nemůže spouštět SQL,
zápisy, změny rolí ani libovolné akce. SQL má pevné šablony a read-only transakci.
Mapové hodnoty a příznak demo dat pocházejí z nástrojů, nikoliv z textu modelu.
Chybějící okres není nula; agregace nemusí pokrývat všechny obce okresu.
Bez ETL dat model musí přiznat omezení, ne generovat statistiky.

Konfigurace: `MCP_SERVER_URL`, `GEMINI_TIMEOUT_SECONDS` (celý běh, výchozí 60 s),
`GEMINI_MAX_OUTPUT_TOKENS` (2048), `LLM_MAX_CONCURRENT` (4 na API proces).
Jeden uživatel smí mít jeden souběžný chatový požadavek. Běh má nejvýše šest
modelových kol a dvanáct volání nástrojů. Google se při chybě automaticky neopakuje.
Kvóta vrací 429, časový limit 504, chybějící konfigurace/MCP 503; provider detaily se
klientovi neposílají. `GET /api/chat/status` vrací jen boolean `configured`.

`make test-api` a `make test-mcp` testují klienta bez skutečných Google credentials;
CI neprovádí placená živá volání. MCP bridge a čtecí dotazy se testují vůči DB.
SDK: [Google Gen AI Python](https://googleapis.github.io/python-genai/).
