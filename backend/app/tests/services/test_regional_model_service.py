"""Tests for storing the CAMS model and viewing it beside a city's monitors."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import CAMS_BASE_URL, CAMS_VARIABLES, PILOT_CITY_CENTRES
from app.core.enums import PilotCity, Pollutant, StationTier
from app.repositories import model_repository, observation_repository, station_repository
from app.repositories.model_repository import ModelRow
from app.repositories.observation_repository import MeasurementRow
from app.repositories.session import get_db_session
from app.services import regional_model_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
COIMBATORE = PILOT_CITY_CENTRES["coimbatore"]


def _model_hours(session: Session, value: float = 20.0, hours: int = 48) -> None:
    model_repository.upsert_hours(
        session,
        [
            ModelRow(
                city="coimbatore",
                pollutant=Pollutant.PM10,
                observed_at=NOW + timedelta(hours=offset),
                value=value + max(offset, 0),
                is_forecast=offset > 0,
                grid_point=(77.0, 11.0),
            )
            for offset in range(-hours, hours + 1)
        ],
    )


def _monitor(session: Session, value: float, hours: int = 30) -> None:
    station_id = station_repository.upsert_station(
        session,
        source="test",
        source_station_id="sidco-kurichi",
        name="SIDCO Kurichi",
        tier=StationTier.REFERENCE,
        coordinates=COIMBATORE,
    )
    observation_repository.upsert_measurements(
        session,
        [
            MeasurementRow(
                station_id=station_id,
                pollutant=Pollutant.PM10,
                observed_at=NOW - timedelta(hours=offset, minutes=30),
                value_raw=value,
                unit="µg/m³",
            )
            for offset in range(1, hours + 1)
        ],
    )


class TestView:
    def test_states_the_latest_hour_and_the_peaks_ahead(self, session: Session) -> None:
        _model_hours(session)

        view = regional_model_service.city_view(
            session, PilotCity.COIMBATORE, Pollutant.PM10, now=NOW
        )

        assert view.latest is not None
        assert view.latest.observed_at == NOW
        assert view.next_day_peak == pytest.approx(20.0 + 24)
        assert view.outlook_peak == pytest.approx(20.0 + 48)
        assert view.grid_point == (77.0, 11.0)

    def test_measures_the_model_against_the_citys_monitors(self, session: Session) -> None:
        _model_hours(session)
        _monitor(session, value=40.0)

        view = regional_model_service.city_view(
            session, PilotCity.COIMBATORE, Pollutant.PM10, now=NOW
        )

        # The model sits at 20 before now; the monitor reads 40.
        assert view.comparison.median_ratio == pytest.approx(0.5)
        assert view.comparison.is_established is True
        assert view.compared_stations == 1

    def test_another_citys_monitors_are_not_compared(self, session: Session) -> None:
        _model_hours(session)
        _monitor(session, value=40.0)

        view = regional_model_service.city_view(session, PilotCity.DELHI, Pollutant.PM10, now=NOW)

        assert view.latest is None
        assert view.comparison.pairs == 0


@respx.mock
async def test_ingest_stores_history_and_marks_the_forecast(session: Session) -> None:
    times = [(NOW + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M") for offset in (-1, 1)]
    hourly: dict[str, object] = {"time": times}
    hourly.update({variable: [15.0, 18.0] for variable in CAMS_VARIABLES.values()})
    respx.get(f"{CAMS_BASE_URL}/air-quality").mock(
        return_value=httpx.Response(
            200, json={"latitude": 11.0, "longitude": 77.0, "hourly": hourly}
        )
    )

    stored = await regional_model_service.ingest_city(session, PilotCity.COIMBATORE, now=NOW)

    assert stored == len(CAMS_VARIABLES) * 2
    rows = model_repository.hours_between(
        session, "coimbatore", Pollutant.PM25, NOW - timedelta(hours=2), NOW + timedelta(hours=2)
    )
    assert [row.is_forecast for row in rows] == [False, True]


def test_the_endpoint_labels_the_model_and_carries_its_comparison(
    app: FastAPI, session: Session
) -> None:
    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        body = client.get(
            "/v1/regional-model", params={"city": "coimbatore", "pollutant": "pm10"}
        ).json()

    assert "CAMS" in body["source"]
    assert "Modelled, not measured" in body["notice"]
    assert body["comparison"]["pairs"] == 0
    assert body["latest"] is None
