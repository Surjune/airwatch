"""Tests for reading CPCB's labels, timestamps and missing values."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core import cpcb
from app.core.enums import Pollutant


def test_maps_the_labels_of_both_the_live_feeds_and_the_bulletin() -> None:
    assert cpcb.pollutant("PM2.5") is Pollutant.PM25
    assert cpcb.pollutant(" ozone ") is Pollutant.O3
    assert cpcb.pollutant("O3") is Pollutant.O3
    assert cpcb.pollutant("Benzene") is None


def test_reads_an_ist_timestamp_as_utc() -> None:
    # 21:00 IST is 15:30 UTC.
    assert cpcb.parse_timestamp("08-10-2026 21:00:00") == datetime(2026, 10, 8, 15, 30, tzinfo=UTC)


def test_rejects_a_timestamp_in_another_format() -> None:
    with pytest.raises(ValueError):
        cpcb.parse_timestamp("2026-10-08T21:00:00")


def test_a_missing_value_is_none_never_zero() -> None:
    assert cpcb.optional_value("NA") is None
    assert cpcb.optional_value(" ") is None
    assert cpcb.optional_value("garbled") is None
    assert cpcb.optional_value("51") == 51.0
