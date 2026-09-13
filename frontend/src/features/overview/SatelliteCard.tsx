import { Card } from '@/components/ui/Card';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { Resource } from '@/hooks/useAnalysis';
import type { Satellite, SatelliteProduct } from '@/hooks/useSources';
import { formatColumn, SATELLITE_PRODUCTS } from '@/lib/satellite';

/** Sparkline drawing box, in SVG units; the drawn size comes from CSS. */
const WIDTH = 320;
const HEIGHT = 72;
const PAD = 4;

interface SatelliteCardProps {
  readonly satellite: Resource<Satellite>;
  readonly product: SatelliteProduct;
  readonly onProductChange: (product: SatelliteProduct) => void;
}

/**
 * Sentinel-5P over the city: a two-week daily series for one column product.
 *
 * Presented as what it is -- the gas in the whole atmospheric column over
 * ~36 km² cells -- beside, not instead of, the ground readings. It matters most
 * where monitors are fewest.
 */
export function SatelliteCard({ satellite, product, onProductChange }: SatelliteCardProps) {
  const { data, error, isLoading } = satellite;
  const series = data?.series ?? [];
  const latest = series.at(-1);
  const option = SATELLITE_PRODUCTS.find((item) => item.key === product) ?? SATELLITE_PRODUCTS[0];

  return (
    <Card
      eyebrow="From orbit · Sentinel-5P TROPOMI"
      title={option.description}
      aside={
        <SegmentedControl
          label="Satellite product"
          options={SATELLITE_PRODUCTS}
          value={product}
          onChange={onProductChange}
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
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="figure text-2xl font-medium text-ink">
              {formatColumn(product, latest.value)}
            </span>
            <span className="text-xs text-ink-muted">
              city mean on{' '}
              {new Date(latest.observed_on).toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short',
              })}{' '}
              · {latest.cells} of {data?.total_cells ?? '?'} cells observed
            </span>
          </div>
          <Sparkline values={series.map((day) => day.value)} />
          <p className="mt-2 text-xs leading-relaxed text-ink-subtle">
            {series.length} observed days of the last 14. A column over the whole atmosphere, not
            what anyone breathes at street level; cloudy days are left out rather than drawn as
            zero.
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
        fill="var(--color-surface-sunken)"
      />
      <path
        d={path}
        fill="none"
        stroke="var(--color-ink)"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      {last && <circle cx={last[0]} cy={last[1]} r={3} fill="var(--color-signal)" />}
    </svg>
  );
}
