import { Skeleton } from '@/components/ui/Skeleton';
import { Stat, StatRow } from '@/components/ui/Stat';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { HotspotPanel } from '@/features/hotspots/HotspotPanel';
import { MapView } from '@/features/map/MapView';
import { useHotspots, useStations } from '@/hooks/useAnalysis';

/** Detection window, in hours. Two weeks, matching the ingested history. */
const DETECTION_WINDOW_HOURS = 336;

/**
 * The live map screen.
 *
 * Extracted from the shell so the shell only routes between screens. The map
 * and the hotspot list are one screen rather than two because they answer one
 * question between them: the map says where, the list says how far above what
 * was predicted, and neither is much use alone.
 *
 * Three states are kept visibly distinct. An API failure that renders as a
 * blank map would read as clean air, which is precisely the misreading this
 * system exists to prevent.
 */
export function MapScreen() {
  const stations = useStations();
  const hotspots = useHotspots(DETECTION_WINDOW_HOURS);

  const failure = stations.error ?? hotspots.error;
  const isLoading = stations.isLoading || hotspots.isLoading;
  const detected = hotspots.data?.hotspots ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="shrink-0 border-b border-border bg-surface px-4 py-2.5 sm:px-6">
          <StatRow>
            <Stat
              label="Stations reporting"
              value={stations.data?.station_count ?? '—'}
              note="Most recent reading per site"
            />
            <Stat
              label="Hotspots detected"
              value={hotspots.data?.hotspot_count ?? '—'}
              note={`Over the last ${String(Math.round(DETECTION_WINDOW_HOURS / 24))} days`}
              tone={detected.length > 0 ? 'danger' : 'neutral'}
            />
          </StatRow>
        </div>

        <div className="min-h-0 flex-1">
          {failure ? (
            <div className="p-4 sm:p-6">
              <StatusMessage
                kind="error"
                title={
                  failure.isConfigurationFailure
                    ? 'The deployment is misconfigured'
                    : 'Could not load air quality data'
                }
                detail={
                  failure.isConfigurationFailure
                    ? `${failure.message} An empty map here would mean missing configuration, not clean air.`
                    : `${failure.message} An empty map here would mean the request failed, not that the air is clean.`
                }
                {...(failure.requestId ? { requestId: failure.requestId } : {})}
              />
            </div>
          ) : isLoading ? (
            <div className="p-4 sm:p-6">
              <Skeleton label="Loading stations and detected hotspots" rows={5} />
            </div>
          ) : (
            <MapView readings={stations.data?.readings ?? []} hotspots={detected} />
          )}
        </div>
      </div>

      <aside
        aria-label="Detected hotspots"
        className="flex max-h-[45vh] min-h-0 shrink-0 flex-col border-t border-border bg-surface lg:max-h-none lg:w-[26rem] lg:border-l lg:border-t-0"
      >
        <div className="shrink-0 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">Detected hotspots</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Ranked by how far above the surrounding network&rsquo;s prediction each sits, not by
            concentration
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
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
              <StatusMessage
                kind="empty"
                title="No hotspots in this window"
                detail="Every station sat within the expected range of its neighbours. That is a real result, not an absence of data."
              />
            </div>
          ) : (
            <HotspotPanel hotspots={detected} />
          )}
        </div>
      </aside>
    </div>
  );
}
