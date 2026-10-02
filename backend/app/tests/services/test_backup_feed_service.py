"""Tests for the backup monitor feed: CPCB's monitors through WAQI while OpenAQ is silent.

Repositories are stubbed, so these test the rules -- which monitors are filled,
from which WAQI station, and with what -- rather than the SQL, which has its own
integration tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.constants import WAQI_BASE_URL
from app.core.enums import MeasurementOrigin, PilotCity, Pollutant
from app.core.exceptions import MissingCredentialError
from app.core.us_aqi import concentration
from app.external.waqi_client import WaqiStation
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow
from app.services.backup_feed_service import (
    agency,
    city_bbox,
    credits_agency,
    fill_city,
    match_stations,
    site_key,
)
from app.tests.external.test_waqi_client import ANAND_VIHAR

NOW = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
#: When ANAND_VIHAR's figures were measured: 13:00 IST.
MEASURED = datetime(2026, 10, 2, 7, 30, tzinfo=UTC)

#: AirWatch's reference monitor at Anand Vihar, and another across Delhi.
ANAND_VIHAR_ID, ITO_ID = 11, 12
MONITORS: list[tuple[int, str, tuple[float, float]]] = [
    (ANAND_VIHAR_ID, "Anand Vihar, New Delhi - DPCC", (77.31580, 28.64760)),
    (ITO_ID, "ITO, New Delhi - CPCB", (77.24157, 28.62855)),
]

BOUNDS = [
    {"lat": 28.647622, "lon": 77.315809, "uid": 2553, "station": {"name": "Anand Vihar"}},
    {"lat": 28.628624, "lon": 77.241060, "uid": 2554, "station": {"name": "ITO"}},
]


def waqi_station(uid: int, lon: float, lat: float, name: str = "") -> WaqiStation:
    return WaqiStation(uid=uid, name=name or str(uid), coordinates=(lon, lat))


@pytest.fixture
def token(settings: Settings) -> Settings:
    return settings.model_copy(update={"waqi_api_token": "test-waqi-token"})


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[MeasurementRow]:
    rows: list[MeasurementRow] = []

    def insert(_session: object, batch: list[MeasurementRow]) -> int:
        rows.extend(batch)
        return len(batch)

    monkeypatch.setattr(
        station_repository, "stations_with_coordinates", lambda *a, **k: list(MONITORS)
    )
    monkeypatch.setattr(observation_repository, "insert_missing_measurements", insert)
    return rows


def newest(monkeypatch: pytest.MonkeyPatch, latest: dict[tuple[int, Pollutant], datetime]) -> None:
    monkeypatch.setattr(observation_repository, "newest_by_station", lambda *a, **k: latest)


def silent_everywhere() -> dict[tuple[int, Pollutant], datetime]:
    quiet = datetime(2026, 9, 29, 14, 30, tzinfo=UTC)
    return {
        (station, pollutant): quiet
        for station in (ANAND_VIHAR_ID, ITO_ID)
        for pollutant in (Pollutant.PM25, Pollutant.PM10)
    }


def feed(**overrides: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok", "data": {**ANAND_VIHAR, **overrides}})


class TestMatching:
    def test_pairs_each_monitor_with_the_instrument_beside_it(self) -> None:
        matched = match_stations(
            [waqi_station(2553, 77.315809, 28.647622), waqi_station(2554, 77.24106, 28.628624)],
            MONITORS,
        )

        assert {station: candidate.uid for station, candidate in matched.items()} == {
            ANAND_VIHAR_ID: 2553,
            ITO_ID: 2554,
        }

    def test_ignores_a_station_too_far_to_be_the_same_instrument(self) -> None:
        # About 2 km east of Anand Vihar.
        assert match_stations([waqi_station(7, 77.336, 28.6476)], MONITORS) == {}

    def test_one_waqi_station_fills_only_the_nearer_of_two_monitors(self) -> None:
        close_pair = [
            (1, "a", (77.3158, 28.6476)),
            (2, "b", (77.3200, 28.6476)),
        ]

        matched = match_stations([waqi_station(9, 77.3160, 28.6476)], close_pair)

        assert list(matched) == [1]

    def test_a_same_named_site_may_sit_a_few_kilometres_off(self) -> None:
        # WAQI placed DPCC's Mundka about 4.5 km from OpenAQ's position for it.
        mundka = [(5, "Mundka, Delhi - DPCC", (77.0329, 28.6823))]

        waqi_mundka = waqi_station(77, 77.0784, 28.6823, "Mundka, Delhi, Delhi, India")

        matched = match_stations([waqi_mundka], mundka)
        unnamed = match_stations([waqi_mundka], [(5, "Elsewhere - DPCC", (77.0329, 28.6823))])

        assert list(matched) == [5]
        assert unnamed == {}

    def test_reduces_site_names_for_comparison(self) -> None:
        assert site_key("R.K. Puram, Delhi, Delhi, India") == site_key("R K Puram, Delhi - DPCC")
        assert site_key("Punjabi Bagh, Delhi") != site_key("Pusa, Delhi - IMD")

    def test_requires_the_monitors_own_agency(self) -> None:
        dpcc = [
            "Delhi Pollution Control Commitee (Government of NCT of Delhi) http://dpccairdata.com/"
        ]

        assert agency("Anand Vihar, New Delhi - DPCC") == "DPCC"
        assert credits_agency(dpcc, "Anand Vihar, New Delhi - DPCC")
        # DPCC's Pusa is not IMD's Pusa, and a community sensor is nobody's monitor.
        assert not credits_agency(dpcc, "Pusa, Delhi - IMD")
        assert not credits_agency(["Clarity https://clarity.io"], "Okhla Phase-2, Delhi - DPCC")
        assert not credits_agency(dpcc, "A monitor with no agency in its name")

    def test_the_box_covers_the_city_view(self) -> None:
        west, south, east, north = city_bbox(PilotCity.DELHI)

        assert west < 77.209 < east
        assert south < 28.6139 < north
        assert north - south == pytest.approx(2 * 40_000 / 111_320, rel=1e-3)


class TestFill:
    async def test_needs_a_token(self, settings: Settings) -> None:
        with pytest.raises(MissingCredentialError):
            await fill_city(settings, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

    @respx.mock
    async def test_makes_no_request_while_every_monitor_is_reporting(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recent = NOW - timedelta(minutes=30)
        newest(monkeypatch, dict.fromkeys(silent_everywhere(), recent))
        route = respx.get(url__startswith=WAQI_BASE_URL)

        outcome = await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert outcome.silent_stations == 0
        assert not route.called
        assert stored == []

    @respx.mock
    async def test_fills_silent_monitors_with_converted_marked_readings(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        newest(monkeypatch, silent_everywhere())
        respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
            return_value=httpx.Response(200, json={"status": "ok", "data": BOUNDS})
        )
        respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=feed())
        respx.get(f"{WAQI_BASE_URL}/feed/@2554/").mock(
            return_value=feed(
                idx=2554,
                iaqi={"pm25": {"v": 88}},
                attributions=[{"name": "CPCB - India Central Pollution Control Board", "url": ""}],
            )
        )

        outcome = await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert (outcome.silent_stations, outcome.matched_stations, outcome.stored) == (2, 2, 3)
        by_key = {(row.station_id, row.pollutant): row for row in stored}
        anand_pm25 = by_key[(ANAND_VIHAR_ID, Pollutant.PM25)]
        assert anand_pm25.value_raw == pytest.approx(concentration(Pollutant.PM25, 132))
        assert anand_pm25.observed_at == MEASURED
        assert anand_pm25.unit == "ug/m3"
        assert {row.origin for row in stored} == {MeasurementOrigin.WAQI}
        # The gas figures are never converted.
        assert {row.pollutant for row in stored} == {Pollutant.PM25, Pollutant.PM10}

    @respx.mock
    async def test_never_stores_a_station_that_does_not_credit_the_monitors_agency(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A community sensor standing beside a monitor must not become one.
        newest(monkeypatch, silent_everywhere())
        respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
            return_value=httpx.Response(200, json={"status": "ok", "data": BOUNDS[:1]})
        )
        respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(
            return_value=feed(
                attributions=[{"name": "AirGradient", "url": "https://airgradient.com"}]
            )
        )

        outcome = await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert outcome.matched_stations == 1
        assert stored == []

    @respx.mock
    async def test_ignores_a_figure_waqi_has_itself_stopped_updating(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        newest(monkeypatch, silent_everywhere())
        respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
            return_value=httpx.Response(200, json={"status": "ok", "data": BOUNDS[:1]})
        )
        respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(
            return_value=feed(time={"iso": "2026-10-01T09:00:00+05:30"})
        )

        await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert stored == []

    @respx.mock
    async def test_fills_only_the_pollutant_that_went_quiet(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # PM10 arrived through OpenAQ at the same hour WAQI reports; only PM2.5 is missing.
        latest = silent_everywhere()
        latest[(ANAND_VIHAR_ID, Pollutant.PM10)] = MEASURED
        newest(monkeypatch, latest)
        respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
            return_value=httpx.Response(200, json={"status": "ok", "data": BOUNDS[:1]})
        )
        respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=feed())

        await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert [(row.station_id, row.pollutant) for row in stored] == [
            (ANAND_VIHAR_ID, Pollutant.PM25)
        ]

    @respx.mock
    async def test_an_index_off_the_table_is_left_out(
        self, token: Settings, stored: list[MeasurementRow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        newest(monkeypatch, silent_everywhere())
        respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
            return_value=httpx.Response(200, json={"status": "ok", "data": BOUNDS[:1]})
        )
        respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=feed(iaqi={"pm25": {"v": 612}}))

        await fill_city(token, object(), PilotCity.DELHI, now=NOW)  # type: ignore[arg-type]

        assert stored == []
