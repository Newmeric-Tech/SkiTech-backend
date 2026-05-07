.PHONY: help install dev test lint format migrate run

## Development Tasks

help:
	@echo "Skitec FastAPI Backend - Development Commands"
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install dependencies"
	@echo "  make install-dev      Install dev dependencies"
	@echo ""
	@echo "Running:"
	@echo "  make dev              Start development server"
	@echo "  make run              Run production server"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test             Run tests"
	@echo "  make test-cov         Run tests with coverage"
	@echo "  make lint             Run linting checks"
	@echo "  make format           Format code with Black"
	@echo "  make type-check       Run mypy type checking"
	@echo ""
	@echo "Database:"
	@echo "  make migrate          Run migrations"
	@echo "  make migrate-create   Create new migration"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-up        Start Docker Compose"
	@echo "  make docker-down      Stop Docker Compose"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=app --cov-report=html

lint:
	pylint app/
	flake8 app/

format:
	black app/ tests/
	isort app/ tests/

type-check:
	mypy app/

migrate:
	alembic upgrade head

migrate-create:
	@read -p "Enter migration name: " name; \
	alembic revision --autogenerate -m "$$name"

docker-build:
	docker build -t skitec:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f
