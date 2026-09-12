"""What the federation actually looks like, and whether it helped.

Two different kinds of fact live here and are deliberately kept apart.

**The monitoring gap is measured live.** How many stations each pilot city has,
and how many of them are actually reporting the pollutant, are counted from this
database on every request. That distinction is the finding: a site whose PM2.5
sensor died months ago still reports as active if its thermometer works, so
every published count of "active stations" includes monitors measuring nothing.

**The transfer result is a recorded experiment.** Whether the federated model
helped or harmed a node was measured by a training run, not by anything the API
can recompute, so it is reported with the conditions it was measured under --
row counts included, because a 23-row test set is a signal rather than a settled
fact and a reader has to be able to see that.

Mixing the two would let a stale experiment masquerade as a live measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.constants import (
    FEDERATED_GLOBAL_MAE_UGM3,
    FEDERATED_HARM_TOLERANCE,
    FEDERATED_LOCAL_MAE_UGM3,
    FEDERATED_TEST_ROWS,
    FEDERATED_TRAIN_ROWS,
    PILOT_CITY_CENTRES,
    PILOT_REPORTING_WINDOW_HOURS,
)
from app.core.enums import Pollutant
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


@dataclass(frozen=True, slots=True)
class TransferResult:
    """Whether the federated model helped this node, as measured."""

    node: str
    local_mae: float
    global_mae: float
    train_rows: int
    test_rows: int

    @property
    def improvement(self) -> float:
        """Relative change from adopting the global model. Negative means worse."""
        if self.local_mae <= 0:
            return 0.0
        return (self.local_mae - self.global_mae) / self.local_mae

    @property
    def is_harmed(self) -> bool:
        """Whether the global model measurably degraded this node."""
        return self.improvement < -FEDERATED_HARM_TOLERANCE

    @property
    def recommendation(self) -> str:
        """What this node should do, given the measurement."""
        if self.is_harmed:
            return "keep the local model"
        if self.improvement > FEDERATED_HARM_TOLERANCE:
            return "adopt the federated model"
        return "either; the difference is inside the noise"


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
    """The measured effect of federating, per node that took part."""
    return [
        TransferResult(
            node=node,
            local_mae=local,
            global_mae=FEDERATED_GLOBAL_MAE_UGM3[node],
            train_rows=FEDERATED_TRAIN_ROWS[node],
            test_rows=FEDERATED_TEST_ROWS[node],
        )
        for node, local in FEDERATED_LOCAL_MAE_UGM3.items()
    ]


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
    harmed = [result.node for result in transfer if result.is_harmed]
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
    if harmed:
        parts.append(
            f"Federated averaging measurably harmed {_name_list(harmed)}, so the "
            "recommendation is that it keeps its local model. That is the measurement, "
            "not a provisional result awaiting a better one."
        )
    if not parts:
        parts.append("Every participating node is at least as good under the federated model.")
    return " ".join(parts)


def status(session: Session, pollutant: Pollutant = Pollutant.PM25) -> FederationStatus:
    """The federation's live coverage and its measured transfer result."""
    coverage = node_coverage(session, pollutant)
    transfer = transfer_results()

    logger.info(
        "federation.status",
        nodes=len(coverage),
        reporting=sum(1 for node in coverage if node.reporting_stations > 0),
        harmed=sum(1 for result in transfer if result.is_harmed),
    )

    return FederationStatus(
        coverage=coverage,
        transfer=transfer,
        reporting_window_hours=PILOT_REPORTING_WINDOW_HOURS,
        summary=_summarise(coverage, transfer),
    )
