# Every routine command lives here, so README, CI and your terminal agree.
# Run `make help` for the list.

SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE := docker compose
PYTEST_COV := --cov=app --cov=resume_engine --cov=resume_ml --cov-report=term-missing --cov-report=xml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	@echo "Missing .env. Run: cp .env.example .env" && exit 1

# ---------------------------------------------------------------- stack
.PHONY: up down down-volumes logs ps
up: .env ## Build and start the stack; return once every service is healthy
	$(COMPOSE) up -d --build --wait --wait-timeout 180

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) down

down-volumes: ## Stop the stack AND delete all local data (Postgres, Redis, storage)
	$(COMPOSE) down -v

logs: ## Follow logs of all services
	$(COMPOSE) logs -f

ps: ## Show service status and health
	$(COMPOSE) ps

# ---------------------------------------------------------------- python
.PHONY: install lint fmt typecheck test test-integration check
install: ## Install the locked Python environment (all workspace packages + dev tools)
	uv sync --locked --all-packages

lint: ## Lint and check formatting (no changes)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix lint issues and format code
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy --strict on engine/src and backend/app
	uv run mypy

test: ## Unit tests with coverage (no services needed)
	uv run pytest -m "not integration" $(PYTEST_COV) --cov-fail-under=70

test-integration: ## Integration tests against the running stack (run `make up` first)
	uv run pytest -m integration

check: lint typecheck test ## Everything CI's unit job runs

# ---------------------------------------------------------------- ml
.PHONY: data splits label label-down label-tasks label-import evaluate
data: ## Verify the Kaggle archive, extract PDFs, write records and the profile report
	uv run resume-ml data

splits: ## Create the frozen gold/train split file (once; refuses to overwrite)
	uv run resume-ml splits

label: .env ## Start Label Studio at http://localhost:8081
	$(COMPOSE) --profile labeling up -d label-studio
	@echo "Label Studio: http://localhost:$${LABEL_STUDIO_PORT:-8081}  (login from .env)"

label-down: ## Stop Label Studio (labels are kept in its volume)
	$(COMPOSE) --profile labeling stop label-studio

label-tasks: ## Write data/labeling/gold_tasks.json to import into Label Studio
	uv run resume-ml label-tasks

label-import: ## Validate an export: make label-import EXPORT=path/to/export.json [PARTIAL=1]
	@test -n "$(EXPORT)" || (echo "usage: make label-import EXPORT=path/to/export.json" && exit 1)
	uv run resume-ml label-import "$(EXPORT)" $(if $(PARTIAL),--partial,)

evaluate: ## Reproduce the gold-set evaluation (arrives in M3)
	@echo "evaluate: not implemented yet (milestone M3)" && exit 1
