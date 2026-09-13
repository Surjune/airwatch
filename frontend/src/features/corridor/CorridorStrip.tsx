import type { StripSegment } from '@/features/corridor/segments';
import { aqiBand, aqiColour } from '@/lib/aqi';

interface CorridorStripProps {
  readonly label: string;
  readonly segments: readonly StripSegment[];
  /** Which estimate to draw: the forecast itself, or its precautionary upper bound. */
  readonly bound: 'value' | 'upper';
}

/**
 * One band of colour per sample along the route, start on the left.
 *
 * Unsupported stretches are drawn as hatched unknown ground rather than left out,
 * because two coloured samples either side of a gap would otherwise look like a
 * continuous, forecast road.
 */
export function CorridorStrip({ label, segments, bound }: CorridorStripProps) {
  return (
    <div>
      <p className="mb-1 text-xs text-ink-muted">{label}</p>
      <div className="flex h-9 overflow-hidden rounded-[3px] border border-ink/25">
        {segments.map(({ point, gapBefore }) => {
          const value = bound === 'value' ? point.value : point.upper_bound;
          const index = bound === 'value' ? point.aqi : point.upper_bound_aqi;
          return (
            <div key={point.distance_along_km} className="flex h-full flex-1">
              {gapBefore && (
                <div
                  className="h-full w-4 shrink-0 bg-[repeating-linear-gradient(135deg,var(--color-surface-sunken)_0_4px,var(--color-surface)_4px_8px)]"
                  title="No station in range — unknown, not clean"
                />
              )}
              <div
                className="h-full flex-1"
                style={{ backgroundColor: aqiColour(index) }}
                title={`${point.distance_along_km.toFixed(1)} km · ${value.toFixed(0)} µg/m³ · index ${index.toFixed(0)}, ${aqiBand(index)}`}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
