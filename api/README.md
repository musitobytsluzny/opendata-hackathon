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

Chat zatím vrací 503 do implementace datového/agentního backendu.
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
