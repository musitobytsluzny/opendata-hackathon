COMPOSE = docker compose --env-file .env -f infra/compose.dev.yml
COMPOSE_CLOUD = $(COMPOSE) -f infra/compose.cloud.yml

.PHONY: setup up up-cloud down logs ps build seed config config-cloud lint format check smoke test-api test-etl test-mcp check-gemini check-gemini-cloud import-data validate-demo refresh-landing

setup:
	@test -f .env || cp .env.example .env

up: setup
	$(COMPOSE) up -d --build --wait

up-cloud: setup
	$(COMPOSE_CLOUD) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps -a

build: setup
	$(COMPOSE) build

seed: setup
	$(COMPOSE) up -d --build --wait db api-init
	$(COMPOSE) run --rm --build --no-deps etl python -m etl.main --seed

import-data: setup
	$(COMPOSE) run --rm --no-deps etl python -m etl.main --all --keep-going

config: setup
	$(COMPOSE) config --quiet

config-cloud: setup
	$(COMPOSE_CLOUD) config --quiet

lint: setup
	$(COMPOSE) run --rm --build --no-deps quality-python
	$(COMPOSE) run --rm --build --no-deps quality-web

format: setup
	$(COMPOSE) run --rm --build --no-deps quality-python sh -c 'ruff check --fix . && ruff format .'
	$(COMPOSE) run --rm --build --no-deps quality-web /app/node_modules/.bin/prettier --write .

check: config lint
	$(COMPOSE) run --rm --no-deps quality-web npm --prefix /app run build

smoke: setup
	BASE_URL="http://$$($(COMPOSE) port nginx 80)" python3 infra/smoke.py

test-api: setup
	$(COMPOSE) exec -T api python -m unittest discover -s tests -v

test-etl: setup
	$(COMPOSE) run --rm --no-deps etl python -m unittest discover -s etl/tests -v

test-mcp: setup
	$(COMPOSE) exec -T mcp python -m unittest discover -s tests -v

check-gemini: setup
	$(COMPOSE) exec -T api python -m scripts.check_gemini

check-gemini-cloud: setup
	$(COMPOSE_CLOUD) exec -T api python -m scripts.check_gemini

# Opt-in: uses the configured Gemini quota and real MCP/data services.
validate-demo: setup
	$(COMPOSE) exec -T api python -m scripts.validate_demo

# Real public-place data and routes, exported without using private chat history.
refresh-landing: setup
	$(COMPOSE) exec -T api python -m scripts.export_landing_examples | node web/scripts/update-landing-examples.mjs
