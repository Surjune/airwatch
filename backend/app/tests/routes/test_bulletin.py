"""Tests for the daily bulletin endpoint, through the real route, service and schemas."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.enums import Pollutant
from app.repositories import bulletin_repository
from app.repositories.bulletin_repository import BulletinRow
from app.repositories.session import get_db_session

KANPUR = BulletinRow("Kanpur", date(2026, 10, 8), 44, "Good", (Pollutant.PM25, Pollutant.NO2), 2, 4)


@pytest.fixture
def api(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(
        bulletin_repository,
        "latest_for_city",
        lambda _session, city: KANPUR if city == "Kanpur" else None,
    )

    def _no_database() -> Iterator[Any]:
        yield object()

    app.dependency_overrides[get_db_session] = _no_database
    with TestClient(app) as client:
        yield client


def test_serves_the_citys_line_with_when_its_average_ran_to(api: TestClient) -> None:
    response = api.get("/v1/bulletin", params={"city": "kanpur"})

    assert response.status_code == 200
    line = response.json()["bulletin"]
    assert (line["aqi"], line["category"]) == (44, "Good")
    assert line["prominent_pollutants"] == ["pm25", "no2"]
    assert (line["stations_reporting"], line["stations_total"]) == (2, 4)
    assert line["averaged_until"] == "2026-10-08T10:30:00Z"
    assert line["source_url"] == "https://cpcb.gov.in/upload/Downloads/AQI_Bulletin_20261008.pdf"


def test_a_city_with_no_stored_line_has_a_null_bulletin(api: TestClient) -> None:
    response = api.get("/v1/bulletin", params={"city": "coimbatore"})

    assert response.status_code == 200
    assert response.json()["bulletin"] is None
