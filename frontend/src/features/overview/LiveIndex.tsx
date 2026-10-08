import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import type { LiveStation, OfficialStation } from '@/hooks/useSources';
import { BACKUP_NOTE, BACKUP_TAG, isBackup } from '@/lib/origin';
import { pollutantLabel, type Pollutant } from '@/lib/scope';
import { istDateTime, timeAgo } from '@/lib/time';

/** Other monitors listed under the headline one. */
const OTHERS_SHOWN = 4;

/**
 * AirWatch's own index from the monitors' latest hour, in the official card's
 * place while CPCB's figure is out of date.
 *
 * A resident opening the page wants today's air, and the monitors are often
 * still reporting it when CPCB's feed is not. The card never takes CPCB's name:
 * its heading, its note and CPCB's last figure beneath it keep the two apart.
 */
export function LiveIndex({
  lead,
  others,
  official,
  cityLabel,
}: {
  /** The monitor with the highest current index. */
  readonly lead: LiveStation;
  /** The other monitors with a current reading, worst first. */
  readonly others: readonly LiveStation[];
  /** CPCB's last figure for the city's worst station, however old, if there is one. */
  readonly official: OfficialStation | undefined;
  readonly cityLabel: string;
}) {
  const shown = [lead, ...others.slice(0, OTHERS_SHOWN)];
  const anyBackup = shown.some((station) => station.origins.some(isBackup));
  const anyOpenAq = shown.some((station) => station.origins.some((origin) => !isBackup(origin)));
  const relays = [anyOpenAq && 'OpenAQ', anyBackup && 'aqicn.org'].filter(Boolean).join(' · ');
  const subIndices = Object.entries(lead.sub_indices).sort(([, a], [, b]) => b - a);

  return (
    <Card
      eyebrow={`AirWatch live index · monitors via ${relays}`}
      title={`What the monitors show for ${cityLabel} now`}
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <AqiChip aqi={lead.aqi} size="lg" />
        <div className="min-w-0 text-right">
          <p className="truncate text-sm font-medium text-ink">{lead.name}</p>
          <p className="text-xs text-ink-subtle">
            Set by {pollutantLabel(lead.dominant_pollutant)} · {timeAgo(lead.observed_at)}
            {lead.origins.some(isBackup) && ` · ${BACKUP_TAG}`}
          </p>
        </div>
      </div>
      <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-3">
        {subIndices.map(([pollutant, value]) => (
          <div key={pollutant} className="flex items-baseline gap-1.5">
            <dt className="text-xs text-ink-muted">{pollutantLabel(pollutant as Pollutant)}</dt>
            <dd className="figure text-[13px] text-ink">{Math.round(value)}</dd>
          </div>
        ))}
        <p className="w-full text-xs text-ink-subtle">
          {official
            ? `CPCB’s official index for ${cityLabel} has not updated since ${istDateTime(official.reported_at)} IST.`
            : `CPCB’s official index for ${cityLabel} is not available.`}{' '}
          This figure is AirWatch’s own: each monitor’s latest hourly PM2.5 and PM10 on CPCB’s
          scale, the higher of the two. CPCB’s index averages 24 hours and adds gases, so its figure
          can differ.
        </p>
      </dl>
      <ul className="mt-4 divide-y divide-border border-t border-border">
        {others.slice(0, OTHERS_SHOWN).map((station) => (
          <li key={station.station_id} className="flex items-center gap-3 py-2">
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{station.name}</span>
            <span className="figure hidden text-xs text-ink-subtle sm:inline">
              {istDateTime(station.observed_at)}
            </span>
            <AqiChip aqi={station.aqi} />
          </li>
        ))}
        {official && (
          <li className="flex items-center gap-3 py-2">
            <span className="min-w-0 flex-1 text-xs text-ink-subtle">
              CPCB’s last official index: {official.station_name},{' '}
              {istDateTime(official.reported_at)} IST
            </span>
            <AqiChip aqi={official.aqi} />
          </li>
        )}
        {anyBackup && <li className="py-2 text-xs text-ink-subtle">{BACKUP_NOTE}</li>}
      </ul>
    </Card>
  );
}
