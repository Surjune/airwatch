"""Database engine and session management.

The only module that constructs an engine. Everything else receives a session,
so a caller cannot accidentally open a second connection pool.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Connections held open in the pool.
_POOL_SIZE = 5

#: Extra connections opened under load before requests start queueing.
_MAX_OVERFLOW = 10

#: Seconds a connection may sit idle before being recycled, which keeps the pool
#: from handing out sockets a proxy has already dropped.
_POOL_RECYCLE_SECONDS = 1800


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide engine."""
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        pool_recycle=_POOL_RECYCLE_SECONDS,
        # Verifies a connection is alive before use. Without it the first query
        # after an idle period fails on a stale socket rather than reconnecting.
        pool_pre_ping=True,
        future=True,
    )
    logger.info("database.engine_created", pool_size=_POOL_SIZE)
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session, committing on success.

    Rolls back on any exception before re-raising, so a partially applied
    ingestion batch never survives a failure. Used by workers and scripts; the
    API uses :func:`get_db_session` instead.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with session_scope() as session:
        yield session
