import type { StationReading } from '@/hooks/useAnalysis';
import { aqiBand, aqiColour } from '@/lib/aqi';
import { timeAgo } from '@/lib/time';

/** Rows shown: enough to see the pattern, few enough to read at a glance. */
const SHOWN = 6;

/**
 * The stations reading highest right now.
 *
 * This is the one place the dashboard ranks by concentration, and it says so:
 * it answers "where is the air worst", which a resident asks, and is kept apart
 * from hotspots, which answer "where is something unexpected happening".
 */
export function WorstStations({ readings }: { readonly readings: readonly StationReading[] }) {
  const worst = [...readings].sort((a, b) => b.aqi - a.aqi).slice(0, SHOWN);
  const top = worst[0]?.aqi ?? 1;

  if (worst.length === 0) {
    return <p className="text-sm text-ink-muted">No station has reported recently.</p>;
  }

  return (
    <ol className="space-y-3">
      {worst.map((reading) => (
        <li key={reading.station_id}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-sm font-medium text-ink">{reading.name}</span>
            <span className="shrink-0 text-sm font-semibold text-ink">
              AQI {Math.round(reading.aqi)}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${String(Math.max((reading.aqi / top) * 100, 4))}%`,
                  background: aqiColour(reading.aqi),
                }}
              />
            </div>
            <span className="w-40 shrink-0 text-right text-xs text-ink-subtle">
              {aqiBand(reading.aqi)} · {timeAgo(reading.observed_at)}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}
