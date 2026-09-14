import { Card } from '@/components/ui/Card';
import { describeBias, type RegionalModel } from '@/lib/regional-model';

interface ModelOutlookProps {
  readonly model: RegionalModel | null;
  readonly cityLabel: string;
}

/**
 * What the regional model expects over the city, where no route forecast can be made.
 *
 * Offered in place of an empty screen, and explicitly not as a route forecast:
 * the model averages over tens of kilometres, so it can say whether the next
 * three days look worse than the last three across the city, and nothing about
 * where along a road the air changes.
 */
export function ModelOutlook({ model, cityLabel }: ModelOutlookProps) {
  if (!model?.latest || model.outlook_peak === null) return null;

  const upcoming = model.hours.filter((hour) => hour.is_forecast).map((hour) => hour.value);
  const low = upcoming.length > 0 ? Math.min(...upcoming) : null;

  return (
    <Card eyebrow="Modelled · CAMS via Open-Meteo" title={`City-wide outlook for ${cityLabel}`}>
      <p className="text-sm leading-relaxed text-ink">
        Over the next 72 hours the regional model expects between{' '}
        <strong className="figure font-medium">{low === null ? '—' : low.toFixed(0)}</strong> and{' '}
        <strong className="figure font-medium">{model.outlook_peak.toFixed(0)} µg/m³</strong> across
        the city, against{' '}
        <strong className="figure font-medium">{model.latest.value.toFixed(0)} µg/m³</strong> now.
      </p>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
        {describeBias(model.comparison)}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-ink-subtle">
        Not a route forecast: the model cannot see where along a road the air changes. Use it for
        whether the coming days look better or worse than now.
      </p>
    </Card>
  );
}
