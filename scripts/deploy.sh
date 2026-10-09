#!/bin/sh
set -eu

# Resolve the Compose project from this script even when called elsewhere.
cd "$(dirname "$0")/.."

docker compose build bot worker
docker compose up -d --wait --wait-timeout 120 postgres redis
docker compose run --rm --no-deps bot alembic upgrade head
docker compose up -d bot worker
docker compose ps
