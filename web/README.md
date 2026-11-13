# Web

React, TypeScript a Vite. Konfigurace se načítá z kořenového `.env`, lokální
`web/.env` se nepoužívá. Do klienta Vite předává pouze `VITE_*` proměnné.

Pro celý stack používej `make up` v kořeni repozitáře. Nginx zajišťuje `/api/`
a `/mcp/`; otevři http://localhost:8080/. Login výchozí konfigurace volá skutečné
API. Mock režim se zapíná přes `VITE_USE_MOCK_AUTH=true` v kořenovém `.env`.

```sh
npm ci --prefix web
npm run lint --prefix web
npm run format:check --prefix web
npm run build --prefix web
```

Formátování používá společnou kořenovou konfiguraci Prettieru; Python řeší Ruff.
Kontroly celého repozitáře včetně Dockeru: `make check`.

Stránky a MapLibre se načítají samostatně; mapa se aktivuje až při zobrazení.
Obnovení přihlášení ověřuje `GET /api/auth/me`. Registrace volá `/api/users/`
a následně `/api/auth/login`; mock je pouze explicitní volba v root `.env`.
Chat volá autentizovaný `POST /api/chat/ask` s omezenou textovou historií.
Backend používá Gemini a MCP; mapová čísla čte z DB. Klíč Gemini není ve webu.
Ukázky na landing page zůstávají označené a chyby kvóty/timeoutu se zobrazí v chatu.
