"""The inputs a back-trajectory needs, read from storage in the shape it consumes.

Two services attribute hotspots -- the analysis API to rank candidates, and alert
dispatch to find which jurisdiction holds the likeliest source -- and services
may not import one another. So the translation from stored rows to wind records
and candidate sources lives here, once, rather than in both.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.h3_grid import cell_centroid
from app.ml.attribution import CandidateSource, WindRecord, fire_to_candidate
from app.repositories import observation_repository, station_repository


def wind_records(session: Session, since: datetime) -> list[WindRecord]:
    """Every city's stored wind since a point in time, placed at its cell's centre."""
    return [
        WindRecord(
            coordinates=cell_centroid(record.h3_cell),
            observed_at=record.observed_at,
            wind_u=record.wind_u,
            wind_v=record.wind_v,
        )
        for record in observation_repository.weather_in_window(session, since)
    ]


def candidate_sources(session: Session, since: datetime) -> list[CandidateSource]:
    """Registered sources and recent fire detections, as attribution candidates."""
    sources: list[CandidateSource] = [
        CandidateSource(
            identifier=str(source.id),
            name=source.name,
            source_type=source.source_type,
            coordinates=(float(lon), float(lat)),
            emission_prior=source.emission_prior,
        )
        for source, lon, lat in station_repository.list_sources_with_coordinates(session)
    ]

    for (
        fire_id,
        lon,
        lat,
        observed_at,
        frp_mw,
        confidence,
    ) in observation_repository.fire_detections_in_window(session, since):
        sources.append(
            fire_to_candidate(
                identifier=f"fire-{fire_id}",
                coordinates=(float(lon), float(lat)),
                observed_at=observed_at,
                frp_mw=float(frp_mw),
                confidence=float(confidence),
            )
        )

    return sources
