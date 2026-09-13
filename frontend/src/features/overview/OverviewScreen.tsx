import { ArrowRight, BellRing, Hourglass, Radar, RadioTower } from 'lucide-react';
import type { ReactNode } from 'react';

import type { ScreenKey } from '@/components/layout/navigation';
import { PollutantToggle } from '@/components/layout/PollutantToggle';
import { Card } from '@/components/ui/Card';
import { MetricCard } from '@/components/ui/MetricCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { NoHotspots } from '@/features/hotspots/NoHotspots';
import { OfficialAqiCard } from '@/features/overview/OfficialAqiCard';
import { SatelliteCard } from '@/features/overview/SatelliteCard';
import { TopHotspots } from '@/features/overview/TopHotspots';
import { WorstStations } from '@/features/overview/WorstStations';
import { Workflow } from '@/features/overview/Workflow';
import { useAlerts } from '@/hooks/useAlerts';
import { useHotspots, useStations } from '@/hooks/useAnalysis';
import { pollutantLabel, useScope } from '@/lib/scope';

/** Detection window, in hours, matching the live map. */
const DETECTION_WINDOW_HOURS = 336;

/**
 * The landing screen: the state of the network in one view, and a way into
 * each part of it.
 *
 * Every figure keeps its window or caveat beside it, and a panel whose request
 * failed says so rather than showing zero -- "0 open alerts" from a dead API
 * would be the most reassuring and least true thing on the page.
 */
export function OverviewScreen({ onNavigate }: { readonly onNavigate: (key: ScreenKey) => void }) {
  const { city, pollutant, current } = useScope();
  const stations = useStations(pollutant, city);
  const hotspots = useHotspots(DETECTION_WINDOW_HOURS, pollutant, city);
  const label = pollutantLabel(pollutant);
  const cityLabel = current?.label ?? '…';
  const alerts = useAlerts(city);

  const figure = (isLoading: boolean, failed: boolean, value: number | undefined): ReactNode =>
    isLoading ? '…' : failed || value === undefined ? '—' : value;

  const open = alerts.alerts.filter((alert) => alert.status !== 'resolved').length;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <section className="relative overflow-hidden rounded-2xl bg-chrome px-6 py-7 text-chrome-ink shadow-raised sm:px-8">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-teal-400/20 blur-3xl"
          />
          <p className="text-xs font-semibold uppercase tracking-wider text-teal-300">
            Pilot network · {cityLabel}
          </p>
          <h1 className="mt-2 max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">
            Find the pollution the city average hides.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-chrome-muted">
            AirWatch compares every monitor with what its neighbours predict, traces unexpected
            spikes back along the wind to candidate sources, and routes an alert to the authority
            responsible — then keeps the record of whether anyone answered.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <NavButton
              primary
              onClick={() => {
                onNavigate('map');
              }}
            >
              Open the live map
            </NavButton>
            <NavButton
              onClick={() => {
                onNavigate('alerts');
              }}
            >
              Authority console
            </NavButton>
          </div>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-ink">{cityLabel} right now</h2>
          <PollutantToggle />
        </div>

        <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            icon={RadioTower}
            label="Stations reporting"
            value={figure(
              stations.isLoading,
              Boolean(stations.error),
              stations.data?.station_count,
            )}
            note={`Latest ${label} reading per site`}
          />
          <MetricCard
            icon={Radar}
            label="Hotspots detected"
            value={figure(
              hotspots.isLoading,
              Boolean(hotspots.error),
              hotspots.data?.hotspot_count,
            )}
            note="Last 14 days, above neighbourhood prediction"
            tone={(hotspots.data?.hotspot_count ?? 0) > 0 ? 'danger' : 'neutral'}
          />
          <MetricCard
            icon={BellRing}
            label="Open alerts"
            value={figure(alerts.isLoading, Boolean(alerts.error), open)}
            note="Routed to an authority, not yet resolved"
            tone={open > 0 ? 'warn' : 'ok'}
          />
          <MetricCard
            icon={Hourglass}
            label="Past deadline"
            value={figure(alerts.isLoading, Boolean(alerts.error), alerts.breaches.length)}
            note="Sent and never acknowledged in time"
            tone={alerts.breaches.length > 0 ? 'danger' : 'ok'}
          />
        </dl>

        <div className="grid gap-6 lg:grid-cols-5">
          <Card
            className="lg:col-span-3"
            title="Where something unexpected is happening"
            description="Hotspots ranked by how far they sit above prediction — not by concentration"
            aside={
              <Link
                onClick={() => {
                  onNavigate('map');
                }}
              >
                View on map
              </Link>
            }
          >
            {hotspots.error ? (
              <StatusMessage
                kind="error"
                title="Hotspots unavailable"
                detail={hotspots.error.message}
              />
            ) : hotspots.isLoading ? (
              <Skeleton label="Detecting hotspots" rows={4} />
            ) : (hotspots.data?.hotspot_count ?? 0) === 0 ? (
              <NoHotspots
                cityLabel={cityLabel}
                stationCount={stations.data?.station_count ?? 0}
                minNeighbours={hotspots.data?.min_neighbours ?? 0}
                pollutantLabel={label}
              />
            ) : (
              <TopHotspots hotspots={hotspots.data?.hotspots ?? []} />
            )}
          </Card>

          <Card
            className="lg:col-span-2"
            title="Highest latest readings"
            description={`CPCB ${label} sub-index at each station's most recent report, with its age`}
          >
            {stations.error ? (
              <StatusMessage
                kind="error"
                title="Stations unavailable"
                detail={stations.error.message}
              />
            ) : stations.isLoading ? (
              <Skeleton label="Loading stations" rows={5} />
            ) : (
              <WorstStations readings={stations.data?.readings ?? []} />
            )}
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <OfficialAqiCard city={city} cityLabel={cityLabel} />
          <SatelliteCard city={city} />
        </div>

        <section aria-labelledby="workflow-heading">
          <h2 id="workflow-heading" className="text-base font-semibold text-ink">
            From detection to accountability
          </h2>
          <p className="mb-3 mt-0.5 text-sm text-ink-muted">
            Four steps, each with its own screen.
          </p>
          <Workflow onNavigate={onNavigate} />
        </section>
      </div>
    </div>
  );
}

function NavButton({
  children,
  onClick,
  primary = false,
}: {
  readonly children: ReactNode;
  readonly onClick: () => void;
  readonly primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
        primary
          ? 'bg-teal-400 text-chrome hover:bg-teal-300'
          : 'bg-white/10 text-chrome-ink hover:bg-white/15'
      }`}
    >
      {children}
      {primary && <ArrowRight aria-hidden className="size-4" />}
    </button>
  );
}

function Link({
  children,
  onClick,
}: {
  readonly children: ReactNode;
  readonly onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover"
    >
      {children}
      <ArrowRight aria-hidden className="size-3.5" />
    </button>
  );
}
