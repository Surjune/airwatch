import { Skeleton } from '@/components/ui/Skeleton';
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
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border bg-surface px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink">Live map</h1>
            <p className="text-xs text-ink-muted">
              Latest PM2.5 at each station · hotspots over the last{' '}
              {String(Math.round(DETECTION_WINDOW_HOURS / 24))} days
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Pill label="Stations reporting" value={stations.data?.station_count} />
            <Pill
              label="Hotspots"
              value={hotspots.data?.hotspot_count}
              danger={detected.length > 0}
            />
          </div>
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

/** A compact figure for the map toolbar, where a full stat block would cost map height. */
function Pill({
  label,
  value,
  danger = false,
}: {
  readonly label: string;
  readonly value: number | undefined;
  readonly danger?: boolean;
}) {
  return (
    <span className="inline-flex items-baseline gap-2 rounded-lg border border-border bg-surface-sunken px-3 py-1.5">
      <span className={`text-base font-semibold ${danger ? 'text-danger' : 'text-ink'}`}>
        {value ?? '—'}
      </span>
      <span className="text-xs text-ink-muted">{label}</span>
    </span>
  );
}
