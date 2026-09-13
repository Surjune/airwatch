"""Integration tests for the authority registry built from OpenStreetMap boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.repositories import alert_repository
from app.services import seed_service

pytestmark = pytest.mark.integration

#: Real station positions, as (lon, lat), and the district each must route to.
ROUTES = {
    (77.3152, 28.6469): "East Delhi district administration, Delhi",
    (77.3573, 28.6603): "Ghaziabad district administration",
    (76.9790, 10.9425): "Coimbatore district administration",
    (80.3237, 26.4263): "Kanpur Nagar district administration",
}


def test_the_committed_registry_routes_real_stations_to_their_district(session: Session) -> None:
    seed_service.load_authorities(session)
    session.flush()

    names = alert_repository.authority_names(session)
    for point, district in ROUTES.items():
        matches = alert_repository.authorities_containing(session, point)
        tiers = {tier for _, tier in matches}
        # Every station sits inside a district (tier 1) and its state body (tier 2).
        assert tiers == {1, 2}, point
        assert district in {names[authority_id] for authority_id, _ in matches}


def test_an_authority_dropped_from_the_registry_stops_receiving_alerts(
    session: Session, tmp_path: Path
) -> None:
    square = [[77.0, 28.5], [77.4, 28.5], [77.4, 28.8], [77.0, 28.8]]
    registry = tmp_path / "authorities.json"

    registry.write_text(
        json.dumps({"authorities": [{"name": "Placeholder zone", "jurisdiction": square}]}),
        encoding="utf-8",
    )
    seed_service.load_authorities(session, registry)
    assert alert_repository.authorities_containing(session, (77.2, 28.6))

    registry.write_text(
        json.dumps({"authorities": [{"name": "Real district", "jurisdiction": square}]}),
        encoding="utf-8",
    )
    seed_service.load_authorities(session, registry)
    session.flush()

    matches = alert_repository.authorities_containing(session, (77.2, 28.6))
    # Only the current authority is routed to; the retired row still exists.
    assert len(matches) == 1
    assert alert_repository.count_authorities(session) == 2
