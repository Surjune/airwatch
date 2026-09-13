"""Shared test fixtures.

Tests never make real network calls and never read the developer's own ``.env``.
Every fixture here builds its configuration explicitly so a test result cannot
depend on what happens to be in the local environment.

The database fixtures at the bottom serve the tests marked ``integration``.
Those need a real PostgreSQL with PostGIS, because DISTINCT ON, ON CONFLICT,
ST_Contains and ST_X have no stand-in. They skip with a reported reason when no
database is reachable, so a clean clone still runs the suite green.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.repositories.models import Base


@pytest.fixture
def settings() -> Settings:
    """Settings with no upstream credentials configured.

    The absence is deliberate: it is the state a fresh clone starts in, and every
    code path must degrade to an explicit typed error rather than to invented
    data.
    """
    return Settings(
        environment="test",
        log_level="WARNING",
        database_url="postgresql+psycopg://airwatch:airwatch@localhost:5433/airwatch_test",
        redis_url="redis://localhost:6380/1",
        openaq_api_key="",
        cpcb_api_key="",
        firms_map_key="",
        gee_service_account_email="",
        gee_private_key_path="",
    )


@pytest.fixture
def configured_settings(settings: Settings) -> Settings:
    """Settings with placeholder credentials, for exercising the configured path."""
    return settings.model_copy(
        update={
            "openaq_api_key": "test-openaq-key",
            "cpcb_api_key": "test-cpcb-key",
            "firms_map_key": "test-firms-key",
        }
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An application instance built from the test settings."""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """An HTTP client bound to the test application."""
    with TestClient(app) as test_client:
        yield test_client


#: Where the integration database lives. Overridable so CI can point at its own
#: service container without editing the suite.
TEST_DATABASE_URL = os.environ.get(
    "AIRWATCH_TEST_DATABASE_URL",
    "postgresql+psycopg://airwatch:airwatch@localhost:5433/airwatch_test",
)

#: Set in CI to turn an unreachable database from a skip into a failure. Locally
#: a skip keeps a clean clone green; in CI it would let the integration suite
#: silently not run while the build still reported success.
REQUIRE_DATABASE = os.environ.get("AIRWATCH_REQUIRE_DATABASE", "").lower() in {"1", "true", "yes"}

#: The maintenance database used only to create the test database itself.
_ADMIN_DATABASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"

#: Name of the database these tests own outright, and will drop tables in. Kept
#: distinct from the development database so a test run can never destroy
#: ingested data.
_TEST_DATABASE_NAME = TEST_DATABASE_URL.rsplit("/", 1)[1]


def _ensure_database() -> None:
    """Create the test database and its PostGIS extension if absent."""
    admin = create_engine(_ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": _TEST_DATABASE_NAME},
        ).scalar_one_or_none()
        if exists is None:
            # The identifier cannot be bound as a parameter, so it is taken from
            # the configured URL rather than from anything a test supplies.
            connection.execute(text(f'CREATE DATABASE "{_TEST_DATABASE_NAME}"'))
    admin.dispose()

    target = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with target.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    target.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """An engine against the integration database, or skip if unreachable."""
    try:
        _ensure_database()
        created = create_engine(TEST_DATABASE_URL)
        with created.connect():
            pass
    except SQLAlchemyError as error:
        message = f"no PostgreSQL with PostGIS at {TEST_DATABASE_URL}: {error}"
        if REQUIRE_DATABASE:
            # In CI a skip would be indistinguishable from a pass at a glance, and
            # the database tests are the ones that cover the SQL. Failing loudly is
            # the only way to be sure they actually ran.
            pytest.fail(message)
        pytest.skip(message)

    # Tables are built from the ORM metadata rather than by running Alembic.
    # The migrations are the deployment path; what these tests need is a schema
    # matching the models they query.
    #
    # Dropped first, every session. create_all does not alter an existing table,
    # so a column added to a model would simply never appear in a test database
    # created before it -- and the suite would fail against a schema no
    # deployment will ever have. This database is owned outright by the suite,
    # which is why dropping it is safe and why it is a separate database from
    # the development one.
    Base.metadata.drop_all(created)
    Base.metadata.create_all(created)
    yield created
    created.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back when the test ends.

    Each test runs inside a transaction that is never committed, so tests cannot
    see each other's rows and the database is left as it was found.
    """
    connection = engine.connect()
    transaction = connection.begin()
    open_session = Session(bind=connection, expire_on_commit=False)
    try:
        yield open_session
    finally:
        open_session.close()
        transaction.rollback()
        connection.close()
