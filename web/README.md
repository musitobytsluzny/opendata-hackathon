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
