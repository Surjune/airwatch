import { aqiBand, aqiColour } from '@/lib/aqi';

interface AqiChipProps {
  /** The index value, or null where no index can be stated. */
  readonly aqi: number | null;
  readonly size?: 'sm' | 'lg';
}

/**
 * An AQI figure beside a swatch of its band colour, with the band named.
 *
 * The number is never shown in the band colour itself: yellow text on paper is
 * unreadable, and a reading is only useful if it can be read.
 */
export function AqiChip({ aqi, size = 'sm' }: AqiChipProps) {
  if (aqi === null) {
    return <span className="figure text-[13px] text-ink-subtle">no index</span>;
  }
  const rounded = Math.round(aqi);
  if (size === 'lg') {
    return (
      <span className="inline-flex items-center gap-3">
        <span aria-hidden className="h-12 w-1.5" style={{ backgroundColor: aqiColour(aqi) }} />
        <span>
          <span className="figure block text-5xl font-medium leading-none text-ink">{rounded}</span>
          <span className="mt-1.5 block text-sm font-medium text-ink-muted">{aqiBand(aqi)}</span>
        </span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5" title={aqiBand(aqi)}>
      <span
        aria-hidden
        className="size-2.5 rounded-[2px]"
        style={{ backgroundColor: aqiColour(aqi) }}
      />
      <span className="figure text-[13px] font-medium text-ink">{rounded}</span>
    </span>
  );
}
