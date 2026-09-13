# AirWatch API and worker image. Build from the repository root:
#   docker build -f backend/Dockerfile -t airwatch-api .
#
# The same image runs the API, the hourly worker and the one-off migration step;
# only the command differs, so all three always run identical code.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The application resolves infra/seed and infra/fixtures relative to the
# repository root, so the image keeps the repository's layout.
WORKDIR /srv/airwatch/backend

# Dependencies first, so a code change does not reinstall them.
COPY backend/pyproject.toml ./
RUN python -m pip install --upgrade pip \
    && mkdir -p app \
    && touch app/__init__.py \
    && pip install . \
    && rm -rf app build *.egg-info

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY infra/seed /srv/airwatch/infra/seed
COPY infra/fixtures /srv/airwatch/infra/fixtures

# Never run as root: a compromise of the API should not own the container.
RUN useradd --system --uid 10001 --home-dir /srv/airwatch airwatch \
    && chown -R airwatch:airwatch /srv/airwatch
USER airwatch

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4).status == 200 else 1)"

# --proxy-headers makes the rate limiter see each visitor's address rather than
# the reverse proxy's. Only Caddy can reach this port, on the private compose
# network, so trusting its forwarded headers is safe.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
