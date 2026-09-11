"""Database fixtures for repository integration tests.

These tests need a real PostgreSQL with PostGIS. Nothing else can answer whether
``DISTINCT ON`` returns one row per station, whether ``ON CONFLICT`` makes a
second ingestion converge, or whether ``ST_X`` yields longitude rather than
latitude -- and those are exactly the claims the repository layer makes.

When no database is reachable the whole package skips, so a clean clone with no
container running still runs the suite green. The skip is reported rather than
silent: an untested repository layer should be visible in the output.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.models import Base

#: Where the integration database lives. Overridable so CI can point at its own
#: service container without editing the suite.
TEST_DATABASE_URL = os.environ.get(
    "AIRWATCH_TEST_DATABASE_URL",
    "postgresql+psycopg://airwatch:airwatch@localhost:5433/airwatch_test",
)

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
        pytest.skip(f"no PostgreSQL with PostGIS at {TEST_DATABASE_URL}: {error}")

    # Tables are built from the ORM metadata rather than by running Alembic.
    # The migrations are the deployment path and are exercised by deploying;
    # what these tests need is a schema matching the models they query.
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
