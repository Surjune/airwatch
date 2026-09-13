import { useState } from 'react';

import { Card } from '@/components/ui/Card';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { useSatellite, type SatelliteProduct } from '@/hooks/useSources';
import type { CityKey } from '@/lib/scope';
import { formatColumn, SATELLITE_PRODUCTS } from '@/lib/satellite';

const DAYS = 14;
const WIDTH = 320;
const HEIGHT = 72;
const PAD = 4;

/**
 * Sentinel-5P over the city: a two-week daily series for one column product.
 *
 * Presented as what it is -- the gas in the whole atmospheric column over
 * ~36 km² cells -- beside, not instead of, the ground readings. It is most useful
 * where monitors are fewest, which is why it sits on the overview for every city.
 */
export function SatelliteCard({ city }: { readonly city: CityKey }) {
  const [product, setProduct] = useState<SatelliteProduct>('no2');
  const { data, error, isLoading } = useSatellite(city, product, DAYS);
  const series = data?.series ?? [];
  const latest = series.at(-1);
  const option = SATELLITE_PRODUCTS.find((item) => item.key === product) ?? SATELLITE_PRODUCTS[0];

  return (
    <Card
      title="From orbit · Sentinel-5P"
      description={`${option.description} · daily mean over the city`}
      aside={
        <SegmentedControl
          label="Satellite product"
          options={SATELLITE_PRODUCTS}
          value={product}
          onChange={setProduct}
        />
      }
    >
      {error ? (
        <StatusMessage kind="error" title="Satellite data unavailable" detail={error.message} />
      ) : isLoading ? (
        <Skeleton label="Loading satellite columns" rows={3} />
      ) : series.length === 0 || !latest ? (
        <StatusMessage
          kind="empty"
          title="No satellite days stored"
          detail="Nothing has been fetched for this city and product, or every recent day was clouded out. That is an absence of observation, not clean air."
        />
      ) : (
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-ink">
              {formatColumn(product, latest.value)}
            </span>
            <span className="text-xs text-ink-muted">
              on{' '}
              {new Date(latest.observed_on).toLocaleDateString('en-IN', {
                day: '2-digit',
                month: 'short',
              })}{' '}
              · {latest.cells} of {data?.total_cells ?? '?'} cells observed
            </span>
          </div>
          <Sparkline values={series.map((day) => day.value)} />
          <p className="mt-2 text-xs leading-relaxed text-ink-subtle">
            A column over roughly 36 km² cells, not what anyone breathes at street level. Days with
            no overpass or full cloud cover are left out rather than drawn as zero.
          </p>
        </div>
      )}
    </Card>
  );
}

function Sparkline({ values }: { readonly values: readonly number[] }) {
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const step = values.length > 1 ? (WIDTH - PAD * 2) / (values.length - 1) : 0;
  const points = values.map((value, index) => {
    const x = PAD + index * step;
    const y = HEIGHT - PAD - ((value - low) / span) * (HEIGHT - PAD * 2);
    return [x, y] as const;
  });
  const path = points
    .map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const last = points.at(-1);

  return (
    <svg
      viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
      className="mt-3 h-20 w-full"
      role="img"
      aria-label="Daily values over the last two weeks"
      preserveAspectRatio="none"
    >
      <path
        d={`${path} L${String(WIDTH - PAD)},${String(HEIGHT)} L${String(PAD)},${String(HEIGHT)} Z`}
        fill="var(--color-accent-subtle)"
      />
      <path
        d={path}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      {last && <circle cx={last[0]} cy={last[1]} r={3} fill="var(--color-accent)" />}
    </svg>
  );
}
