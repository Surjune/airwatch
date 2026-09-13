"""Tests for scoping a position to a pilot city."""

from __future__ import annotations

from app.core.cities import in_city
from app.core.enums import PilotCity

ANAND_VIHAR = (77.3152, 28.6469)
GHAZIABAD_VASUNDHARA = (77.3573, 28.6603)
SIDCO_KURICHI = (76.9790, 10.9425)


def test_every_position_is_in_scope_when_no_city_is_chosen() -> None:
    assert in_city(ANAND_VIHAR, None)
    assert in_city(SIDCO_KURICHI, None)


def test_a_station_belongs_to_its_own_city_only() -> None:
    assert in_city(SIDCO_KURICHI, PilotCity.COIMBATORE)
    assert not in_city(SIDCO_KURICHI, PilotCity.DELHI)
    assert not in_city(ANAND_VIHAR, PilotCity.COIMBATORE)


def test_the_delhi_view_reaches_the_ncr_towns_its_air_mixes_with() -> None:
    # Ghaziabad is outside Delhi's municipal line but inside its airshed.
    assert in_city(GHAZIABAD_VASUNDHARA, PilotCity.DELHI)
