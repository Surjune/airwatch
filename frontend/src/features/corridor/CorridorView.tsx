import { useMemo, useState } from 'react';

import { StatusMessage } from '@/components/ui/StatusMessage';
import { useCorridorForecast } from '@/hooks/useAnalysis';
import { aqiBand, aqiColour } from '@/lib/aqi';

/**
 * Economic corridors worth forecasting, as `lon,lat` polylines.
 *
 * Chosen because pollution follows these rather than administrative lines:
 * freight moves along them, industry clusters beside them, and a person
 * commuting one of them accumulates most of their daily dose on it.
 */
const CORRIDORS = [
  {
    key: 'dwarka-anand-vihar',
    name: 'Dwarka → Anand Vihar',
    note: 'West to east across Delhi, ending at the bus terminal and rail yard.',
    points: '77.03,28.59;77.21,28.61;77.32,28.65',
  },
  {
    key: 'nh48',
    name: 'NH-48 industrial belt',
    note: 'Delhi south-west into the Gurugram manufacturing corridor.',
    points: '77.21,28.61;77.10,28.50;77.03,28.42',
  },
  {
    key: 'ghaziabad',
    name: 'Delhi → Ghaziabad',
    note: 'Eastward into the Indo-Gangetic industrial belt.',
    points: '77.21,28.63;77.32,28.66;77.45,28.67',
  },
] as const;

/** Horizons the forecast was validated at. */
const HORIZONS = [24, 48, 72] as const;

/** A gap wider than this multiple of the median step is unsupported ground. */
const GAP_MULTIPLE = 1.5;

/**
 * Corridor forecast screen.
 *
 * Two things drive the design, and both come from what validation measured.
 *
 * The forecast is a diurnal climatology because climatology beat every learned
 * model on a temporal holdout. That means it resolves the daily cycle and the
 * spatial gradient but has no day-to-day skill, so the screen says where along
 * a route the air turns rather than implying it knows tomorrow will be worse
 * than today.
 *
 * Uncertainty is frequently larger than the signal — 18 ± 28 µg/m³ at the clean
 * end of a real run. Drawing the value alone would be a lie of omission, so the
 * precautionary upper bound is drawn beside it and unsupported stretches are
 * drawn as unknown rather than left to look continuous.
 */
export function CorridorView() {
  const [corridorKey, setCorridorKey] = useState<string>(CORRIDORS[0].key);
  const [horizon, setHorizon] = useState<number>(24);

  const corridor = CORRIDORS.find((item) => item.key === corridorKey) ?? CORRIDORS[0];
  const { data, error, isLoading } = useCorridorForecast(corridor.points, horizon);

  const segments = useMemo(() => {
    const points = data?.points ?? [];
    if (points.length === 0) return [];

    const steps: number[] = [];
    for (let index = 1; index < points.length; index += 1) {
      const current = points[index];
      const previous = points[index - 1];
      if (current && previous) {
        steps.push(current.distance_along_km - previous.distance_along_km);
      }
    }
    steps.sort((a, b) => a - b);
    const median = steps[Math.floor(steps.length / 2)] ?? 1;

    return points.map((point, index) => {
      const previous = index > 0 ? points[index - 1] : undefined;
      return {
        point,
        // A jump wider than the sampling step means the network supported
        // nothing in between, which has to read as unknown rather than as
        // continuity.
        gapBefore:
          previous !== undefined &&
          point.distance_along_km - previous.distance_along_km > median * GAP_MULTIPLE,
      };
    });
  }, [data]);

  const uncoveredKm = data ? data.corridor_length_km - data.covered_length_km : 0;

  return (
    <div className="mx-auto flex h-full min-h-0 max-w-4xl flex-col gap-4 overflow-y-auto p-6">
      <header>
        <h2 className="text-base font-semibold">Corridor outlook</h2>
        <p className="mt-1 text-sm text-neutral-600">
          Where along a route the air changes, {horizon} hours ahead. The estimator is a diurnal
          climatology, because it beat every learned model on a temporal holdout — so it resolves
          the daily cycle and the spatial gradient, and cannot say that tomorrow will be worse than
          today.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {CORRIDORS.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={() => {
              setCorridorKey(option.key);
            }}
            className={`rounded px-3 py-1.5 text-xs font-medium ${
              corridorKey === option.key
                ? 'bg-neutral-800 text-white'
                : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
            }`}
          >
            {option.name}
          </button>
        ))}
        <span className="mx-2 w-px bg-neutral-300" />
        {HORIZONS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => {
              setHorizon(option);
            }}
            className={`rounded px-3 py-1.5 text-xs font-medium ${
              horizon === option
                ? 'bg-neutral-800 text-white'
                : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
            }`}
          >
            {option}h
          </button>
        ))}
      </div>

      <p className="text-xs text-neutral-600">{corridor.note}</p>

      {error ? (
        <StatusMessage
          kind="error"
          title="Could not load the corridor forecast"
          detail={`${error.message} An empty strip here would mean the request failed, not that the route is clean.`}
          {...(error.requestId ? { requestId: error.requestId } : {})}
        />
      ) : isLoading ? (
        <StatusMessage kind="loading" title="Forecasting along the route…" />
      ) : !data || data.point_count === 0 ? (
        <StatusMessage
          kind="empty"
          title="No station supports this route"
          detail="Nothing along it is within range of a monitor, so no forecast can be made. That is unknown ground, not clean air."
        />
      ) : (
        <>
          <section className="rounded border border-neutral-200 bg-white p-4">
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold">Forecast</h3>
              <span className="text-xs text-neutral-600">
                {data.covered_length_km.toFixed(1)} of {data.corridor_length_km.toFixed(1)} km
                covered
              </span>
            </div>

            <Strip
              label="Forecast"
              segments={segments}
              valueOf={(point) => point.value}
            />
            <Strip
              label="With uncertainty"
              segments={segments}
              valueOf={(point) => point.upper_bound}
            />

            <p className="mt-3 text-xs text-neutral-600">
              The second strip is the value plus its uncertainty, which is what a precautionary
              decision uses. On this route the uncertainty is often larger than the value itself —
              the forecast is more useful for <em>where</em> the air turns than for the absolute
              level.
            </p>

            {uncoveredKm > 1 && (
              <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
                {uncoveredKm.toFixed(1)} km of this route returned no forecast at all, because no
                station lies within range. That stretch is unknown, not clean.
              </p>
            )}
          </section>

          <section className="rounded border border-neutral-200 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-neutral-200 text-left text-xs text-neutral-600">
                <tr>
                  <th className="px-3 py-2 font-medium">km</th>
                  <th className="px-3 py-2 font-medium">Forecast</th>
                  <th className="px-3 py-2 font-medium">Upper bound</th>
                  <th className="px-3 py-2 font-medium">Band</th>
                </tr>
              </thead>
              <tbody>
                {segments.map(({ point, gapBefore }) => (
                  <tr key={point.distance_along_km} className="border-b border-neutral-100">
                    <td className="px-3 py-1.5 tabular-nums">
                      {point.distance_along_km.toFixed(1)}
                      {gapBefore && (
                        <span className="ml-2 text-xs text-amber-800">after a gap</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {point.value.toFixed(0)} ± {point.uncertainty.toFixed(0)}
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">{point.upper_bound.toFixed(0)}</td>
                    <td className="px-3 py-1.5">{point.category}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

interface StripSegment {
  readonly point: {
    readonly distance_along_km: number;
    readonly value: number;
    readonly uncertainty: number;
    readonly upper_bound: number;
    readonly category: string;
  };
  readonly gapBefore: boolean;
}

/** One band of colour per sample, with unsupported stretches drawn as unknown. */
function Strip({
  label,
  segments,
  valueOf,
}: {
  readonly label: string;
  readonly segments: readonly StripSegment[];
  readonly valueOf: (point: StripSegment['point']) => number;
}) {
  return (
    <div className="mt-3">
      <p className="mb-1 text-xs text-neutral-600">{label}</p>
      <div className="flex h-8 overflow-hidden rounded border border-neutral-300">
        {segments.map(({ point, gapBefore }) => {
          const value = valueOf(point);
          return (
            <div key={point.distance_along_km} className="flex h-full flex-1">
              {gapBefore && (
                <div
                  className="h-full w-3 bg-neutral-200"
                  title="No station in range — unknown, not clean"
                />
              )}
              <div
                className="h-full flex-1"
                style={{ backgroundColor: aqiColour(value) }}
                title={`${point.distance_along_km.toFixed(1)} km · ${value.toFixed(0)} µg/m³ · ${aqiBand(value)}`}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
