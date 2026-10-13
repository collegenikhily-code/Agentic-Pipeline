# M1: seo-aeo-geo-pipeline Makefile
#
# Targets:
#   make install      - install package + dependencies
#   make test         - run unit tests (no PostgreSQL)
#   make integration  - run integration tests (Docker PostgreSQL)
#   make lint         - run ruff linting
#   make migrate      - apply PostgreSQL migrations
#   make reset-db     - drop and recreate test schema

.PHONY: install test integration lint migrate reset-db help

install:  ## Install package and M1 dependencies
	@echo "Installing seo-aeo-geo-pipeline..."
	@pip install -e .
	@echo "Installation complete."

test:  ## Run unit tests (no PostgreSQL required)
	@echo "Running unit tests..."
	@pytest tests/ -m unit -v
	@echo "Unit tests complete."

integration:  ## Run integration tests (Docker PostgreSQL required)
	@echo "Running integration tests..."
	@pytest tests/ -m integration -v
	@echo "Integration tests complete."

lint:  ## Run linting
	@echo "Running ruff linting..."
	@ruff check src/ tests/
	@echo "Linting complete."

migrate:  ## Apply PostgreSQL migrations
	@echo "Applying database migrations..."
	@if [ -f migrations/versions/001_initial_schema.up.sql ]; then \
		echo "Running migration 001 initial schema..."; \
		# In production, use: alembic upgrade head or psql < migrations/versions/001_initial_schema.up.sql
		psql "$(POSTGRES_URL)" < migrations/versions/001_initial_schema.up.sql || \
		psql "postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)" < migrations/versions/001_initial_schema.up.sql; \
	fi
	@echo "Migration complete."

reset-db:  ## Drop and recreate test database schema
	@echo "Resetting test database..."
	@psql "postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@$(MAKE) migrate
	@echo "Database reset complete."

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "} {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'