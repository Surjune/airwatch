import { useMemo, useState } from 'react';

import { PollutantToggle } from '@/components/layout/PollutantToggle';
import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import { Cell, DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/PageHeader';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { CorridorStrip } from '@/features/corridor/CorridorStrip';
import { CORRIDORS, HORIZONS, type HorizonKey } from '@/features/corridor/corridors';
import { ExposurePanel } from '@/features/corridor/ExposurePanel';
import { markGaps } from '@/features/corridor/segments';
import { useCorridorForecast, useExposureAdvisory } from '@/hooks/useAnalysis';
import { useRegionalModel } from '@/hooks/useSources';
import { ModelOutlook } from '@/features/corridor/ModelOutlook';
import { useScope } from '@/lib/scope';

/** Unforecast length, in km, worth warning about rather than rounding away. */
const UNCOVERED_WARNING_KM = 1;

/**
 * Corridor forecast screen.
 *
 * The forecast is a diurnal climatology, because climatology beat every learned
 * model on a temporal holdout. It resolves the daily cycle and the spatial
 * gradient but has no day-to-day skill, so the screen says where along a route
 * the air turns rather than implying it knows tomorrow will be worse than today.
 *
 * Uncertainty is often larger than the signal, so the precautionary upper bound
 * is drawn beside the value and unsupported stretches are drawn as unknown.
 */
export function CorridorView() {
  const { city, pollutant, current } = useScope();
  const corridors = CORRIDORS[city];
  const [corridorKey, setCorridorKey] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<HorizonKey>('24');

  // A key from the previous city matches nothing here, so the new city's first
  // corridor is shown rather than a stale selection.
  const corridor = corridors.find((item) => item.key === corridorKey) ?? corridors[0];
  const points = corridor?.points ?? '';
  const { data, error, isLoading } = useCorridorForecast(points, Number(horizon), pollutant);
  const advisory = useExposureAdvisory(points, pollutant);
  const model = useRegionalModel(city, pollutant);

  const segments = useMemo(() => markGaps(data?.points ?? []), [data]);
  const uncoveredKm = data ? data.corridor_length_km - data.covered_length_km : 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-4 pb-16 pt-6 sm:px-6 lg:pt-8">
        <PageHeader
          eyebrow={`Step 2 · Forecast · ${current?.label ?? '…'}`}
          title="Corridor forecast"
          description={`Where along a route the air changes, ${horizon} hours ahead. The estimator is a diurnal climatology because it beat every learned model on a temporal holdout — it resolves the daily cycle and the gradient along the road, and cannot say that tomorrow will be worse than today.`}
        />

        <div className="space-y-3">
          <p className="eyebrow">Choose a corridor</p>
          <div className="scroll-row -mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:px-0">
            {corridors.map((option) => {
              const isActive = corridor?.key === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => {
                    setCorridorKey(option.key);
                  }}
                  className={`w-64 shrink-0 rounded-card border p-3 text-left transition-colors sm:w-auto ${
                    isActive
                      ? 'border-ink bg-surface'
                      : 'border-border bg-surface/60 hover:border-ink/40'
                  }`}
                >
                  <span className="block text-sm font-semibold text-ink">{option.name}</span>
                  <span className="mt-1 block text-xs leading-snug text-ink-muted">
                    {option.note}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SegmentedControl
              label="Forecast horizon"
              options={HORIZONS}
              value={horizon}
              onChange={setHorizon}
            />
            <PollutantToggle />
          </div>
        </div>

        {error ? (
          <StatusMessage
            kind="error"
            title="Could not load the corridor forecast"
            detail={`${error.message} An empty strip here would mean the request failed, not that the route is clean.`}
            {...(error.requestId ? { requestId: error.requestId } : {})}
          />
        ) : isLoading ? (
          <Card>
            <Skeleton label="Forecasting along the route" rows={4} />
          </Card>
        ) : !data || data.point_count === 0 ? (
          <>
            <StatusMessage
              kind="empty"
              title="Too few monitors to forecast this route"
              detail="Each point on a route is estimated from several nearby monitors combined, and no point on this one has enough of them in range. A route beside a single monitor is not enough. That is unknown ground, not clean air."
            />
            <ModelOutlook model={model.data} cityLabel={current?.label ?? 'this city'} />
          </>
        ) : (
          <>
            <Card
              eyebrow={`${horizon}-hour outlook`}
              title={corridor?.name ?? 'Route'}
              aside={
                <span className="figure">
                  {data.covered_length_km.toFixed(1)} of {data.corridor_length_km.toFixed(1)} km
                  forecast
                </span>
              }
            >
              <div className="space-y-4">
                <CorridorStrip label="Forecast" segments={segments} bound="value" />
                <CorridorStrip
                  label="Upper bound — value plus uncertainty, what a precautionary decision uses"
                  segments={segments}
                  bound="upper"
                />
                <div className="figure flex justify-between text-[11px] text-ink-subtle">
                  <span>start · {segments[0]?.point.distance_along_km.toFixed(1)} km</span>
                  <span>end · {segments.at(-1)?.point.distance_along_km.toFixed(1)} km</span>
                </div>
              </div>
              {uncoveredKm > UNCOVERED_WARNING_KM && (
                <p className="mt-4 rounded-sm bg-warn-subtle px-3 py-2 text-xs text-warn">
                  {uncoveredKm.toFixed(1)} km of this route returned no forecast, because no station
                  lies within range. That stretch is unknown, not clean.
                </p>
              )}
            </Card>

            <div className="grid gap-4 lg:grid-cols-2">
              <ExposurePanel advisory={advisory.data} isLoading={advisory.isLoading} />
              <Card eyebrow="Samples" title="Along the route" flush>
                <DataTable
                  caption="Forecast samples along the corridor"
                  columns={['km', 'Forecast', 'Upper', 'Band']}
                  numericColumns={[0, 1, 2]}
                >
                  {segments.map(({ point, gapBefore }) => (
                    <tr key={point.distance_along_km}>
                      <Cell numeric>
                        {gapBefore && <span className="mr-2 text-[11px] text-warn">gap ·</span>}
                        {point.distance_along_km.toFixed(1)}
                      </Cell>
                      <Cell numeric>
                        {point.value.toFixed(0)} ± {point.uncertainty.toFixed(0)}
                      </Cell>
                      <Cell numeric muted>
                        {point.upper_bound.toFixed(0)}
                      </Cell>
                      <Cell>
                        <span className="inline-flex items-center gap-2">
                          <AqiChip aqi={point.aqi} />
                          <span className="hidden text-xs text-ink-muted sm:inline">
                            {point.category}
                          </span>
                        </span>
                      </Cell>
                    </tr>
                  ))}
                </DataTable>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
