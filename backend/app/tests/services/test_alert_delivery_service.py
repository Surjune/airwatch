"""Tests for alert delivery.

The behaviour that matters is what happens when delivery fails, because that is
the case an accountability trail can be quietly broken by. A failed delivery
must leave the alert queued and visible; marking it delivered would lose it, and
an authority would never learn of a hotspot the system believes it reported.

The second property is the distinction between "nothing to send" and "nowhere to
send it". A deployment with no endpoint configured must not report success.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import Pollutant
from app.repositories import alert_repository
from app.services import alert_delivery_service, alert_service
from app.tests.services.test_alert_service import _seed_authority, _seed_network

pytestmark = pytest.mark.integration

WEBHOOK_URL = "https://control-room.example.invalid/airwatch"

NOW = datetime(2026, 2, 10, 9, 0, tzinfo=UTC)


def _configured(settings: Settings) -> Settings:
    return settings.model_copy(update={"alert_webhook_url": WEBHOOK_URL})


def _raise_alerts(session: Session) -> int:
    """Seed a network, detect, and route. Returns how many alerts were raised."""
    _seed_network(session)
    _seed_authority(session)
    session.flush()
    outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
    return len(outcome.raised)


class TestNoEndpointConfigured:
    async def test_reports_that_nothing_was_sent(
        self, session: Session, settings: Settings
    ) -> None:
        # Nowhere to send is not the same as nothing to send. A run that
        # reported success here would be claiming an authority had been told.
        _raise_alerts(session)

        outcome = await alert_delivery_service.deliver_pending(session, settings)

        assert outcome.endpoint_configured is False
        assert outcome.attempted == 0
        assert outcome.delivered == 0

    async def test_leaves_the_alerts_queued(self, session: Session, settings: Settings) -> None:
        raised = _raise_alerts(session)

        await alert_delivery_service.deliver_pending(session, settings)

        assert alert_delivery_service.pending_count(session) == raised


class TestSuccessfulDelivery:
    @respx.mock
    async def test_delivers_every_queued_alert(self, session: Session, settings: Settings) -> None:
        raised = _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

        outcome = await alert_delivery_service.deliver_pending(session, _configured(settings))

        assert outcome.delivered == raised
        assert outcome.failed == 0
        assert alert_delivery_service.pending_count(session) == 0

    @respx.mock
    async def test_a_delivered_alert_is_not_sent_twice(
        self, session: Session, settings: Settings
    ) -> None:
        # The queue is the record of what still needs sending, so a second run
        # must find nothing rather than duplicate every message.
        _raise_alerts(session)
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

        await alert_delivery_service.deliver_pending(session, _configured(settings))
        first_pass = route.call_count
        await alert_delivery_service.deliver_pending(session, _configured(settings))

        assert route.call_count == first_pass

    @respx.mock
    async def test_the_payload_carries_expected_alongside_observed(
        self, session: Session, settings: Settings
    ) -> None:
        # A receiver given only the concentration cannot tell a local source
        # from a bad day across the whole city, and only one is theirs to act on.
        _raise_alerts(session)
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

        await alert_delivery_service.deliver_pending(session, _configured(settings))

        payload = route.calls[0].request.content.decode()
        assert '"peak_expected"' in payload
        assert '"peak_excess"' in payload
        assert '"standardised_excess"' in payload

    @respx.mock
    async def test_the_payload_locates_the_hotspot_in_geojson_order(
        self, session: Session, settings: Settings
    ) -> None:
        import json

        _raise_alerts(session)
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

        await alert_delivery_service.deliver_pending(session, _configured(settings))

        body = json.loads(route.calls[0].request.content)
        longitude, latitude = body["location"]["coordinates"]
        # Delhi sits near 77E, 28N, so a transposed pair is unmistakable.
        assert 68.0 < longitude < 98.0
        assert 6.0 < latitude < 38.0


class TestFailedDelivery:
    @respx.mock
    async def test_a_refused_alert_stays_queued(self, session: Session, settings: Settings) -> None:
        # The property the whole trail depends on. Marking it delivered would
        # lose it, and an authority would never learn of a hotspot the system
        # believes it reported.
        raised = _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(400))

        outcome = await alert_delivery_service.deliver_pending(session, _configured(settings))

        assert outcome.failed == raised
        assert outcome.delivered == 0
        assert alert_delivery_service.pending_count(session) == raised

    @respx.mock
    async def test_the_failure_reason_is_recorded(
        self, session: Session, settings: Settings
    ) -> None:
        # A silent authority and an unreachable one are different findings, and
        # only the stored reason tells them apart.
        _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))

        await alert_delivery_service.deliver_pending(session, _configured(settings))

        detail = alert_repository.list_alert_details(session)[0]
        assert detail.delivered_at is None
        assert detail.delivery_error is not None

    @respx.mock
    async def test_an_unreachable_endpoint_does_not_lose_alerts(
        self, session: Session, settings: Settings
    ) -> None:
        raised = _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(side_effect=httpx.ConnectError("refused"))

        outcome = await alert_delivery_service.deliver_pending(session, _configured(settings))

        assert outcome.failed == raised
        assert alert_delivery_service.pending_count(session) == raised

    @respx.mock
    async def test_a_later_run_can_still_deliver(
        self, session: Session, settings: Settings
    ) -> None:
        # An outage must delay delivery, never cancel it.
        raised = _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))
        await alert_delivery_service.deliver_pending(session, _configured(settings))

        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
        recovered = await alert_delivery_service.deliver_pending(session, _configured(settings))

        assert recovered.delivered == raised
        assert alert_delivery_service.pending_count(session) == 0


class TestOrdering:
    @respx.mock
    async def test_the_worst_excess_is_delivered_first(
        self, session: Session, settings: Settings
    ) -> None:
        # A queue that cannot be drained in one pass should send the most
        # significant findings first, not the oldest.
        import json

        _raise_alerts(session)
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

        await alert_delivery_service.deliver_pending(session, _configured(settings))

        excesses = [
            json.loads(call.request.content)["measurement"]["standardised_excess"]
            for call in route.calls
        ]
        assert excesses == sorted(excesses, reverse=True)


class TestDeliveryState:
    @respx.mock
    async def test_delivery_is_recorded_separately_from_recording(
        self, session: Session, settings: Settings
    ) -> None:
        _raise_alerts(session)
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(202))

        before = alert_repository.list_alert_details(session)[0]
        assert before.delivered_at is None

        await alert_delivery_service.deliver_pending(
            session, _configured(settings), now=NOW + timedelta(minutes=5)
        )

        after = alert_repository.list_alert_details(session)[0]
        assert after.delivered_at == NOW + timedelta(minutes=5)
        assert after.sent_at < after.delivered_at
