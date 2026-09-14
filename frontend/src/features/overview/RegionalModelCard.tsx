import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { Resource } from '@/hooks/useAnalysis';
import { ModelChart } from '@/features/overview/ModelChart';
import { describeBias, type RegionalModel } from '@/lib/regional-model';
import { istDateTime } from '@/lib/time';

interface RegionalModelCardProps {
  readonly model: Resource<RegionalModel>;
  readonly cityLabel: string;
  readonly pollutantLabel: string;
}

/**
 * The CAMS regional model over the city: every hour, past and forecast.
 *
 * Where monitors are silent this is the only hourly number there is, which is
 * exactly why it is framed so carefully: labelled as modelled, drawn with its
 * forecast dashed, and followed by how it compared with this city's monitors
 * before anyone reads the figure as the air on their street.
 */
export function RegionalModelCard({ model, cityLabel, pollutantLabel }: RegionalModelCardProps) {
  const { data, error, isLoading } = model;

  return (
    <Card
      eyebrow="Modelled · CAMS via Open-Meteo"
      title={`Regional model: ${pollutantLabel} across ${cityLabel}, hour by hour`}
    >
      {error ? (
        <StatusMessage kind="error" title="Regional model unavailable" detail={error.message} />
      ) : isLoading ? (
        <Skeleton label="Loading the regional model" rows={3} />
      ) : !data?.latest ? (
        <StatusMessage
          kind="empty"
          title="No model hours stored for this city yet"
          detail="The worker fetches the model every hour. Until the first fetch, there is nothing to show — not clean air."
        />
      ) : (
        <div>
          <dl className="grid grid-cols-3 gap-3">
            <Figure
              label={`Now · ${istDateTime(data.latest.observed_at)} IST`}
              value={data.latest.value}
            />
            <Figure label="Next 24 h peak" value={data.next_day_peak} />
            <Figure label="Next 72 h peak" value={data.outlook_peak} />
          </dl>
          <ModelChart hours={data.hours} />
          <p className="figure mt-1 flex justify-between text-[11px] text-ink-subtle">
            <span>3 days ago</span>
            <span>now</span>
            <span>+3 days (forecast, dashed)</span>
          </p>
          <p className="mt-3 border-t border-border pt-3 text-[13px] leading-relaxed text-ink">
            {describeBias(data.comparison)}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-ink-subtle">{data.notice}</p>
        </div>
      )}
    </Card>
  );
}

function Figure({ label, value }: { readonly label: string; readonly value: number | null }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[11px] font-medium text-ink-subtle">{label}</dt>
      <dd className="figure mt-0.5 text-xl font-medium text-ink">
        {value === null ? '—' : value.toFixed(0)}
        <span className="ml-1 text-xs font-normal text-ink-muted">µg/m³</span>
      </dd>
    </div>
  );
}
