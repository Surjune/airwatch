"""Tests for CPCB's rule for stating a station AQI, and the stored city view."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.constants import OFFICIAL_SUB_INDEX_MAX_AGE_HOURS, TNPCB_AQI_PATH, TNPCB_BASE_URL
from app.core.enums import OfficialRelay, PilotCity, Pollutant
from app.repositories import official_aqi_repository, station_repository
from app.repositories.official_aqi_repository import OfficialRow
from app.services.official_aqi_service import ingest_tnpcb, latest_for_city, station_aqi
from app.tests.external.test_tnpcb_client import MANALI_VILLAGE, SIDCO, page

NOW = datetime(2026, 9, 13, 8, 30, tzinfo=UTC)


class TestStationAqi:
    def test_is_the_highest_sub_index_with_the_pollutant_that_sets_it(self) -> None:
        overall, dominant = station_aqi({Pollutant.PM10: 28, Pollutant.NO2: 22, Pollutant.CO: 44})
        assert overall == 44
        assert dominant is Pollutant.CO

    def test_is_not_stated_with_fewer_than_three_pollutants(self) -> None:
        assert station_aqi({Pollutant.PM25: 180, Pollutant.NO2: 40}) == (None, None)

    def test_is_not_stated_without_a_particulate(self) -> None:
        # Three gases alone could understate a smoky day entirely.
        gases = {Pollutant.NO2: 40, Pollutant.SO2: 30, Pollutant.O3: 60}
        assert station_aqi(gases) == (None, None)


def _row(pollutant: Pollutant, value: float, reported_at: datetime) -> OfficialRow:
    return OfficialRow(
        station_name="SIDCO Kurichi, Coimbatore - TNPCB",
        city="Coimbatore",
        state="TamilNadu",
        coordinates=(76.979, 10.9425),
        pollutant=pollutant,
        reported_at=reported_at,
        sub_index=value,
        sub_index_min=None,
        sub_index_max=None,
    )


@pytest.mark.integration
def test_a_pollutant_that_stopped_reporting_is_not_combined(session: Session) -> None:
    earlier = NOW - timedelta(hours=OFFICIAL_SUB_INDEX_MAX_AGE_HOURS + 1)
    official_aqi_repository.upsert_sub_indices(
        session,
        [
            _row(Pollutant.PM10, 28, NOW),
            _row(Pollutant.NO2, 22, NOW),
            _row(Pollutant.CO, 44, NOW),
            # A sensor silent for longer than the window must not set today's AQI.
            _row(Pollutant.SO2, 150, earlier),
        ],
    )
    session.flush()

    stations = latest_for_city(session, PilotCity.COIMBATORE)

    assert len(stations) == 1
    station = stations[0]
    assert station.reported_at == NOW
    assert Pollutant.SO2 not in station.sub_indices
    assert station.aqi == 44
    assert station.category == "Good"


@pytest.mark.integration
def test_pollutants_published_an_hour_apart_still_make_an_index(session: Session) -> None:
    # SIDCO Kurichi on 15 September 2026: CO and O3 in the newest update, PM10,
    # NO2 and SO2 an hour earlier. Taking only the newest hour stated no index.
    earlier = NOW - timedelta(hours=1)
    official_aqi_repository.upsert_sub_indices(
        session,
        [
            _row(Pollutant.CO, 47, NOW),
            _row(Pollutant.O3, 20, NOW),
            _row(Pollutant.PM10, 28, earlier),
            _row(Pollutant.NO2, 22, earlier),
            _row(Pollutant.SO2, 27, earlier),
        ],
    )
    session.flush()

    station = latest_for_city(session, PilotCity.COIMBATORE)[0]

    assert station.aqi == 47
    assert station.dominant_pollutant is Pollutant.CO
    assert set(station.sub_indices) == {
        Pollutant.CO,
        Pollutant.O3,
        Pollutant.PM10,
        Pollutant.NO2,
        Pollutant.SO2,
    }
    assert station.reported_at == NOW
    assert station.oldest_reported_at == earlier


#: Where CPCB's feed puts SIDCO Kurichi, and where OpenAQ puts it.
SIDCO_OFFICIAL = (76.978996, 10.942451)
SIDCO_OPENAQ = (76.9790, 10.9425)


class TestIngestTnpcb:
    @pytest.fixture
    def stored(self, monkeypatch: pytest.MonkeyPatch) -> list[OfficialRow]:
        rows: list[OfficialRow] = []

        def upsert(_session: Any, batch: list[OfficialRow]) -> int:
            rows.extend(batch)
            return len(batch)

        monkeypatch.setattr(official_aqi_repository, "upsert_sub_indices", upsert)
        monkeypatch.setattr(
            official_aqi_repository,
            "positions_by_station",
            lambda *_: {SIDCO["name"]: SIDCO_OFFICIAL},
        )
        monkeypatch.setattr(
            station_repository,
            "stations_with_coordinates",
            lambda *_, **__: [(9, SIDCO["name"], SIDCO_OPENAQ)],
        )
        return rows

    @respx.mock
    async def test_stores_the_pilot_cities_stations_marked_as_tnpcbs(
        self, stored: list[OfficialRow]
    ) -> None:
        respx.get(f"{TNPCB_BASE_URL}{TNPCB_AQI_PATH}").mock(
            return_value=httpx.Response(
                200, text=page(("Coimbatore", SIDCO), ("Chennai", MANALI_VILLAGE))
            )
        )

        count = await ingest_tnpcb(object())  # type: ignore[arg-type]

        assert count == len(stored) == 3
        assert {row.station_name for row in stored} == {SIDCO["name"]}
        assert {row.relay for row in stored} == {OfficialRelay.TNPCB}
        assert {row.state for row in stored} == {"Tamil Nadu"}
        # CPCB's own position for the station wins over OpenAQ's.
        assert {row.coordinates for row in stored} == {SIDCO_OFFICIAL}

    @respx.mock
    async def test_leaves_out_a_station_it_cannot_place(
        self, stored: list[OfficialRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(official_aqi_repository, "positions_by_station", lambda *_: {})
        monkeypatch.setattr(station_repository, "stations_with_coordinates", lambda *_, **__: [])
        respx.get(f"{TNPCB_BASE_URL}{TNPCB_AQI_PATH}").mock(
            return_value=httpx.Response(200, text=page(("Coimbatore", SIDCO)))
        )

        assert await ingest_tnpcb(object()) == 0  # type: ignore[arg-type]
        assert stored == []


@pytest.mark.integration
def test_reports_which_relay_the_newest_figure_came_through(session: Session) -> None:
    earlier = NOW - timedelta(hours=1)
    tnpcb = [
        OfficialRow(**{**vars_of(_row(pollutant, value, NOW)), "relay": OfficialRelay.TNPCB})
        for pollutant, value in ((Pollutant.PM10, 28), (Pollutant.NO2, 22))
    ]
    official_aqi_repository.upsert_sub_indices(session, [_row(Pollutant.CO, 44, earlier), *tnpcb])
    session.flush()

    station = latest_for_city(session, PilotCity.COIMBATORE)[0]

    assert station.relay is OfficialRelay.TNPCB
    assert official_aqi_repository.positions_by_station(session) == {
        "SIDCO Kurichi, Coimbatore - TNPCB": pytest.approx((76.979, 10.9425))
    }


def vars_of(row: OfficialRow) -> dict[str, Any]:
    """A stored row's fields, to rebuild it with one changed."""
    return {name: getattr(row, name) for name in row.__dataclass_fields__}
