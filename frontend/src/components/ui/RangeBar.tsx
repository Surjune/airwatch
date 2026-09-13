interface RangeBarProps {
  readonly value: number;
  readonly spread: number;
  readonly max: number;
  readonly colour: string;
}

/** Percent of a track, clamped so a value beyond the scale stays on it. */
const PERCENT = 100;

/**
 * A value drawn inside a band, with the band as the point.
 *
 * Neutrally named because two quantities are drawn this way. For a forecast the
 * band is uncertainty; for a hotspot it is the excess over what neighbours
 * predicted. Calling this an "uncertainty bar" would misdescribe half its uses.
 */
export function RangeBar({ value, spread, max, colour }: RangeBarProps) {
  const scale = (amount: number) =>
    `${String(Math.min(PERCENT, Math.max(0, (amount / max) * PERCENT)))}%`;
  const low = Math.max(0, value - spread);
  const high = value + spread;

  return (
    <div className="relative h-2.5 w-full overflow-hidden rounded-[2px] bg-surface-sunken">
      <div
        className="absolute h-full bg-ink-subtle/35"
        style={{ left: scale(low), width: scale(high - low) }}
        title={`range ${low.toFixed(0)}–${high.toFixed(0)}`}
      />
      <div
        className="absolute h-full w-[3px]"
        style={{ left: scale(value), backgroundColor: colour }}
        title={`value ${value.toFixed(0)}`}
      />
    </div>
  );
}
