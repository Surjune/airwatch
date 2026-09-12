"""Tests for the exposure timing advisory.

The behaviour worth protecting is the refusal. This feature rests on a
climatology whose error is frequently larger than the signal, so on most routes
the difference between departure hours will be small — and a system that named a
best hour anyway would be dressing noise as advice that people act on.

The other property is that exposure weights by time in a segment, not by how
many samples fall in it. Getting that backwards would let a long clean stretch
outvote the short filthy one that actually determines the dose.
"""

from __future__ import annotations

import pytest

from app.core.constants import EXPOSURE_MEANINGFUL_REDUCTION, EXPOSURE_TRAVEL_SPEED_KMH
from app.ml.exposure import DepartureOption, RouteSample, advise, route_exposure


def route(*values: float, spacing_km: float = 2.0) -> list[RouteSample]:
    """A route with evenly spaced samples at the given concentrations."""
    return [
        RouteSample(distance_along_km=index * spacing_km, value=value)
        for index, value in enumerate(values)
    ]


def option(hour: int, exposure: float) -> DepartureOption:
    return DepartureOption(
        hour=hour, exposure=exposure, mean_concentration=exposure / 60.0, travel_minutes=60.0
    )


class TestRouteExposure:
    def test_a_dirtier_route_costs_more(self) -> None:
        clean, _, _ = route_exposure(route(20.0, 20.0, 20.0))
        dirty, _, _ = route_exposure(route(200.0, 200.0, 200.0))

        assert dirty > clean

    def test_a_longer_route_costs_more_at_the_same_concentration(self) -> None:
        short, _, _ = route_exposure(route(50.0, 50.0))
        long, _, _ = route_exposure(route(50.0, 50.0, 50.0, 50.0))

        assert long > short

    def test_travel_time_follows_distance_and_speed(self) -> None:
        _, _, minutes = route_exposure(route(50.0, 50.0, 50.0, spacing_km=10.0))

        # 20 km at the assumed speed.
        assert minutes == pytest.approx(20.0 / EXPOSURE_TRAVEL_SPEED_KMH * 60.0)

    def test_a_slower_journey_costs_more(self) -> None:
        # Same air, more time in it. Time is what turns a concentration into an
        # exposure, which is the whole reason speed is a parameter.
        fast, _, _ = route_exposure(route(80.0, 80.0), speed_kmh=40.0)
        slow, _, _ = route_exposure(route(80.0, 80.0), speed_kmh=10.0)

        assert slow > fast

    def test_weighting_is_by_time_not_by_sample_count(self) -> None:
        # A short filthy stretch and a long clean one. Counting samples would
        # let the clean stretch dominate; weighting by time is what makes the
        # answer describe the dose.
        uneven = [
            RouteSample(distance_along_km=0.0, value=400.0),
            RouteSample(distance_along_km=0.5, value=400.0),
            RouteSample(distance_along_km=20.0, value=20.0),
        ]

        _, mean, _ = route_exposure(uneven)

        # The long clean stretch dominates the time, so the mean sits near it
        # rather than near the average of the three sample values.
        assert mean < sum(sample.value for sample in uneven) / len(uneven)

    def test_a_route_with_one_sample_yields_nothing(self) -> None:
        # Nothing supports a segment, so there is no exposure to report. Zero is
        # the honest answer rather than a guess from a single point.
        assert route_exposure(route(100.0)) == (0.0, 0.0, 0.0)

    def test_an_empty_route_yields_nothing(self) -> None:
        assert route_exposure([]) == (0.0, 0.0, 0.0)

    def test_samples_out_of_order_are_handled(self) -> None:
        forwards, _, _ = route_exposure(route(30.0, 90.0, 30.0))
        shuffled = list(reversed(route(30.0, 90.0, 30.0)))

        assert route_exposure(shuffled)[0] == pytest.approx(forwards)


class TestAdvice:
    def test_recommends_the_cheapest_hour_when_the_day_varies(self) -> None:
        advisory = advise([option(8, 1000.0), option(14, 400.0), option(18, 900.0)])

        assert advisory.is_meaningful is True
        assert advisory.best is not None
        assert advisory.best.hour == 14
        assert advisory.worst is not None
        assert advisory.worst.hour == 8

    def test_reports_how_much_is_avoided(self) -> None:
        advisory = advise([option(8, 1000.0), option(14, 400.0)])

        assert advisory.reduction == pytest.approx(0.6)
        assert "60%" in advisory.explanation

    def test_withholds_a_recommendation_on_a_flat_day(self) -> None:
        # The refusal that matters. On a route where the day barely varies,
        # naming an hour would be advice built on less than the forecast's own
        # error, and people act on advice.
        advisory = advise([option(8, 1000.0), option(14, 970.0), option(18, 990.0)])

        assert advisory.is_meaningful is False
        assert "noise" in advisory.explanation

    def test_the_threshold_is_the_configured_one(self) -> None:
        just_under = advise(
            [option(8, 1000.0), option(14, 1000.0 * (1 - EXPOSURE_MEANINGFUL_REDUCTION / 2))]
        )
        just_over = advise(
            [option(8, 1000.0), option(14, 1000.0 * (1 - EXPOSURE_MEANINGFUL_REDUCTION * 2))]
        )

        assert just_under.is_meaningful is False
        assert just_over.is_meaningful is True

    def test_says_so_when_nothing_supports_the_route(self) -> None:
        advisory = advise([option(8, 0.0), option(14, 0.0)])

        assert advisory.best is None
        assert advisory.is_meaningful is False
        assert "unknown ground" in advisory.explanation

    def test_always_states_what_the_estimator_can_say(self) -> None:
        # Whether it recommends or declines, the reader is told the basis: an
        # average day, not a forecast for a particular one.
        varied = advise([option(8, 1000.0), option(14, 300.0)])
        flat = advise([option(8, 1000.0), option(14, 995.0)])

        assert "day-to-day skill" in varied.explanation
        assert "error" in flat.explanation

    def test_options_come_back_in_clock_order(self) -> None:
        # A reader scans a timetable by hour, not by rank.
        advisory = advise([option(18, 500.0), option(8, 900.0), option(14, 300.0)])

        assert [item.hour for item in advisory.options] == [8, 14, 18]

    def test_an_empty_set_of_options_is_not_a_crash(self) -> None:
        advisory = advise([])

        assert advisory.best is None
        assert advisory.options == []
