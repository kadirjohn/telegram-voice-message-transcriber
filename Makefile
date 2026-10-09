.PHONY: up deploy down logs ps migrate test lint lint-fix shell clean

# ── Docker Compose ───────────────────────────────────────────────────────

up:
	docker compose up --build -d

deploy:
	docker compose build bot worker
	docker compose up -d --wait --wait-timeout 120 postgres redis
	docker compose run --rm --no-deps bot alembic upgrade head
	docker compose up -d bot worker
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

restart:
	docker compose restart

# ── Database ─────────────────────────────────────────────────────────────

migrate:
	docker compose run --rm --no-deps bot alembic upgrade head

migrate-new:
	docker compose exec bot alembic revision --autogenerate -m "$(message)"

# ── Testing & Linting ───────────────────────────────────────────────────

test:
	docker compose run --rm bot pytest $(args)

test-local:
	pytest $(args)

lint:
	ruff check .

lint-fix:
	ruff check --fix .

format:
	ruff format .

# ── Worker Scaling ────────────────────────────────────────────────────────

worker-scale:
	docker compose up -d --scale worker=$(count)

# ── Shell ────────────────────────────────────────────────────────────────

shell:
	docker compose exec bot /bin/bash

# ── Cleanup ──────────────────────────────────────────────────────────────

clean:
	docker compose down -v
	docker system prune -f

# ── RQ Dashboard ─────────────────────────────────────────────────────────

dashboard:
	docker compose --profile monitoring up -d rq-dashboard
