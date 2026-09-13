"""Tests for the satellite endpoint, with the service's database queries stubbed."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.enums import PilotCity, SatelliteProduct
from app.repositories import satellite_repository
from app.repositories.satellite_repository import DailyMean
from app.repositories.session import get_db_session
from app.services import satellite_service

DAY = date(2026, 9, 12)


class _Row:
    def __init__(self, cell: str) -> None:
        self.h3_cell = cell
        self.observed_on = DAY
        self.value = 5.7e-5
        self.pixel_count = 42


@pytest.fixture
def api(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def latest(_: Any, cells: list[str], *__: Any) -> list[_Row]:
        return [_Row(cells[0])]

    monkeypatch.setattr(satellite_repository, "latest_per_cell", latest)
    monkeypatch.setattr(
        satellite_repository,
        "daily_means",
        lambda *a, **k: [DailyMean(observed_on=DAY, value=5.7e-5, cells=120)],
    )

    def _no_database() -> Iterator[object]:
        yield object()

    app.dependency_overrides[get_db_session] = _no_database
    with TestClient(app) as client:
        yield client


def test_returns_the_series_and_the_latest_cells_with_outlines(api: TestClient) -> None:
    body = api.get("/v1/satellite", params={"city": "coimbatore", "product": "no2"}).json()

    assert body["unit"] == "mol/m2"
    assert "Sentinel-5P" in body["source"]
    assert body["series"] == [{"observed_on": "2026-09-12", "value": 5.7e-5, "cells": 120}]
    cell = body["cells"][0]
    assert cell["h3_cell"] in satellite_service.city_cells(PilotCity.COIMBATORE)
    assert len(cell["boundary"]) == 6
    # Outlines are (lon, lat) and Coimbatore sits near 77E, 11N.
    assert 76.0 < cell["boundary"][0]["longitude"] < 78.0
    assert 10.0 < cell["boundary"][0]["latitude"] < 12.0


def test_every_product_is_served(api: TestClient) -> None:
    for product in SatelliteProduct:
        response = api.get("/v1/satellite", params={"city": "delhi", "product": product.value})
        assert response.status_code == 200


def test_requires_a_city_and_rejects_an_unknown_one(api: TestClient) -> None:
    assert api.get("/v1/satellite").status_code == 422
    assert api.get("/v1/satellite", params={"city": "mumbai"}).status_code == 422
