COMPOSE = docker compose --env-file .env -f infra/compose.dev.yml

.PHONY: setup up down logs ps build seed config lint format check smoke test-api test-etl

setup:
	@test -f .env || cp .env.example .env

up: setup
	$(COMPOSE) up -d --build --wait

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

config: setup
	$(COMPOSE) config --quiet

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
