"""Ingestion: pull from upstreams, normalise, persist.

The only place the three tiers are brought together. Business rules live here;
the clients below know nothing about the database, and the repositories know
nothing about the providers.

Two rules govern every path through this module:

* **Normalise units at the boundary, once.** A reading is converted into the unit
  its CPCB breakpoint table expects before it is stored, so nothing downstream
  has to remember that CO is milligrams while everything else is micrograms, or
  that OpenAQ reports gases as mixing ratios.
* **A failing upstream fails loudly and alone.** One provider being down must not
  abort the others, but it must never be recorded as "no pollution found" either.
  Each source reports its own outcome, and the caller sees which succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core import aqi
from app.core.config import Settings
from app.core.constants import BACKFILL_DAYS
from app.core.enums import Pollutant, StationTier
from app.core.exceptions import AirWatchError
from app.core.geo import LonLat
from app.core.h3_grid import point_to_cell
from app.core.logging import get_logger
from app.external.firms_client import FirmsClient
from app.external.openaq_client import OpenAQClient, OpenAQLocation, OpenAQReading
from app.external.openmeteo_client import OpenMeteoClient
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import FireRow, MeasurementRow, WeatherRow
from app.repositories.session import session_scope

logger = get_logger(__name__)

#: Provider label recorded against stations from OpenAQ.
_OPENAQ_SOURCE = "OpenAQ"


@dataclass(slots=True)
class SourceResult:
    """Outcome of ingesting one upstream."""

    source: str
    succeeded: bool
    records: int = 0
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class IngestionReport:
    """Outcome of a full ingestion run."""

    started_at: datetime
    finished_at: datetime
    results: list[SourceResult] = field(default_factory=list)

    @property
    def total_records(self) -> int:
        return sum(result.records for result in self.results if result.succeeded)

    @property
    def all_succeeded(self) -> bool:
        return all(result.succeeded for result in self.results)

    @property
    def failed_sources(self) -> list[str]:
        return [result.source for result in self.results if not result.succeeded]


class IngestionService:
    """Fetches from every configured upstream and persists the results."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def ingest_all(
        self,
        centre: LonLat,
        *,
        radius_m: int = 25_000,
        fire_bbox: tuple[float, float, float, float] | None = None,
    ) -> IngestionReport:
        """Ingest air quality, weather and fires around a point.

        Args:
            centre: ``(lon, lat)`` of the city being ingested.
            radius_m: Station search radius.
            fire_bbox: ``(west, south, east, north)`` for fire detection. When
                omitted, fires are skipped rather than guessed at from the radius.

        Returns:
            A report naming every source and whether it succeeded. A failure in
            one source never aborts the others, but is never silently swallowed.
        """
        started = datetime.now(UTC)
        results: list[SourceResult] = [
            await self._ingest_air_quality(centre, radius_m),
            await self._ingest_weather(centre),
        ]
        if fire_bbox is not None:
            results.append(await self._ingest_fires(fire_bbox))

        report = IngestionReport(started_at=started, finished_at=datetime.now(UTC), results=results)
        logger.info(
            "ingestion.completed",
            total_records=report.total_records,
            failed_sources=report.failed_sources,
        )
        return report

    async def backfill_history(
        self,
        centre: LonLat,
        *,
        pollutant: Pollutant = Pollutant.PM25,
        days: int = BACKFILL_DAYS,
        radius_m: int = 25_000,
    ) -> SourceResult:
        """Pull hourly history for one pollutant across every active station.

        A single snapshot per station cannot support a fusion model: with one
        time point the only thing to learn from is 60 spatial samples. History
        turns that into thousands, and lets leave-one-station-out validation
        measure something meaningful.

        Args:
            centre: ``(lon, lat)`` of the city.
            pollutant: Which pollutant to backfill. One at a time, because each
                station-pollutant pair costs a request.
            days: Days of history to pull.
            radius_m: Station search radius.

        Returns:
            A result carrying the number of hourly readings stored.
        """
        source = f"OpenAQ history ({pollutant.value})"
        try:
            api_key = self._settings.require("openaq_api_key")
            date_to = datetime.now(UTC)
            date_from = date_to - timedelta(days=days)
            stored = 0

            async with OpenAQClient(api_key) as client:
                locations = client.active_locations(
                    await client.list_locations(centre, radius_m=radius_m)
                )
                logger.info(
                    "backfill.started",
                    stations=len(locations),
                    pollutant=pollutant.value,
                    days=days,
                )

                barren = 0
                for location in locations:
                    written = await self._backfill_location(
                        client, location, pollutant, date_from, date_to
                    )
                    stored += written
                    if written == 0:
                        barren += 1

                if barren:
                    # Worth surfacing rather than silently returning a smaller
                    # number: a station can look active on its station-level
                    # timestamp while the sensor for this pollutant has been
                    # dead for weeks, and that gap is invisible otherwise.
                    logger.info(
                        "backfill.stations_without_data",
                        pollutant=pollutant.value,
                        stations_with_no_readings=barren,
                        stations_total=len(locations),
                    )

            return SourceResult(source=source, succeeded=True, records=stored)
        except AirWatchError as error:
            logger.warning(
                "ingestion.source_failed",
                source=source,
                error_code=error.code,
                error_message=error.message,
            )
            return SourceResult(
                source=source,
                succeeded=False,
                error_code=error.code,
                error_message=error.message,
            )

    async def _backfill_location(
        self,
        client: OpenAQClient,
        location: OpenAQLocation,
        pollutant: Pollutant,
        date_from: datetime,
        date_to: datetime,
    ) -> int:
        """Backfill one station's history for one pollutant."""
        sensor_map = location.pollutant_by_sensor_id()
        sensor_ids = [
            sensor_id for sensor_id, (mapped, _) in sensor_map.items() if mapped is pollutant
        ]
        if not sensor_ids:
            return 0

        with session_scope() as session:
            station_id = station_repository.upsert_station(
                session,
                source=_OPENAQ_SOURCE,
                source_station_id=str(location.id),
                name=location.name,
                tier=StationTier.REFERENCE,
                coordinates=location.coordinates.to_lon_lat(),
                operator=location.provider.name if location.provider else None,
                last_seen_at=location.last_reading_at,
            )

        rows: list[MeasurementRow] = []
        for sensor_id in sensor_ids:
            _, unit = sensor_map[sensor_id]
            hourly = await client.sensor_hourly(sensor_id, date_from=date_from, date_to=date_to)
            for entry in hourly:
                try:
                    value = aqi.to_aqi_unit(pollutant, entry.value, unit)
                except AirWatchError:
                    continue
                rows.append(
                    MeasurementRow(
                        station_id=station_id,
                        observed_at=entry.period_start,
                        pollutant=pollutant,
                        value_raw=value,
                        unit=aqi.CONCENTRATION_UNIT[pollutant],
                    )
                )

        if not rows:
            return 0
        with session_scope() as session:
            return observation_repository.upsert_measurements(session, rows)

    async def _ingest_air_quality(self, centre: LonLat, radius_m: int) -> SourceResult:
        """Ingest reference-tier readings from OpenAQ."""
        try:
            api_key = self._settings.require("openaq_api_key")
            stored = 0

            async with OpenAQClient(api_key) as client:
                locations = await client.list_locations(centre, radius_m=radius_m)
                active = client.active_locations(locations)
                logger.info(
                    "ingestion.openaq_stations",
                    returned=len(locations),
                    active=len(active),
                )

                for location in active:
                    readings = await client.latest_readings(location)
                    if not readings:
                        continue
                    stored += self._persist_location(location, readings)

            return SourceResult(source=_OPENAQ_SOURCE, succeeded=True, records=stored)
        except AirWatchError as error:
            # Typed and expected: a missing key or an upstream outage. Reported,
            # never converted into an empty-but-successful result.
            logger.warning(
                "ingestion.source_failed",
                source=_OPENAQ_SOURCE,
                error_code=error.code,
                error_message=error.message,
            )
            return SourceResult(
                source=_OPENAQ_SOURCE,
                succeeded=False,
                error_code=error.code,
                error_message=error.message,
            )

    def _persist_location(self, location: OpenAQLocation, readings: list[OpenAQReading]) -> int:
        """Store one station and its readings, converting units on the way in."""
        if not readings:
            return 0

        with session_scope() as session:
            station_id = station_repository.upsert_station(
                session,
                source=_OPENAQ_SOURCE,
                source_station_id=str(location.id),
                name=location.name,
                tier=StationTier.REFERENCE,
                coordinates=location.coordinates.to_lon_lat(),
                operator=location.provider.name if location.provider else None,
                last_seen_at=location.last_reading_at,
            )

            rows: list[MeasurementRow] = []
            for reading in readings:
                converted = self._to_storage_unit(reading)
                if converted is None:
                    continue
                value, unit = converted
                rows.append(
                    MeasurementRow(
                        station_id=station_id,
                        observed_at=reading.observed_at,
                        pollutant=reading.pollutant,
                        value_raw=value,
                        unit=unit,
                    )
                )

            return observation_repository.upsert_measurements(session, rows)

    def _to_storage_unit(self, reading: OpenAQReading) -> tuple[float, str] | None:
        """Convert a reading into the unit its AQI table expects.

        Returns None when the conversion is not defined — an unrecognised unit
        from an upstream is dropped with a log line rather than stored under a
        unit it is not in, which would corrupt every index computed from it.
        """
        try:
            value = aqi.to_aqi_unit(reading.pollutant, reading.value, reading.unit)
        except AirWatchError as error:
            logger.warning(
                "ingestion.unit_conversion_failed",
                pollutant=reading.pollutant.value,
                unit=reading.unit,
                error_message=error.message,
            )
            return None
        return value, aqi.CONCENTRATION_UNIT[reading.pollutant]

    async def _ingest_weather(self, centre: LonLat) -> SourceResult:
        """Ingest the wind and boundary-layer field. Needs no credential."""
        source = "Open-Meteo"
        try:
            cell = point_to_cell(centre)
            now = datetime.now(UTC)

            async with OpenMeteoClient() as client:
                # Past days as well as forecast: a back-trajectory needs the wind
                # field for hours that have already happened.
                hours = await client.forecast(centre, forecast_days=3, past_days=2)

            rows = [
                WeatherRow(
                    h3_cell=cell,
                    observed_at=hour.observed_at,
                    wind_u=hour.wind_u,
                    wind_v=hour.wind_v,
                    temperature_c=hour.temperature_c,
                    relative_humidity_pct=hour.relative_humidity_pct,
                    pbl_height_m=hour.pbl_height_m,
                    precipitation_mm=hour.precipitation_mm,
                    is_forecast=hour.observed_at > now,
                )
                for hour in hours
            ]

            with session_scope() as session:
                stored = observation_repository.upsert_weather(session, rows)

            return SourceResult(source=source, succeeded=True, records=stored)
        except AirWatchError as error:
            logger.warning(
                "ingestion.source_failed",
                source=source,
                error_code=error.code,
                error_message=error.message,
            )
            return SourceResult(
                source=source,
                succeeded=False,
                error_code=error.code,
                error_message=error.message,
            )

    async def _ingest_fires(self, bbox: tuple[float, float, float, float]) -> SourceResult:
        """Ingest active-fire detections from NASA FIRMS."""
        source = "NASA FIRMS"
        try:
            map_key = self._settings.require("firms_map_key")

            async with FirmsClient(map_key) as client:
                detections = await client.fires_in_bbox(bbox, day_range=1)

            rows = [
                FireRow(
                    coordinates=detection.coordinates,
                    observed_at=detection.observed_at,
                    confidence=detection.confidence,
                    frp_mw=detection.frp_mw,
                    brightness_k=detection.brightness_k,
                    is_daytime=detection.is_daytime,
                    satellite=detection.satellite,
                )
                for detection in detections
            ]

            with session_scope() as session:
                stored = observation_repository.upsert_fire_detections(session, rows)

            return SourceResult(source=source, succeeded=True, records=stored)
        except AirWatchError as error:
            logger.warning(
                "ingestion.source_failed",
                source=source,
                error_code=error.code,
                error_message=error.message,
            )
            return SourceResult(
                source=source,
                succeeded=False,
                error_code=error.code,
                error_message=error.message,
            )
