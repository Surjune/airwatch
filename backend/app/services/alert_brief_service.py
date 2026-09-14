"""A plain-language brief for an alert, written by Google Gemini.

An alert carries what an inspector needs -- the reading, what the neighbourhood
predicted, the standardised excess, a ranked candidate source -- and an official
reading forty of them before lunch will skip most of it. The brief says the
same thing in two sentences and one suggested inspection.

It is written from the alert's own figures and nothing else, and it is checked
before anyone sees it: every number in the brief must appear verbatim in those
figures (``core/grounding``). A brief that adds one is discarded with a typed
error, never shown and never stored. The figures themselves stay on the alert
card beside it, so the brief is a reading aid, not a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import ALERT_BRIEF_LOOKBACK_HOURS, IST_UTC_OFFSET_MINUTES
from app.core.enums import AlertKind, Pollutant
from app.core.exceptions import NotFoundError, UngroundedAiOutputError
from app.core.grounding import ungrounded_figures
from app.core.logging import get_logger
from app.external.gemini_client import GeminiClient
from app.ml.attribution import attribute, back_trajectory, wind_field_near
from app.repositories import alert_brief_repository, alert_repository, attribution_repository
from app.repositories.alert_repository import AlertDetail

logger = get_logger(__name__)

_CREDENTIAL = "gemini_api_key"
_IST = timezone(timedelta(minutes=IST_UTC_OFFSET_MINUTES))
_PERCENT = 100

_POLLUTANT_LABELS = {
    Pollutant.PM25: "PM2.5",
    Pollutant.PM10: "PM10",
    Pollutant.NO2: "NO2",
    Pollutant.SO2: "SO2",
    Pollutant.O3: "O3",
    Pollutant.CO: "CO",
    Pollutant.NH3: "NH3",
}


@dataclass(frozen=True, slots=True)
class AlertBriefView:
    """A brief ready to show, with where it came from."""

    alert_id: int
    summary: str
    suggested_action: str
    model: str
    generated_at: datetime


def _ist(moment: datetime) -> str:
    return moment.astimezone(_IST).strftime("%d %b %Y, %H:%M IST")


def _likely_source(session: Session, detail: AlertDetail) -> tuple[str, float] | None:
    """The source to name: the one a coordination request was sent about, or the top-ranked."""
    if detail.source_name is not None and detail.source_confidence is not None:
        return detail.source_name, detail.source_confidence
    since = detail.first_seen_at - timedelta(hours=ALERT_BRIEF_LOOKBACK_HOURS)
    wind = attribution_repository.wind_records(session, since)
    trajectory = back_trajectory(
        detail.coordinates, detail.last_seen_at, wind_field_near(wind, detail.coordinates)
    )
    ranked = attribute(
        detail.coordinates,
        detail.last_seen_at,
        trajectory,
        attribution_repository.candidate_sources(session, since),
    )
    return (ranked[0].source.name, ranked[0].confidence) if ranked else None


def alert_facts(detail: AlertDetail, likely_source: tuple[str, float] | None) -> str:
    """The alert's figures as the lines a brief may draw on, and be checked against.

    Numbers are rounded here, once, so the brief and the check see the same
    spelling of each.
    """
    expected = detail.peak_observed - detail.peak_excess
    lines = [
        (
            "Alert type: coordination request. The hotspot is in a neighbouring jurisdiction; "
            "the likely source is on the recipient's ground."
            if detail.kind is AlertKind.COORDINATION
            else "Alert type: hotspot alert, on the recipient's own ground."
        ),
        f"Sent to: {detail.authority_name}",
        f"Location: {detail.station_name or 'a location with no monitor'}",
        f"Pollutant: {_POLLUTANT_LABELS[detail.pollutant]}",
        f"Measured: {detail.peak_observed:.0f} µg/m³",
        f"Predicted from nearby monitors: {expected:.0f} µg/m³",
        f"Excess over the prediction: {detail.peak_excess:.0f} µg/m³",
        f"Excess in multiples of the usual prediction error: {detail.peak_z:.1f}",
        f"First seen: {_ist(detail.first_seen_at)}",
        f"Last seen: {_ist(detail.last_seen_at)}",
        (
            f"Likely source: {likely_source[0]}, {likely_source[1] * _PERCENT:.0f}% plausible "
            "(a ranked candidate from tracing the wind backwards, not a confirmed cause)"
            if likely_source is not None
            else "Likely source: none identified; no registered source or detected fire explains it"
        ),
    ]
    return "\n".join(lines)


async def brief_for(session: Session, settings: Settings, alert_id: int) -> AlertBriefView:
    """The alert's brief: the stored one, or a new one written, checked and stored.

    Raises:
        NotFoundError: No alert has this id.
        MissingCredentialError: No brief exists and no Gemini key is configured.
        UngroundedAiOutputError: Gemini's brief stated a figure the alert does not.
        UpstreamError: Gemini failed.
    """
    stored = alert_brief_repository.brief_for(session, alert_id)
    if stored is None:
        detail = next(
            (
                item
                for item in alert_repository.list_alert_details(session)
                if item.alert_id == alert_id
            ),
            None,
        )
        if detail is None:
            raise NotFoundError("alert", str(alert_id))

        facts = alert_facts(detail, _likely_source(session, detail))
        async with GeminiClient(settings.require(_CREDENTIAL)) as client:
            text = await client.write_brief(facts)
        invented = ungrounded_figures(f"{text.summary} {text.suggested_action}", facts)
        if invented:
            logger.warning("alert_brief.ungrounded", alert_id=alert_id, figures=sorted(invented))
            raise UngroundedAiOutputError(
                client.provider_name,
                "Gemini's brief stated figures this alert does not contain, so it was discarded.",
                details={"figures": sorted(invented)},
            )
        stored = alert_brief_repository.store_brief(
            session,
            alert_id=alert_id,
            summary=text.summary,
            suggested_action=text.suggested_action,
            model=text.model,
        )
        logger.info("alert_brief.written", alert_id=alert_id)

    return AlertBriefView(
        alert_id=stored.alert_id,
        summary=stored.summary,
        suggested_action=stored.suggested_action,
        model=stored.model,
        generated_at=stored.created_at,
    )
