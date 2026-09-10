interface RangeBarProps {
  readonly value: number;
  readonly spread: number;
  readonly max: number;
  readonly colour: string;
}

/**
 * A value drawn inside a band, with the band as the point.
 *
 * The name is deliberately neutral because two different quantities are drawn
 * this way. For a forecast the band is uncertainty: validation put the typical
 * reconstruction error near 10 ug/m3 and the forecast error near 16, so a bare
 * bar would imply a precision the number does not have. For a hotspot the band
 * is the excess over what neighbours predicted. Calling this an "uncertainty
 * bar" while drawing an excess would misdescribe half its uses.
 */
export function RangeBar({ value, spread, max, colour }: RangeBarProps) {
  const scale = (amount: number) =>
    `${String(Math.min(100, Math.max(0, (amount / max) * 100)))}%`;
  const low = Math.max(0, value - spread);
  const high = value + spread;

  return (
    <div className="relative h-3 w-full overflow-hidden rounded bg-neutral-200">
      <div
        className="absolute h-full bg-neutral-400/50"
        style={{ left: scale(low), width: scale(high - low) }}
        title={`plausible range ${low.toFixed(0)}–${high.toFixed(0)}`}
      />
      <div
        className="absolute h-full w-[3px]"
        style={{ left: scale(value), backgroundColor: colour }}
        title={`estimate ${value.toFixed(0)}`}
      />
    </div>
  );
}
