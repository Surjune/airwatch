"""Tests for Gemini-written alert briefs: their facts, the figure check, and storage."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import GEMINI_BASE_URL, GEMINI_MODELS
from app.core.enums import AlertKind, AlertStatus, Pollutant
from app.core.exceptions import MissingCredentialError, NotFoundError, UngroundedAiOutputError
from app.repositories import alert_brief_repository, alert_repository
from app.repositories.alert_repository import AlertDetail
from app.services import alert_brief_service, alert_service
from app.services.alert_brief_service import alert_facts
from app.tests.services.test_alert_service import NOW, _seed_authority, _seed_network

URL = f"{GEMINI_BASE_URL}/models/{GEMINI_MODELS[0]}:generateContent"


def detail(**overrides: object) -> AlertDetail:
    values: dict[str, object] = {
        "alert_id": 1,
        "status": AlertStatus.SENT,
        "sent_at": datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
        "delivered_at": None,
        "delivery_error": None,
        "acknowledged_at": None,
        "resolved_at": None,
        "resolution_note": None,
        "authority_id": 3,
        "authority_name": "East Delhi district administration",
        "hotspot_id": 1,
        "station_name": "Prashant Garden, Khora - UPPCB",
        "coordinates": (77.34, 28.62),
        "pollutant": Pollutant.PM25,
        "first_seen_at": datetime(2026, 9, 10, 7, 30, tzinfo=UTC),
        "last_seen_at": datetime(2026, 9, 10, 10, 30, tzinfo=UTC),
        "peak_observed": 74.2,
        "peak_excess": 54.1,
        "peak_z": 3.72,
        "kind": AlertKind.COORDINATION,
        "source_name": "Ghazipur landfill",
        "source_confidence": 0.69,
    }
    values.update(overrides)
    return AlertDetail(**values)  # type: ignore[arg-type]


def gemini(summary: str, action: str = "Inspect the most likely source first.") -> httpx.Response:
    text = json.dumps({"summary": summary, "suggested_action": action})
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    )


@pytest.fixture
def voiced(settings: Settings) -> Settings:
    return settings.model_copy(update={"gemini_api_key": "test-gemini-key"})


class TestFacts:
    def test_states_each_figure_once_rounded_and_the_time_in_ist(self) -> None:
        facts = alert_facts(detail(), ("Ghazipur landfill", 0.69))

        assert "Measured: 74 µg/m³" in facts
        assert "Predicted from nearby monitors: 20 µg/m³" in facts
        assert "Excess in multiples of the usual prediction error: 3.7" in facts
        # 07:30 UTC is 13:00 IST.
        assert "First seen: 10 Sep 2026, 13:00 IST" in facts

    def test_names_the_source_as_a_candidate_with_its_plausibility(self) -> None:
        facts = alert_facts(detail(), ("Ghazipur landfill", 0.69))

        assert "Ghazipur landfill, 69% plausible" in facts
        assert "not a confirmed cause" in facts

    def test_says_when_no_source_explains_it(self) -> None:
        facts = alert_facts(detail(kind=AlertKind.LOCAL), None)

        assert "none identified" in facts
        assert "own ground" in facts

    def test_an_unmonitored_location_is_said_plainly(self) -> None:
        assert "a location with no monitor" in alert_facts(detail(station_name=None), None)


async def test_without_a_key_nothing_is_attempted(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(alert_brief_repository, "brief_for", lambda *_: None)
    monkeypatch.setattr(alert_repository, "list_alert_details", lambda *_: [detail()])
    monkeypatch.setattr(alert_brief_service, "_likely_source", lambda *_: None)

    with pytest.raises(MissingCredentialError):
        await alert_brief_service.brief_for(None, settings, 1)  # type: ignore[arg-type]


@pytest.mark.integration
class TestStoredBriefs:
    def _alert_id(self, session: Session) -> int:
        _seed_network(session)
        _seed_authority(session)
        return (
            alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
            .raised[0]
            .alert_id
        )

    @respx.mock
    async def test_a_brief_is_written_once_and_then_read_back(
        self, session: Session, voiced: Settings
    ) -> None:
        alert_id = self._alert_id(session)
        route = respx.post(URL).mock(return_value=gemini("A hotspot needs inspection."))

        first = await alert_brief_service.brief_for(session, voiced, alert_id)
        second = await alert_brief_service.brief_for(session, voiced, alert_id)

        assert first.summary == second.summary == "A hotspot needs inspection."
        assert first.model == GEMINI_MODELS[0]
        assert route.call_count == 1

    @respx.mock
    async def test_a_brief_with_an_invented_figure_is_discarded(
        self, session: Session, voiced: Settings
    ) -> None:
        alert_id = self._alert_id(session)
        respx.post(URL).mock(return_value=gemini("Levels were 9999 µg/m³, a record."))

        with pytest.raises(UngroundedAiOutputError) as raised:
            await alert_brief_service.brief_for(session, voiced, alert_id)

        assert "9999" in raised.value.details["figures"]
        assert alert_brief_repository.brief_for(session, alert_id) is None

    async def test_an_unknown_alert_is_not_found(self, session: Session, voiced: Settings) -> None:
        with pytest.raises(NotFoundError):
            await alert_brief_service.brief_for(session, voiced, 987654)
