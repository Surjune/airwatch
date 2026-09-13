"""Tests for wind back-trajectory source attribution.

The properties that matter most are directional: a source downwind of a hotspot
must never be named, and a source that started burning after the hotspot was
observed must never be named. Both would be confident, plausible-looking, and
wrong — and in an enforcement context that is worse than naming nobody.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import SourceType
from app.core.geo import LonLat, destination_point, haversine_distance_m
from app.ml.attribution import (
    CandidateSource,
    WindHour,
    WindRecord,
    attribute,
    back_trajectory,
    fire_to_candidate,
    wind_field_near,
)

DELHI: LonLat = (77.2090, 28.6139)
OBSERVED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

#: A westerly: air moving east at 5 m/s, so the source lies to the west.
WESTERLY = WindHour(wind_u=5.0, wind_v=0.0)
CALM = WindHour(wind_u=0.0, wind_v=0.1)


def wind_field(wind: WindHour, hours: int = 8) -> dict[datetime, WindHour]:
    """A steady wind field covering the hours before the observation."""
    return {OBSERVED_AT - timedelta(hours=offset): wind for offset in range(hours + 1)}


def source_at(
    distance_m: float,
    bearing_deg: float,
    *,
    name: str = "Test source",
    prior: float = 0.9,
    observed_at: datetime | None = None,
) -> CandidateSource:
    return CandidateSource(
        identifier=name,
        name=name,
        source_type=SourceType.INDUSTRY,
        coordinates=destination_point(DELHI, bearing_deg, distance_m),
        emission_prior=prior,
        observed_at=observed_at,
    )


def wind_records(at: LonLat, wind: WindHour, hours: int = 3) -> list[WindRecord]:
    """Hourly records for one weather cell."""
    return [
        WindRecord(
            coordinates=at,
            observed_at=OBSERVED_AT - timedelta(hours=offset),
            wind_u=wind.wind_u,
            wind_v=wind.wind_v,
        )
        for offset in range(hours)
    ]


class TestWindFieldNear:
    def test_uses_the_nearest_cell_when_cities_share_hours(self) -> None:
        # Two cities, identical timestamps, opposite winds. Keyed by hour alone
        # the later city would overwrite the earlier; the nearest must win.
        coimbatore: LonLat = (76.96, 11.01)
        records = wind_records(coimbatore, WindHour(-5.0, 0.0)) + wind_records(DELHI, WESTERLY)

        field = wind_field_near(records, destination_point(DELHI, 90.0, 5000.0))

        assert set(field.values()) == {WESTERLY}
        assert len(field) == 3

    def test_no_cell_in_range_is_an_empty_field(self) -> None:
        coimbatore: LonLat = (76.96, 11.01)

        assert wind_field_near(wind_records(coimbatore, WESTERLY), DELHI) == {}

    def test_a_cell_at_the_boundary_still_counts(self) -> None:
        edge = destination_point(DELHI, 0.0, 10_000.0)

        field = wind_field_near(wind_records(edge, WESTERLY), DELHI, max_distance_m=10_001.0)

        assert len(field) == 3


class TestBackTrajectory:
    def test_walks_upwind(self) -> None:
        # A westerly carries air eastward, so tracing backwards moves west and
        # longitude decreases. The reverse would put every source on the wrong
        # side of the city.
        points = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))

        assert len(points) > 1
        assert points[-1].position[0] < DELHI[0]
        assert points[-1].position[1] == pytest.approx(DELHI[1], abs=1e-3)

    def test_travels_further_at_higher_wind_speed(self) -> None:
        slow = back_trajectory(DELHI, OBSERVED_AT, wind_field(WindHour(2.0, 0.0)))
        fast = back_trajectory(DELHI, OBSERVED_AT, wind_field(WindHour(8.0, 0.0)))

        slow_reach = haversine_distance_m(DELHI, slow[-1].position)
        fast_reach = haversine_distance_m(DELHI, fast[-1].position)
        assert fast_reach > slow_reach * 3

    def test_steps_backwards_in_time(self) -> None:
        points = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        assert points[0].at_time == OBSERVED_AT
        assert points[-1].at_time < points[0].at_time

    def test_the_cone_widens_with_backtrack_time(self) -> None:
        # Wind-field error and dispersion both compound, so certainty about
        # where the air came from has to degrade with distance back.
        points = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        assert points[-1].cone_half_angle_deg > points[1].cone_half_angle_deg

    def test_calm_air_stops_the_trajectory(self) -> None:
        # Without wind the air did not come from anywhere else; continuing would
        # invent a direction the data does not support.
        points = back_trajectory(DELHI, OBSERVED_AT, wind_field(CALM))
        assert len(points) == 1

    def test_missing_wind_stops_the_trajectory(self) -> None:
        assert len(back_trajectory(DELHI, OBSERVED_AT, {})) == 1


class TestDirectionality:
    def test_a_source_directly_upwind_is_attributed(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        upwind = source_at(6000.0, 270.0, name="Upwind plant")

        ranked = attribute(DELHI, OBSERVED_AT, trajectory, [upwind])

        assert [a.source.name for a in ranked] == ["Upwind plant"]

    def test_a_source_downwind_is_never_attributed(self) -> None:
        # The single most important negative case. The air over the hotspot came
        # from the west; a plant to the east cannot have caused it, however close.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        downwind = source_at(6000.0, 90.0, name="Downwind plant")

        assert attribute(DELHI, OBSERVED_AT, trajectory, [downwind]) == []

    def test_a_source_across_the_wind_is_not_attributed(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        crosswind = source_at(6000.0, 0.0, name="Northern plant")

        assert attribute(DELHI, OBSERVED_AT, trajectory, [crosswind]) == []

    def test_a_closer_upwind_source_outranks_a_distant_one(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        near = source_at(4000.0, 270.0, name="Near plant")
        far = source_at(20_000.0, 270.0, name="Far plant")

        ranked = attribute(DELHI, OBSERVED_AT, trajectory, [near, far])

        assert ranked[0].source.name == "Near plant"


class TestLocalSources:
    def test_a_colocated_source_needs_no_transport(self) -> None:
        # Delhi hotspots frequently occur under 2 m/s, where a plume barely
        # moves and the source is simply what the monitor stands next to.
        # Requiring it to lie upwind would make a bus terminal at the station
        # permanently invisible.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WindHour(1.5, 0.0)))
        terminal = CandidateSource(
            identifier="isbt",
            name="Bus terminal",
            source_type=SourceType.ROAD_SEGMENT,
            coordinates=DELHI,
            emission_prior=0.6,
        )

        ranked = attribute(DELHI, OBSERVED_AT, trajectory, [terminal])

        assert len(ranked) == 1
        assert ranked[0].hours_upwind == 0.0
        assert "no transport is required" in ranked[0].explanation

    def test_a_local_source_is_found_regardless_of_wind_direction(self) -> None:
        # Whichever way the wind blows, a source underfoot is still a candidate.
        for bearing_wind in (WindHour(5.0, 0.0), WindHour(-5.0, 0.0), WindHour(0.0, 5.0)):
            trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(bearing_wind))
            nearby = source_at(800.0, 45.0, name="Nearby yard")
            assert attribute(DELHI, OBSERVED_AT, trajectory, [nearby])


class TestTemporalPlausibility:
    def test_a_fire_detected_after_the_hotspot_is_rejected(self) -> None:
        # It cannot have caused something that was already happening.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        later = source_at(
            6000.0, 270.0, name="Later fire", observed_at=OBSERVED_AT + timedelta(hours=2)
        )

        assert attribute(DELHI, OBSERVED_AT, trajectory, [later]) == []

    def test_a_stale_fire_is_rejected(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        old = source_at(6000.0, 270.0, name="Old fire", observed_at=OBSERVED_AT - timedelta(days=3))

        assert attribute(DELHI, OBSERVED_AT, trajectory, [old]) == []

    def test_a_recent_fire_is_accepted(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        recent = source_at(
            6000.0, 270.0, name="Recent fire", observed_at=OBSERVED_AT - timedelta(hours=2)
        )

        assert [a.source.name for a in attribute(DELHI, OBSERVED_AT, trajectory, [recent])] == [
            "Recent fire"
        ]

    def test_a_registered_facility_has_no_time_constraint(self) -> None:
        # A facility has no single moment of emission, unlike a fire detection.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        facility = source_at(6000.0, 270.0, name="Plant", observed_at=None)

        assert attribute(DELHI, OBSERVED_AT, trajectory, [facility])


class TestNoEvidence:
    def test_calm_conditions_yield_no_upwind_attribution(self) -> None:
        # With no trajectory there is no directional evidence, and guessing from
        # proximity alone would name whichever facility happened to be nearest.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(CALM))
        distant = source_at(15_000.0, 270.0, name="Distant plant")

        assert attribute(DELHI, OBSERVED_AT, trajectory, [distant]) == []

    def test_an_empty_registry_returns_nothing(self) -> None:
        # A legitimate answer: it points at an unregistered source.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        assert attribute(DELHI, OBSERVED_AT, trajectory, []) == []

    def test_low_confidence_candidates_are_suppressed(self) -> None:
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        weak = source_at(22_000.0, 270.0, name="Weak distant source", prior=0.05)

        assert attribute(DELHI, OBSERVED_AT, trajectory, [weak]) == []


class TestFireCandidates:
    def test_a_larger_fire_gets_a_higher_prior(self) -> None:
        small = fire_to_candidate("a", DELHI, OBSERVED_AT, frp_mw=2.0, confidence=0.9)
        large = fire_to_candidate("b", DELHI, OBSERVED_AT, frp_mw=60.0, confidence=0.9)
        assert large.emission_prior > small.emission_prior

    def test_a_low_confidence_detection_is_discounted(self) -> None:
        certain = fire_to_candidate("a", DELHI, OBSERVED_AT, frp_mw=20.0, confidence=0.95)
        doubtful = fire_to_candidate("b", DELHI, OBSERVED_AT, frp_mw=20.0, confidence=0.25)
        assert doubtful.emission_prior < certain.emission_prior

    def test_a_fire_carries_its_detection_time(self) -> None:
        fire = fire_to_candidate("a", DELHI, OBSERVED_AT, frp_mw=10.0, confidence=0.65)
        assert fire.observed_at == OBSERVED_AT
        assert fire.source_type is SourceType.CROP_RESIDUE_FIRE

    def test_a_huge_fire_cannot_overwhelm_the_geometry(self) -> None:
        # A massive blaze in the wrong direction still did not cause this hotspot.
        trajectory = back_trajectory(DELHI, OBSERVED_AT, wind_field(WESTERLY))
        downwind_inferno = fire_to_candidate(
            "inferno",
            destination_point(DELHI, 90.0, 6000.0),
            OBSERVED_AT - timedelta(hours=1),
            frp_mw=500.0,
            confidence=0.95,
        )

        assert attribute(DELHI, OBSERVED_AT, trajectory, [downwind_inferno]) == []
