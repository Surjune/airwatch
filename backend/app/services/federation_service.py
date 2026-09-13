"""What the federation actually looks like, and whether it helped.

Two different kinds of fact live here and are deliberately kept apart.

**The monitoring gap is measured live.** How many stations each pilot city has,
and how many of them are actually reporting the pollutant, are counted from this
database on every request. That distinction is the finding: a site whose PM2.5
sensor died months ago still reports as active if its thermometer works, so
every published count of "active stations" includes monitors measuring nothing.

**The transfer result is a recorded experiment.** Whether a federated model
helped or harmed a node was measured by a training run, not by anything the API
can recompute, so it is reported with the conditions it was measured under: the
row counts, and a bootstrap interval on every difference. The verdict comes from
the interval through ``core/evidence``, never from the point estimate alone.

That rule is here because an earlier version of this service broke it, telling
readers "federated averaging measurably harmed Kanpur" on 23 held-out rows whose
interval spans zero.

Mixing the two would let a stale experiment masquerade as a live measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.constants import (
    FEDERATED_CANDIDATE_RESULTS,
    FEDERATED_LOCAL_MAE_UGM3,
    FEDERATED_TEST_ROWS,
    FEDERATED_TRAIN_ROWS,
    FL_NEGATIVE_TRANSFER_TOLERANCE,
    PILOT_CITY_CENTRES,
    PILOT_REPORTING_WINDOW_HOURS,
)
from app.core.enums import Pollutant
from app.core.evidence import Effect, EffectEstimate, classify
from app.core.logging import get_logger
from app.repositories import station_repository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NodeCoverage:
    """One city's monitoring, as it stands right now."""

    node: str
    stations: int
    reporting_stations: int
    readings: int
    latest_reading_at: datetime | None

    @property
    def silent_stations(self) -> int:
        """Stations in range that are not currently reporting this pollutant."""
        return max(0, self.stations - self.reporting_stations)

    @property
    def is_unmonitored(self) -> bool:
        """Whether this city has never had data for this pollutant.

        Distinct from stale. A city with monitors that have produced nothing is
        a monitoring gap; a city whose readings have simply stopped arriving is
        an ingestion gap, and calling the second one a monitoring gap would be a
        false claim about a real place.
        """
        return self.readings == 0

    @property
    def is_stale(self) -> bool:
        """Whether this city has data but none of it recent."""
        return self.readings > 0 and self.reporting_stations == 0


#: Candidates in the order they are presented: plain averaging first, because it
#: is what the design proposed, then the two personalised variants.
CANDIDATE_ORDER: tuple[str, ...] = ("global", "fine-tuned", "local head")


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """One federated candidate against a node's own model, as measured."""

    candidate: str
    mae: float
    estimate: EffectEstimate
    effect: Effect


@dataclass(frozen=True, slots=True)
class TransferResult:
    """Every federated candidate for one node, against that node's own model."""

    node: str
    local_mae: float
    train_rows: int
    test_rows: int
    candidates: list[CandidateResult]

    @property
    def recommendation(self) -> str:
        """What this node should do, given what the evidence establishes."""
        helped = [c.candidate for c in self.candidates if c.effect is Effect.HELPED]
        harmed = [c.candidate for c in self.candidates if c.effect is Effect.HARMED]
        if helped:
            return f"adopt the {helped[0]} model"
        if harmed and len(harmed) == len(self.candidates):
            return "keep the local model"
        return (
            "no evidence either way: keep the local model until a larger holdout "
            "can tell the options apart"
        )


@dataclass(frozen=True, slots=True)
class FederationStatus:
    """The federation as it currently stands."""

    coverage: list[NodeCoverage]
    transfer: list[TransferResult]
    reporting_window_hours: int
    summary: str


def node_coverage(session: Session, pollutant: Pollutant = Pollutant.PM25) -> list[NodeCoverage]:
    """Count the monitoring each pilot city actually has."""
    return [
        NodeCoverage(
            node=name,
            stations=coverage.stations,
            reporting_stations=coverage.reporting_stations,
            readings=coverage.readings,
            latest_reading_at=coverage.latest_reading_at,
        )
        for name, coverage in (
            (name, station_repository.city_coverage(session, centre, pollutant))
            for name, centre in PILOT_CITY_CENTRES.items()
        )
    ]


def transfer_results() -> list[TransferResult]:
    """Every recorded federated candidate, per node, with its verdict."""
    results: list[TransferResult] = []
    for node, local_mae in FEDERATED_LOCAL_MAE_UGM3.items():
        recorded = FEDERATED_CANDIDATE_RESULTS[node]
        candidates = []
        for name in CANDIDATE_ORDER:
            mae, gain, low, high = recorded[name]
            estimate = EffectEstimate(
                gain=gain, low=low, high=high, samples=FEDERATED_TEST_ROWS[node]
            )
            candidates.append(
                CandidateResult(
                    candidate=name,
                    mae=mae,
                    estimate=estimate,
                    effect=classify(
                        estimate,
                        baseline_error=local_mae,
                        tolerance=FL_NEGATIVE_TRANSFER_TOLERANCE,
                    ),
                )
            )
        results.append(
            TransferResult(
                node=node,
                local_mae=local_mae,
                train_rows=FEDERATED_TRAIN_ROWS[node],
                test_rows=FEDERATED_TEST_ROWS[node],
                candidates=candidates,
            )
        )
    return results


def _name_list(nodes: list[str]) -> str:
    """Render node names for prose, so the sentence reads correctly."""
    return ", ".join(name.title() for name in sorted(nodes))


def _summarise(coverage: list[NodeCoverage], transfer: list[TransferResult]) -> str:
    """State the position plainly, favourable or not.

    Unmonitored and stale are reported as different things. A city whose
    monitors have produced nothing has a monitoring gap; a city whose readings
    have merely stopped arriving has an ingestion gap here. Calling the second a
    monitoring gap would be a false claim about a real place, and the whole
    point of this system is not to make those.
    """
    established = [
        (result.node, candidate)
        for result in transfer
        for candidate in result.candidates
        if candidate.effect in (Effect.HELPED, Effect.HARMED)
    ]
    unmonitored = [node.node for node in coverage if node.is_unmonitored]
    stale = [node.node for node in coverage if node.is_stale]

    parts: list[str] = []
    if unmonitored:
        verb = "has" if len(unmonitored) == 1 else "have"
        parts.append(
            f"{_name_list(unmonitored)} {verb} monitors in range that have never reported "
            "this pollutant, which is the gap federation exists to close."
        )
    if stale:
        verb = "has" if len(stale) == 1 else "have"
        parts.append(
            f"{_name_list(stale)} {verb} historical data but nothing recent, which is this "
            "deployment's ingestion falling behind rather than a gap in their network."
        )
    if established:
        for node, candidate in established:
            parts.append(
                f"The {candidate.candidate} model {candidate.effect.value} {node.title()}, "
                "with an interval that excludes zero and an effect large enough to act on."
            )
    else:
        parts.append(
            "No federated model -- plain averaging or either personalised variant -- is "
            "established as helping or harming any node. The point estimates differ, but "
            "the held-out data cannot distinguish them from no effect, so each node keeps "
            "its own model until a larger holdout can."
        )
    return " ".join(parts)


def status(session: Session, pollutant: Pollutant = Pollutant.PM25) -> FederationStatus:
    """The federation's live coverage and its measured transfer result."""
    coverage = node_coverage(session, pollutant)
    transfer = transfer_results()

    logger.info(
        "federation.status",
        nodes=len(coverage),
        reporting=sum(1 for node in coverage if node.reporting_stations > 0),
        established=sum(
            1
            for result in transfer
            for candidate in result.candidates
            if candidate.effect in (Effect.HELPED, Effect.HARMED)
        ),
    )

    return FederationStatus(
        coverage=coverage,
        transfer=transfer,
        reporting_window_hours=PILOT_REPORTING_WINDOW_HOURS,
        summary=_summarise(coverage, transfer),
    )
