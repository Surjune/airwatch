#!/usr/bin/env bash
# Build and (re)start AirWatch on the server. Run from anywhere:
#   bash ~/airwatch/infra/deploy/deploy.sh            # deploy the latest main
#   bash ~/airwatch/infra/deploy/deploy.sh --first-load  # also backfill data
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"
COMPOSE=(docker compose -f infra/docker-compose.prod.yml --env-file .env)

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

for required in SITE_ADDRESS POSTGRES_PASSWORD OPERATOR_API_KEY; do
  if ! grep -Eq "^${required}=.+" .env; then
    echo "Set ${required} in .env before deploying." >&2
    exit 1
  fi
done

say "Updating code"
git pull --ff-only

# The API image runs as uid 10001 (backend/Dockerfile), so a key copied in with
# scp as ubuntu is unreadable inside the container until it is handed over.
if [ -d secrets ] && [ -n "$(sudo ls -A secrets)" ]; then
  say "Granting the containers read access to secrets/"
  sudo chown -R 10001:10001 secrets
  sudo chmod 700 secrets
  sudo find secrets -type f -exec chmod 600 {} +
fi

say "Building images"
"${COMPOSE[@]}" build

say "Starting the stack (migrations and seeding run first)"
"${COMPOSE[@]}" up -d --remove-orphans

say "Waiting for the API to become healthy"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3)" >/dev/null 2>&1; then
    echo "API is healthy."
    break
  fi
  sleep 5
done

# The spoken guide is fixed text, so its audio is generated once here rather
# than while a listener waits. Paragraphs already stored cost nothing.
if grep -Eq "^SARVAM_API_KEY=.+" .env; then
  say "Preparing the spoken guide"
  "${COMPOSE[@]}" exec -T api python -m app.cli voice-guide || true
fi

if [ "${1:-}" = "--first-load" ]; then
  say "Loading history: stations, 14 days of PM2.5 and PM10, official AQI, satellite"
  for city in delhi kanpur coimbatore; do
    "${COMPOSE[@]}" run --rm api python -m app.cli ingest --city "$city" || true
    for pollutant in pm25 pm10; do
      "${COMPOSE[@]}" run --rm api python -m app.cli backfill --city "$city" --pollutant "$pollutant" || true
    done
    "${COMPOSE[@]}" run --rm api python -m app.cli official-aqi --city "$city" || true
    "${COMPOSE[@]}" run --rm api python -m app.cli satellite --city "$city" || true
    "${COMPOSE[@]}" run --rm api python -m app.cli regional-model --city "$city" || true
  done
  say "Checking detection against the recorded episode"
  "${COMPOSE[@]}" run --rm api python -m app.cli replay --event delhi-anand-vihar-august || true
fi

say "Done"
"${COMPOSE[@]}" ps
