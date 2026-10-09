# Pin the Python environment to ./.venv even when the shell exports a global UV_PROJECT_ENVIRONMENT.
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/.venv

.PHONY: install api web test test-backend test-web lint typecheck e2e openapi check-contracts

install: ## Install Python and Node toolchains (+ Playwright Chromium)
	uv sync
	cd apps/web && npm ci && npx playwright install chromium

api: ## Run the API on http://127.0.0.1:8765
	uv run numericos serve

web: ## Run the GUI dev server on http://localhost:5173
	cd apps/web && npm run dev

test: test-backend test-web

test-backend:
	uv run pytest

test-web:
	cd apps/web && npm test

lint:
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && npm run lint

typecheck:
	uv run mypy
	cd apps/web && npm run typecheck

e2e: ## Browser tests against a real API process
	cd apps/web && npm run e2e

openapi: ## Regenerate the public contract and the TypeScript types derived from it
	uv run numericos openapi --output contracts/openapi.v1.json
	cd apps/web && npm run gen:api

check-contracts: openapi ## Fail if committed contracts are stale
	git diff --exit-code -- contracts apps/web/src/api/schema.d.ts
