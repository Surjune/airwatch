"""Shared test fixtures.

Tests never make real network calls and never read the developer's own ``.env``.
Every fixture here builds its configuration explicitly so a test result cannot
depend on what happens to be in the local environment.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


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
