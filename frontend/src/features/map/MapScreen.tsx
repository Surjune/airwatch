import { useState } from 'react';

import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { HotspotPanel } from '@/features/hotspots/HotspotPanel';
import { NoHotspots } from '@/features/hotspots/NoHotspots';
import { HotspotSheet } from '@/features/map/HotspotSheet';
import { MapToolbar, type MapLayers } from '@/features/map/MapToolbar';
import { MapView } from '@/features/map/MapView';
import { useHotspots, useStations } from '@/hooks/useAnalysis';
import { useCitizenSensors } from '@/hooks/useCitizenSensors';
import { useLowCostSensors, useSatellite } from '@/hooks/useSources';
import { pollutantLabel, useScope } from '@/lib/scope';

/** Detection window, in hours. Two weeks, matching the ingested history. */
const DETECTION_WINDOW_HOURS = 336;
const HOURS_PER_DAY = 24;

/**
 * The live map screen.
 *
 * The map and the hotspot list are one screen because they answer one question
 * between them: the map says where, the list says how far above what was
 * predicted, and neither is much use alone.
 *
 * A request failure is never drawn as an empty map, which would read as clean
 * air -- the exact misreading this system exists to prevent.
 */
export function MapScreen() {
  const { city, pollutant, current } = useScope();
  const [layers, setLayers] = useState<MapLayers>({
    sensors: true,
    residents: true,
    satellite: false,
  });

  const stations = useStations(pollutant, city);
  const hotspots = useHotspots(DETECTION_WINDOW_HOURS, pollutant, city);
  const sensors = useLowCostSensors(pollutant, city);
  const residents = useCitizenSensors(pollutant, city);
  const satellite = useSatellite(city, 'no2');

  const failure = stations.error ?? hotspots.error;
  const isLoading = stations.isLoading || hotspots.isLoading || current === null;
  const detected = hotspots.data?.hotspots ?? [];
  const label = pollutantLabel(pollutant);
  const cityLabel = current?.label ?? '…';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <MapToolbar
        cityLabel={cityLabel}
        pollutantLabel={label}
        windowDays={Math.round(DETECTION_WINDOW_HOURS / HOURS_PER_DAY)}
        layers={layers}
        onLayersChange={setLayers}
        counts={{
          monitors: stations.data?.station_count,
          sensors: sensors.data?.sensor_count,
          residents: residents.data?.reading_count,
        }}
      />

      <div className="relative flex min-h-0 flex-1">
        <div className="min-h-0 min-w-0 flex-1">
          {failure ? (
            <div className="p-4 sm:p-6">
              <StatusMessage
                kind="error"
                title={
                  failure.isConfigurationFailure
                    ? 'The deployment is misconfigured'
                    : 'Could not load air quality data'
                }
                detail={`${failure.message} An empty map here would mean the request failed, not that the air is clean.`}
                {...(failure.requestId ? { requestId: failure.requestId } : {})}
              />
            </div>
          ) : isLoading ? (
            <div className="p-4 sm:p-6">
              <Skeleton label="Loading stations and detected hotspots" rows={5} />
            </div>
          ) : (
            <MapView
              readings={stations.data?.readings ?? []}
              hotspots={detected}
              centre={[current.centre.longitude, current.centre.latitude]}
              radiusM={current.radius_m}
              pollutantLabel={label}
              sensors={layers.sensors ? (sensors.data?.readings ?? []) : []}
              residents={layers.residents ? (residents.data?.readings ?? []) : []}
              satellite={
                layers.satellite && satellite.data
                  ? { cells: satellite.data.cells, product: 'no2' }
                  : null
              }
            />
          )}
        </div>

        <HotspotSheet count={hotspots.data?.hotspot_count}>
          {failure ? (
            <div className="p-4">
              <StatusMessage kind="error" title="Hotspot detection unavailable" />
            </div>
          ) : isLoading ? (
            <div className="p-4">
              <Skeleton label="Detecting hotspots" rows={4} />
            </div>
          ) : detected.length === 0 ? (
            <div className="p-4">
              <NoHotspots
                cityLabel={cityLabel}
                stationCount={stations.data?.station_count ?? 0}
                minNeighbours={hotspots.data?.min_neighbours ?? 0}
                pollutantLabel={label}
              />
            </div>
          ) : (
            <HotspotPanel hotspots={detected} />
          )}
        </HotspotSheet>
      </div>
    </div>
  );
}
