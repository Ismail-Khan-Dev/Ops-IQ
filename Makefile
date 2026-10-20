# ── OpsIQ Makefile ──────────────────────────────────────────
# Common development and production commands

.PHONY: help dev prod staging test lint clean build deploy dr dr-check dr-verify dr-restore dr-report

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ─────────────────────────────────────────────

dev: ## Start development stack (auto-merges override)
	docker compose up -d
	@echo "API: http://localhost:8000"
	@echo "Grafana: http://localhost:3003"
	@echo "Prometheus: http://localhost:9093"

dev-logs: ## Follow development logs
	docker compose logs -f api

dev-down: ## Stop development stack
	docker compose down

# ── Production ──────────────────────────────────────────────

prod: ## Start production stack
	bash scripts/deploy.sh up

prod-down: ## Stop production stack
	bash scripts/deploy.sh down

prod-status: ## Show production status
	bash scripts/deploy.sh status

prod-logs: ## Follow production logs
	bash scripts/deploy.sh logs

prod-backup: ## Create backup
	bash scripts/deploy.sh backup

# ── Testing ─────────────────────────────────────────────────

test: ## Run all tests (Python + Frontend)
	@echo "Running Python tests..."
	py -3 -m pytest tests/ -x -q --tb=short
	@echo "Running frontend tests..."
	cd frontend && npx vitest run

test-python: ## Run Python tests only
	py -3 -m pytest tests/ -x -q --tb=short

test-frontend: ## Run frontend unit tests only
	cd frontend && npx vitest run

test-e2e: ## Run Playwright E2E tests
	cd frontend && npx playwright test

test-coverage: ## Run tests with coverage
	py -3 -m pytest tests/ --cov=ecommerce_ops --cov-report=term-missing

# ── Linting ─────────────────────────────────────────────────

lint: ## Run all linters
	ruff check ecommerce_ops/
	cd frontend && npx next lint

lint-fix: ## Auto-fix lint issues
	ruff check ecommerce_ops/ --fix
	ruff format ecommerce_ops/
	cd frontend && npx next lint --fix

# ── Build ───────────────────────────────────────────────────

build: ## Build all Docker images
	docker compose build

build-api: ## Build API image only
	docker compose build api

build-frontend: ## Build frontend image only
	docker compose build dashboard

# ── Database ────────────────────────────────────────────────

db-migrate: ## Run Alembic migrations
	alembic upgrade head

db-revision: ## Create new migration (usage: make db-revision MSG="add users table")
	alembic revision --autogenerate -m "$(MSG)"

db-check: ## Check for migration drift
	bash scripts/check-migrations.sh

# ── Utilities ───────────────────────────────────────────────

clean: ## Remove Docker artifacts
	docker compose down -v --remove-orphans
	docker system prune -f
	@echo "Cleaned."

shell-api: ## Shell into API container
	docker compose exec api /bin/bash

shell-db: ## Shell into PostgreSQL
	docker compose exec postgres psql -U postgres ecommerce_ops

seed-demo: ## Seed database with demo data
	curl -s -X POST http://localhost:8000/api/demo/seed \
		-H "Authorization: Bearer opsiq-dev-key-2024" | python -m json.tool

# ── Staging ────────────────────────────────────────────────

staging: ## Start staging stack (parallel to prod)
	docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
	@echo "Staging API: http://localhost:8100"
	@echo "Staging Dashboard: http://localhost:3300"
	@echo "Staging Grafana: http://localhost:3004"

staging-down: ## Stop staging stack
	docker compose -f docker-compose.yml -f docker-compose.staging.yml down

staging-logs: ## Follow staging logs
	docker compose -f docker-compose.yml -f docker-compose.staging.yml logs -f api

# ── Disaster Recovery ───────────────────────────────────────

dr: dr-check ## Run DR health check (alias)

dr-check: ## Run DR health check
	bash scripts/disaster-recovery.sh check

dr-verify: ## Verify latest backup can be restored
	bash scripts/verify-backup.sh

dr-restore: ## Restore database from backup (interactive)
	bash scripts/restore-db.sh

dr-report: ## Generate DR status report
	bash scripts/disaster-recovery.sh report

dr-backup: ## Create backup + verify it
	bash scripts/backup-db.sh && bash scripts/verify-backup.sh
