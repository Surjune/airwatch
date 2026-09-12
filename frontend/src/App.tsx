import { useState } from 'react';

import { StatusMessage } from '@/components/ui/StatusMessage';
import { AlertConsole } from '@/features/alerts/AlertConsole';
import { HotspotPanel } from '@/features/hotspots/HotspotPanel';
import { MapView } from '@/features/map/MapView';
import { useHotspots, useStations } from '@/hooks/useAnalysis';

const DETECTION_WINDOW_HOURS = 336;

/** The two things this system does: show what is happening, and make someone answer for it. */
const VIEWS = [
  { key: 'map', label: 'Map' },
  { key: 'alerts', label: 'Authority console' },
] as const;

type ViewKey = (typeof VIEWS)[number]['key'];

/**
 * Application shell.
 *
 * Three states are kept visibly distinct everywhere: loading, failed, and
 * loaded-but-empty. An API failure that renders as a blank map would read as
 * clean air, which is precisely the misreading this system exists to prevent.
 */
export function App(): React.JSX.Element {
  const [view, setView] = useState<ViewKey>('map');
  const stations = useStations();
  const hotspots = useHotspots(DETECTION_WINDOW_HOURS);

  const failure = stations.error ?? hotspots.error;
  const isLoading = stations.isLoading || hotspots.isLoading;

  return (
    <div className="flex h-screen flex-col bg-neutral-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">AirWatch</h1>
          <p className="text-xs text-neutral-600">
            Hyperlocal air quality · hotspots are places dirtier than their neighbourhood predicts,
            not places where the air is simply bad
          </p>
        </div>
        <nav className="flex gap-1">
          {VIEWS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => {
                setView(option.key);
              }}
              className={`rounded px-3 py-1.5 text-xs font-medium ${
                view === option.key
                  ? 'bg-neutral-800 text-white'
                  : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </nav>
      </header>

      {view === 'alerts' ? (
        <div className="min-h-0 flex-1">
          <AlertConsole />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1">
            {failure ? (
              <div className="p-6">
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
                      : failure.message
                  }
                  {...(failure.requestId ? { requestId: failure.requestId } : {})}
                />
              </div>
            ) : isLoading ? (
              <div className="p-6">
                <StatusMessage kind="loading" title="Loading stations and detected hotspots…" />
              </div>
            ) : (
              <MapView
                readings={stations.data?.readings ?? []}
                hotspots={hotspots.data?.hotspots ?? []}
              />
            )}
          </main>

          <aside className="w-[26rem] shrink-0 overflow-y-auto border-l border-neutral-200 bg-white">
            <div className="border-b border-neutral-200 px-4 py-3">
              <h2 className="text-sm font-semibold">Detected hotspots</h2>
              <p className="text-xs text-neutral-600">
                {hotspots.data
                  ? `${String(hotspots.data.hotspot_count)} over the last ${String(
                      Math.round(hotspots.data.window_hours / 24),
                    )} days · ${String(stations.data?.station_count ?? 0)} stations reporting`
                  : '—'}
              </p>
            </div>

            {failure ? (
              <div className="p-4">
                <StatusMessage kind="error" title="Hotspot detection unavailable" />
              </div>
            ) : isLoading ? (
              <div className="p-4">
                <StatusMessage kind="loading" title="Detecting…" />
              </div>
            ) : (hotspots.data?.hotspots.length ?? 0) === 0 ? (
              <div className="p-4">
                <StatusMessage
                  kind="empty"
                  title="No hotspots detected in this window"
                  detail="Every station sat within the expected range of its neighbours. That is a real result, not an absence of data."
                />
              </div>
            ) : (
              <HotspotPanel hotspots={hotspots.data?.hotspots ?? []} />
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
