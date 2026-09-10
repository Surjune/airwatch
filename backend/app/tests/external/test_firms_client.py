"""Tests for the NASA FIRMS active-fire client.

The CSV fixture is a verbatim copy of real API output, header included.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.constants import FIRMS_BASE_URL
from app.core.exceptions import UpstreamResponseError, UpstreamUnavailableError, ValidationError
from app.external.firms_client import FirmsClient

MAP_KEY = "secret-map-key-value"
INDIA_BBOX = (68.0, 6.0, 97.5, 37.5)

#: Real FIRMS output. Note acq_time 718 meaning 07:18, and letter confidences.
REAL_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "6.71136,81.53332,331.31,0.61,0.71,2026-09-08,718,N,VIIRS,n,2.0NRT,289.61,5.84,D\n"
    "30.21000,75.61000,367.20,0.48,0.62,2026-09-08,1830,N,VIIRS,h,2.0NRT,301.40,42.10,D\n"
    "28.90000,77.10000,320.05,0.55,0.66,2026-09-08,2015,N,VIIRS,l,2.0NRT,288.10,0.40,N\n"
)

HEADER_ONLY_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
)


def area_url() -> str:
    """The FIRMS area endpoint, matched by prefix since the key is in the path."""
    return f"{FIRMS_BASE_URL}/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/68.0,6.0,97.5,37.5/1"


def build_client() -> FirmsClient:
    return FirmsClient(MAP_KEY, backoff_base_seconds=0.0)


class TestCsvParsing:
    @respx.mock
    async def test_parses_real_csv_output(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        # The 0.40 MW detection is below the FRP floor and is dropped.
        assert len(fires) == 2

    @respx.mock
    async def test_orders_strongest_fire_first(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        assert [fire.frp_mw for fire in fires] == [42.10, 5.84]

    @respx.mock
    async def test_stores_coordinates_in_lon_lat_order(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        lon, lat = fires[0].coordinates
        # Punjab: longitude ~75, latitude ~30. Transposed, this would be in China.
        assert lon == pytest.approx(75.61)
        assert lat == pytest.approx(30.21)

    @respx.mock
    async def test_decodes_the_unpadded_hhmm_acquisition_time(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        by_frp = {fire.frp_mw: fire for fire in fires}
        # 1830 is 18:30, squarely in the 16:00-18:00 stubble-burning window that
        # satellites were said to miss.
        assert by_frp[42.10].observed_at == datetime(2026, 9, 8, 18, 30, tzinfo=UTC)
        # 718 is 07:18, not 7 minutes and not 07:00.
        assert by_frp[5.84].observed_at == datetime(2026, 9, 8, 7, 18, tzinfo=UTC)

    @respx.mock
    async def test_normalises_viirs_letter_confidence(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        by_frp = {fire.frp_mw: fire for fire in fires}
        assert by_frp[42.10].confidence == pytest.approx(0.95)  # "h"
        assert by_frp[5.84].confidence == pytest.approx(0.65)  # "n"

    @respx.mock
    async def test_reads_the_day_night_flag(self) -> None:
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=REAL_CSV))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        assert all(fire.is_daytime for fire in fires)

    @respx.mock
    async def test_a_header_only_body_means_no_fires_not_a_failure(self) -> None:
        # A quiet day is a legitimate answer, distinct from an outage.
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=HEADER_ONLY_CSV))

        async with build_client() as client:
            assert await client.fires_in_bbox(INDIA_BBOX) == []

    @respx.mock
    async def test_an_empty_body_is_a_failure(self) -> None:
        # FIRMS always returns a header, so a truly empty body is a fault and
        # must not be read as "no fires burning".
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=""))

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="empty body"):
                await client.fires_in_bbox(INDIA_BBOX)

    @respx.mock
    async def test_missing_columns_are_a_failure(self) -> None:
        respx.get(area_url()).mock(
            return_value=httpx.Response(200, text="latitude,longitude\n1.0,2.0\n")
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="missing required columns"):
                await client.fires_in_bbox(INDIA_BBOX)

    @respx.mock
    async def test_one_malformed_row_does_not_discard_the_overpass(self) -> None:
        corrupt = REAL_CSV.replace("6.71136,81.53332", "not-a-number,81.53332")
        respx.get(area_url()).mock(return_value=httpx.Response(200, text=corrupt))

        async with build_client() as client:
            fires = await client.fires_in_bbox(INDIA_BBOX)

        # The Punjab fire survives; only the unreadable row is skipped.
        assert len(fires) == 1
        assert fires[0].frp_mw == pytest.approx(42.10)


class TestCredentialLeakage:
    """The MAP_KEY travels in the URL path, so it must never reach a log or a client."""

    def test_sanitise_path_masks_the_key(self) -> None:
        client = build_client()
        masked = client.sanitise_path(f"/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/1,2,3,4/1")
        assert MAP_KEY not in masked
        assert "***" in masked

    @respx.mock
    async def test_the_key_never_appears_in_an_error_envelope(self) -> None:
        # The error details are returned verbatim to API callers. An unmasked
        # path here would hand every caller the account's FIRMS credential.
        respx.get(area_url()).mock(return_value=httpx.Response(500))

        async with build_client() as client:
            with pytest.raises(UpstreamUnavailableError) as excinfo:
                await client.fires_in_bbox(INDIA_BBOX)

        rendered = str(excinfo.value.details)
        assert MAP_KEY not in rendered
        assert "***" in rendered


class TestBoundingBoxValidation:
    async def test_rejects_inverted_longitude(self) -> None:
        async with build_client() as client:
            with pytest.raises(ValidationError, match="west"):
                await client.fires_in_bbox((97.5, 6.0, 68.0, 37.5))

    async def test_rejects_inverted_latitude(self) -> None:
        async with build_client() as client:
            with pytest.raises(ValidationError, match="south"):
                await client.fires_in_bbox((68.0, 37.5, 97.5, 6.0))

    async def test_rejects_an_out_of_range_coordinate(self) -> None:
        async with build_client() as client:
            with pytest.raises(ValidationError):
                await client.fires_in_bbox((68.0, 6.0, 200.0, 37.5))


class TestDayRange:
    @respx.mock
    async def test_caps_the_day_range_at_the_api_maximum(self) -> None:
        # The live API rejects 6 or more with "Invalid day range. Expects [1..5]",
        # so an over-large request is clamped rather than sent and refused.
        route = respx.get(
            f"{FIRMS_BASE_URL}/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/68.0,6.0,97.5,37.5/5"
        ).mock(return_value=httpx.Response(200, text=HEADER_ONLY_CSV))

        async with build_client() as client:
            await client.fires_in_bbox(INDIA_BBOX, day_range=99)

        assert route.called

    @respx.mock
    async def test_floors_the_day_range_at_one(self) -> None:
        route = respx.get(
            f"{FIRMS_BASE_URL}/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/68.0,6.0,97.5,37.5/1"
        ).mock(return_value=httpx.Response(200, text=HEADER_ONLY_CSV))

        async with build_client() as client:
            await client.fires_in_bbox(INDIA_BBOX, day_range=0)

        assert route.called


class TestUpstreamMessage:
    @respx.mock
    async def test_carries_the_providers_own_explanation(self) -> None:
        # FIRMS names the real constraint in the body. Discarding it turns a
        # one-line diagnosis into an investigation.
        respx.get(area_url()).mock(
            return_value=httpx.Response(400, text="Invalid day range. Expects [1..5].")
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError) as excinfo:
                await client.fires_in_bbox(INDIA_BBOX)

        assert "Expects [1..5]" in str(excinfo.value.details["upstream_message"])

    @respx.mock
    async def test_masks_a_key_echoed_back_in_the_error_body(self) -> None:
        # Some providers echo the request URL into the error text, which for
        # FIRMS would contain the MAP_KEY.
        respx.get(area_url()).mock(
            return_value=httpx.Response(400, text=f"Bad request for /area/csv/{MAP_KEY}/x")
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError) as excinfo:
                await client.fires_in_bbox(INDIA_BBOX)

        assert MAP_KEY not in str(excinfo.value.details)
