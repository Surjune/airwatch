import type { Resource, StationsResponse } from '@/hooks/useAnalysis';
import type { CitizenReport } from '@/hooks/useCitizen';
import type { SensorReadings } from '@/hooks/useCitizenSensors';
import type { HealthState } from '@/hooks/useHealth';
import type { LowCostSensors, OfficialAqi, Satellite } from '@/hooks/useSources';
import type { RegionalModel } from '@/lib/regional-model';
import { TierTile } from '@/features/overview/TierTile';
import { isRecent, RECENT_READING_HOURS } from '@/lib/readings';
import { MONITORS_FOR_DETECTION, tierState } from '@/lib/tiers';

interface NetworkTiersProps {
  readonly stations: Resource<StationsResponse>;
  readonly official: Resource<OfficialAqi>;
  readonly sensors: Resource<LowCostSensors>;
  readonly photos: readonly CitizenReport[] | null;
  readonly readings: Resource<SensorReadings>;
  readonly satellite: Resource<Satellite>;
  readonly model: Resource<RegionalModel>;
  readonly health: HealthState;
  readonly pollutantLabel: string;
}

/**
 * Every source of evidence, grouped by the three tiers the system is built on.
 *
 * Ground truth is accurate and sparse; the dense tier is everywhere and biased;
 * the coverage tier is complete and coarse. Laying them side by side is the
 * argument for fusing them, and showing each one's count for *this* city is the
 * honest part: in a data-poor city most tiles say how little there is.
 */
export function NetworkTiers({
  stations,
  official,
  sensors,
  photos,
  readings,
  satellite,
  model,
  health,
  pollutantLabel,
}: NetworkTiersProps) {
  // Only what reported lately counts as reporting: a monitor silent for days is
  // still on record, and counting it would describe a network that is not there.
  const monitorCount = stations.data?.readings.filter((reading) =>
    isRecent(reading.observed_at),
  ).length;
  const quietMonitors =
    stations.data && monitorCount !== undefined ? stations.data.station_count - monitorCount : 0;
  const officialCount = official.data?.stations.filter((station) =>
    isRecent(station.reported_at),
  ).length;
  const quietOfficial =
    official.data && officialCount !== undefined ? official.data.station_count - officialCount : 0;
  const residentCount =
    photos === null || readings.data === null
      ? undefined
      : photos.length + readings.data.reading_count;
  const latestPass = satellite.data?.series.at(-1);
  const firms = health.report?.upstreams.find((upstream) => upstream.provider.includes('FIRMS'));

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
      <TierTile
        tier="Tier 1 · ground truth"
        name="Reference monitors"
        value={monitorCount ?? '…'}
        note={`Reported ${pollutantLabel} in the last ${String(RECENT_READING_HOURS)} hours${quiet(quietMonitors)}. Detection needs ${String(MONITORS_FOR_DETECTION)} in range to compare each with its neighbours.`}
        state={tierState(monitorCount, MONITORS_FOR_DETECTION, Boolean(stations.error))}
      />
      <TierTile
        tier="Tier 1 · ground truth"
        name="CPCB official feed"
        value={officialCount ?? '…'}
        note={`Stations in CPCB's live index that reported in the last ${String(RECENT_READING_HOURS)} hours${quiet(quietOfficial)}, fetched hourly from data.gov.in and shown as published.`}
        state={tierState(officialCount, 1, Boolean(official.error))}
      />
      <TierTile
        tier="Tier 2 · dense, biased"
        name="Low-cost sensor networks"
        value={sensors.data?.sensor_count ?? '…'}
        note="Community optical sensors. Shown uncalibrated and kept out of every estimate."
        state={tierState(sensors.data?.sensor_count, 1, Boolean(sensors.error))}
      />
      <TierTile
        tier="Tier 2 · dense, biased"
        name="Residents"
        value={residentCount ?? '…'}
        note={
          residentCount === undefined
            ? 'Photographs and household sensor readings in the last 24 hours.'
            : `${String(photos?.length ?? 0)} photographs and ${String(readings.data?.reading_count ?? 0)} sensor readings in the last 24 hours.`
        }
        state={tierState(residentCount, 1, Boolean(readings.error))}
      />
      <TierTile
        tier="Tier 3 · complete, coarse"
        name="Sentinel-5P satellite"
        value={
          latestPass
            ? `${String(latestPass.cells)}/${String(satellite.data?.total_cells ?? 0)}`
            : '…'
        }
        note={
          latestPass
            ? `Cells with an NO₂ column on ${new Date(latestPass.observed_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}. Fills the ground between monitors, at ~36 km².`
            : 'Daily NO₂, SO₂, CO and aerosol columns over ~36 km² cells.'
        }
        state={tierState(satellite.data?.series.length, 1, Boolean(satellite.error))}
      />
      <TierTile
        tier="Tier 3 · complete, coarse"
        name="Weather and fires"
        value="hourly"
        note={`Open-Meteo wind steers every back-trajectory. NASA FIRMS fire detections ${firms?.configured === false ? 'are not configured' : 'are ranked as candidate sources'}.`}
        state={
          health.isLoading
            ? 'loading'
            : health.error || firms?.configured === false
              ? 'thin'
              : 'live'
        }
      />
      <TierTile
        tier="Tier 3 · modelled, coarse"
        name="CAMS regional air-quality model"
        value={model.data?.latest ? `${model.data.latest.value.toFixed(0)} µg/m³` : '…'}
        note={
          model.data?.latest
            ? `Modelled ${pollutantLabel} over the city this hour, with a 72-hour outlook. Fills every hour monitors miss; checked against them, never used for detection.`
            : 'Hourly modelled concentrations and a 72-hour outlook, for every hour the monitors miss.'
        }
        state={tierState(model.data?.hours.length, 1, Boolean(model.error))}
        className="sm:col-span-2 lg:col-span-3"
      />
    </div>
  );
}

/** ", and 2 more on record gone quiet", or nothing when every station is current. */
function quiet(count: number): string {
  if (count <= 0) return '';
  return `, and ${String(count)} more on record ${count === 1 ? 'has' : 'have'} gone quiet`;
}
