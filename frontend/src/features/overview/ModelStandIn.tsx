import type { Resource } from '@/hooks/useAnalysis';
import { describeBias, type RegionalModel } from '@/lib/regional-model';
import { timeAgo } from '@/lib/time';

/**
 * The regional model's latest hour, offered while no monitor in the city is
 * reporting.
 *
 * A city resting on one monitor goes dark whenever that monitor does. The model
 * keeps a current figure on the page, labelled as modelled and followed by how
 * far it has read from this city's monitors, so it is never mistaken for one.
 */
export function ModelStandIn({
  model,
  pollutantLabel,
}: {
  readonly model: Resource<RegionalModel>;
  readonly pollutantLabel: string;
}) {
  const data = model.data;
  const latest = data?.latest;
  if (!data || !latest) return null;

  return (
    <div className="border-b border-border bg-surface-sunken px-4 py-3 sm:px-5">
      <p className="eyebrow">Meanwhile · CAMS regional model</p>
      <p className="mt-1.5 text-[13px] text-ink">
        Modelled {pollutantLabel} over the city:{' '}
        <span className="figure font-medium">
          {latest.value.toFixed(0)} {data.unit}
        </span>
        , {timeAgo(latest.observed_at)}.
      </p>
      <p className="mt-1 text-xs leading-relaxed text-ink-subtle">
        Modelled, not measured, and averaged over tens of kilometres.{' '}
        {describeBias(data.comparison)}
      </p>
    </div>
  );
}
