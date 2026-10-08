"""Tests for the live index endpoint, through the real route, service and schemas."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.enums import MeasurementOrigin, Pollutant
from app.repositories import observation_repository
from app.repositories.session import get_db_session
from app.tests.services.test_live_index_service import ANAND_VIHAR, Row, row


@pytest.fixture
def api(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    rows = {
        Pollutant.PM25: [row(1, ANAND_VIHAR, 100.0, origin=MeasurementOrigin.WAQI)],
        Pollutant.PM10: [row(1, ANAND_VIHAR, 150.0, origin=MeasurementOrigin.WAQI)],
    }

    def latest(_session: Any, pollutant: Pollutant, *_: Any, **__: Any) -> list[Row]:
        return rows.get(pollutant, [])

    monkeypatch.setattr(observation_repository, "latest_reading_per_station", latest)

    def _no_database() -> Iterator[Any]:
        yield object()

    app.dependency_overrides[get_db_session] = _no_database
    with TestClient(app) as client:
        yield client


def test_states_each_monitors_index_and_where_it_came_from(api: TestClient) -> None:
    response = api.get("/v1/live-index", params={"city": "delhi"})

    assert response.status_code == 200
    body = response.json()
    assert body["station_count"] == 1
    assert "not published by CPCB" in body["basis"]
    [station] = body["stations"]
    assert station["dominant_pollutant"] == "pm25"
    assert set(station["sub_indices"]) == {"pm25", "pm10"}
    assert station["origins"] == ["waqi"]
    assert station["position"] == {"longitude": ANAND_VIHAR[0], "latitude": ANAND_VIHAR[1]}


def test_rejects_a_city_it_does_not_cover(api: TestClient) -> None:
    response = api.get("/v1/live-index", params={"city": "mumbai"})

    assert response.status_code == 422
