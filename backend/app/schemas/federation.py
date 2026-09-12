"""Response models for the federation dashboard.

Two kinds of fact are kept visibly apart. Coverage is counted from the database
on every request; the transfer result was measured by a training run and is
reported with the conditions it was measured under. A reader who could not tell
them apart might take a stale experiment for a live reading.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NodeCoverageResponse(BaseModel):
    """One city's monitoring, counted now."""

    node: str
    stations: int = Field(description="Sites within range of the city centre.")
    reporting_stations: int = Field(
        description="Of those, how many have produced a reading for this pollutant recently."
    )
    silent_stations: int = Field(
        description=(
            "Stations in range not reporting this pollutant. A site whose PM2.5 "
            "sensor died still counts as active if its thermometer works, so "
            "every published count of active stations includes monitors "
            "measuring nothing."
        )
    )
    readings: int
    latest_reading_at: datetime | None = None
    is_unmonitored: bool = Field(
        description=(
            "True when monitors in range have never reported this pollutant. A "
            "genuine monitoring gap."
        )
    )
    is_stale: bool = Field(
        description=(
            "True when there is historical data but nothing recent. That is this "
            "deployment's ingestion falling behind, not a gap in the city's "
            "network, and the two must not be conflated."
        )
    )


class TransferResultResponse(BaseModel):
    """Whether the federated model helped one node, as measured."""

    node: str
    local_mae: float = Field(description="Error of the node's own model, in ug/m3.")
    global_mae: float = Field(description="Error of the federated model on the same holdout.")
    improvement: float = Field(
        description="Relative change from adopting the global model. Negative means worse."
    )
    is_harmed: bool
    recommendation: str
    train_rows: int
    test_rows: int = Field(
        description=(
            "Published so a reader can weigh the result. A holdout of a few dozen "
            "rows is a signal, not a settled fact."
        )
    )


class FederationStatusResponse(BaseModel):
    """The federation as it currently stands."""

    reporting_window_hours: int = Field(
        description="How recently a station must have reported to count as reporting."
    )
    summary: str = Field(
        description="The position in one sentence, stated whether or not it flatters the design."
    )
    coverage: list[NodeCoverageResponse]
    transfer: list[TransferResultResponse]
