.PHONY: bootstrap plane-up up down restart logs logs-gateway logs-mcp health \
        test test-unit test-integration ask mobile-run mobile-test mobile-apk \
        submodules

PROJECT     := plane-assistant
ENV_FILE    := .env
COMPOSE     := docker compose -p $(PROJECT) --env-file $(ENV_FILE)
GPU_FILE    := $(if $(GPU),-f docker-compose.gpu.yml,)

# ---------------------------------------------------------------------------
# Bootstrap / Plane's two-phase startup (see plane/README.md)
# ---------------------------------------------------------------------------

bootstrap: ## Create .env, generate a gateway token, init submodules
	./scripts/bootstrap.sh

submodules: ## (Re-)initialize vendored git submodules
	git submodule update --init --recursive

plane-up: $(ENV_FILE) ## Phase 1: start only Plane so you can create a workspace + API key
	$(COMPOSE) -f plane/docker-compose.yml up -d
	@echo "Plane starting -- open http://localhost:8080 once healthy, then see plane/README.md."

# ---------------------------------------------------------------------------
# Full stack
# ---------------------------------------------------------------------------

up: $(ENV_FILE) check-plane-configured ## Phase 2: start everything else (requires plane-up + Plane bootstrap first)
	$(COMPOSE) -f docker-compose.yml $(GPU_FILE) up -d

down: ## Stop and remove every container in the stack
	$(COMPOSE) -f docker-compose.yml down

restart: down up ## Restart the full stack

logs: ## Tail logs for every service
	$(COMPOSE) -f docker-compose.yml logs -f

logs-gateway: ## Tail gateway logs only
	$(COMPOSE) -f docker-compose.yml logs -f gateway

logs-mcp: ## Tail plane-mcp logs only
	$(COMPOSE) -f docker-compose.yml logs -f plane-mcp

health: ## Run scripts/healthcheck.sh against the running stack
	./scripts/healthcheck.sh

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test: test-unit test-integration ## Run the full gateway test suite

test-unit: ## Gateway unit tests: config, prompts, agents, sessions, speech clients
	docker run --rm -v "$(CURDIR)/gateway:/app" -v "$(CURDIR)/prompts:/app/prompts:ro" -w /app python:3.11-slim \
		sh -c "pip install --quiet -e '.[dev]' >/dev/null && python -m pytest -q \
			--ignore=tests/test_api_query.py --ignore=tests/test_api_audio.py \
			--ignore=tests/test_api_errors.py --ignore=tests/test_app_lifespan.py"

test-integration: ## Gateway API-level tests (FastAPI TestClient + mocked CLI/STT/TTS)
	docker run --rm -v "$(CURDIR)/gateway:/app" -w /app python:3.11-slim \
		sh -c "pip install --quiet -e '.[dev]' >/dev/null && python -m pytest -q \
			tests/test_api_query.py tests/test_api_audio.py tests/test_api_errors.py \
			tests/test_app_lifespan.py"

# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

ask: ## make ask QUERY="list all my projects"
	./scripts/ask-plane.sh "$(QUERY)"

mobile-run: ## Run the Flutter app on a connected device/emulator
	cd mobile && flutter run

mobile-test: ## Run Flutter unit/widget tests
	cd mobile && flutter test

mobile-apk: ## Build a release APK via the reproducible Docker build
	cd mobile && docker compose run --rm mobile-build

# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

$(ENV_FILE):
	@echo "$(ENV_FILE) not found -- run 'make bootstrap' first." >&2
	@exit 1

check-plane-configured:
	@slug=$$(grep -E '^PLANE_WORKSPACE_SLUG=' $(ENV_FILE) | cut -d= -f2-); \
	key=$$(grep -E '^PLANE_API_KEY=' $(ENV_FILE) | cut -d= -f2-); \
	if [ -z "$$slug" ] || [ -z "$$key" ]; then \
		echo "PLANE_WORKSPACE_SLUG / PLANE_API_KEY are not set in $(ENV_FILE)." >&2; \
		echo "Run 'make plane-up', complete Plane's Phase 1 bootstrap (see plane/README.md)," >&2; \
		echo "fill both values into $(ENV_FILE), then re-run 'make up'." >&2; \
		exit 1; \
	fi
