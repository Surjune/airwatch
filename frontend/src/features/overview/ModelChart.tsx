import type { RegionalModel } from '@/lib/regional-model';

/** Drawing box, in SVG units; the drawn size comes from CSS. */
const WIDTH = 320;
const HEIGHT = 80;
const PAD = 4;

type Hour = RegionalModel['hours'][number];

/**
 * The model's last three days and next three, with "now" marked.
 *
 * The past is drawn solid and the forecast dashed, so the line never suggests
 * the model knows tomorrow as well as it reconstructs yesterday.
 */
export function ModelChart({ hours }: { readonly hours: readonly Hour[] }) {
  if (hours.length < 2) return null;
  const values = hours.map((hour) => hour.value);
  const high = Math.max(...values, 1);
  const step = (WIDTH - PAD * 2) / (hours.length - 1);
  const point = (hour: Hour, index: number) =>
    `${(PAD + index * step).toFixed(1)},${(HEIGHT - PAD - (hour.value / high) * (HEIGHT - PAD * 2)).toFixed(1)}`;

  const split = hours.findIndex((hour) => hour.is_forecast);
  const pastEnd = split === -1 ? hours.length : split;
  const past = hours.slice(0, pastEnd).map((hour, index) => point(hour, index));
  const future = hours
    .slice(Math.max(pastEnd - 1, 0))
    .map((hour, index) => point(hour, index + Math.max(pastEnd - 1, 0)));
  const nowX = PAD + Math.max(pastEnd - 1, 0) * step;

  return (
    <svg
      viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
      className="mt-3 h-20 w-full"
      role="img"
      aria-label="Modelled hourly concentration over the last three days and the next three"
      preserveAspectRatio="none"
    >
      <line
        x1={nowX}
        x2={nowX}
        y1={0}
        y2={HEIGHT}
        stroke="var(--color-border-strong)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
      {past.length > 1 && (
        <polyline
          points={past.join(' ')}
          fill="none"
          stroke="var(--color-ink)"
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {future.length > 1 && (
        <polyline
          points={future.join(' ')}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}
