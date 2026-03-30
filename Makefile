.PHONY: help install install-dev run migrate makemigrations shell test test-cov lint \
        type-check security-check docker-up docker-down docker-logs docker-build \
        celery-worker celery-beat celery-flower clean generate-jwt-keys

# Default target
help:
	@echo "SocialOS — Available Commands"
	@echo "========================================"
	@echo "  install          Install production dependencies"
	@echo "  install-dev      Install all dependencies (incl. dev extras)"
	@echo "  run              Start Django development server"
	@echo "  migrate          Apply database migrations"
	@echo "  makemigrations   Create new migrations"
	@echo "  shell            Start Django interactive shell (IPython)"
	@echo "  test             Run test suite"
	@echo "  test-cov         Run tests with coverage report"
	@echo "  lint             Run ruff linter"
	@echo "  type-check       Run mypy type checker"
	@echo "  security-check   Run bandit + safety"
	@echo "  docker-up        Start all services via docker-compose"
	@echo "  docker-down      Stop all services"
	@echo "  docker-logs      Tail logs from all containers"
	@echo "  docker-build     (Re)build Docker images"
	@echo "  celery-worker    Start Celery worker (publish queue)"
	@echo "  celery-beat      Start Celery Beat scheduler"
	@echo "  celery-flower    Start Flower monitoring dashboard"
	@echo "  generate-jwt-keys Generate RS256 key pair for JWT"
	@echo "  clean            Remove __pycache__, .pyc, coverage artefacts"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
run:
	DJANGO_SETTINGS_MODULE=socialos.settings.development \
	python manage.py runserver 0.0.0.0:8000

run-asgi:
	DJANGO_SETTINGS_MODULE=socialos.settings.development \
	uvicorn socialos.asgi:application --host 0.0.0.0 --port 8000 --reload

migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations

shell:
	python manage.py shell_plus --ipython 2>/dev/null || python manage.py shell

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test:
	pytest $(filter-out $@,$(MAKECMDGOALS))

test-cov:
	pytest --cov=apps --cov=utils --cov-report=term-missing --cov-report=html --cov-fail-under=80

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------
lint:
	ruff check apps/ socialos/ utils/ --fix

format:
	ruff format apps/ socialos/ utils/

type-check:
	mypy apps/ socialos/ utils/ --ignore-missing-imports

security-check:
	bandit -r apps/ socialos/ utils/ -ll
	safety check

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down

docker-logs:
	docker compose -f docker/docker-compose.yml logs -f

docker-build:
	docker compose -f docker/docker-compose.yml build --no-cache

docker-restart:
	docker compose -f docker/docker-compose.yml restart

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
celery-worker:
	celery -A socialos worker -Q publish,scheduler,notifications,ai,analytics,reports,audit \
		--concurrency=4 --loglevel=info

celery-beat:
	celery -A socialos beat --scheduler django_celery_beat.schedulers:DatabaseScheduler \
		--loglevel=info

celery-flower:
	celery -A socialos flower --port=5555

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
generate-jwt-keys:
	@echo "Generating RS256 key pair..."
	openssl genrsa -out jwt_private.pem 2048
	openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
	@echo "Keys generated: jwt_private.pem, jwt_public.pem"
	@echo "Add their contents to .env as JWT_PRIVATE_KEY and JWT_PUBLIC_KEY"
	@echo "Remember: replace newlines with \\n in the .env value"

generate-encryption-key:
	@python -c "import secrets; print('TOKEN_ENCRYPTION_KEY=' + secrets.token_hex(32))"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache

%:
	@:
