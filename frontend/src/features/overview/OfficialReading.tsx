import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { BulletinLine } from '@/features/overview/BulletinLine';
import { BulletinReading } from '@/features/overview/BulletinReading';
import { LiveIndex } from '@/features/overview/LiveIndex';
import type { Resource } from '@/hooks/useAnalysis';
import type {
  Bulletin,
  LiveIndex as LiveIndexData,
  OfficialAqi,
  OfficialStation,
} from '@/hooks/useSources';
import { officialRelayLabel } from '@/lib/origin';
import { BULLETIN_RECENT_HOURS, isRecent, rankRecent } from '@/lib/readings';
import { pollutantLabel, type Pollutant } from '@/lib/scope';
import { istDateTime, timeAgo } from '@/lib/time';

/** Other stations listed under the headline one. */
const OTHERS_SHOWN = 4;

/**
 * The official index, as CPCB itself published it, leading the page.
 *
 * It leads because it is the number a resident has already seen in the news, so
 * everything AirWatch adds is read against it. The headline station is the one
 * with the highest index; an index is stated only where CPCB would state one.
 *
 * While CPCB's hourly figure is out of date and the monitors are still
 * reporting, AirWatch's own index from their latest hour leads instead, beside
 * CPCB's last figure. With no hourly figure current at all, CPCB's daily bulletin
 * leads if it is; failing that, CPCB's last report stays, marked as old. The
 * bulletin's line stays in view under whichever leads.
 */
export function OfficialReading({
  official,
  live,
  bulletin,
  cityLabel,
}: {
  readonly official: Resource<OfficialAqi>;
  readonly live: Resource<LiveIndexData>;
  readonly bulletin: Resource<Bulletin>;
  readonly cityLabel: string;
}) {
  const { data, error, isLoading } = official;
  const ranked = [...(data?.stations ?? [])].sort((a, b) => (b.aqi ?? -1) - (a.aqi ?? -1));
  const [lead, ...others] = ranked;
  const officialCurrent = lead !== undefined && isRecent(lead.reported_at);
  const [liveLead, ...liveOthers] = rankRecent(live.data?.stations ?? []).recent;
  const daily = bulletin.data?.bulletin ?? null;
  const dailyCurrent =
    daily !== null && isRecent(daily.averaged_until, new Date(), BULLETIN_RECENT_HOURS);
  const waiting = isLoading || (!officialCurrent && (live.isLoading || bulletin.isLoading));

  if (!waiting && !officialCurrent && liveLead) {
    return (
      <LiveIndex
        lead={liveLead}
        others={liveOthers}
        official={lead}
        bulletin={daily}
        cityLabel={cityLabel}
      />
    );
  }
  if (!waiting && !officialCurrent && daily !== null && dailyCurrent) {
    return <BulletinReading bulletin={daily} official={lead} cityLabel={cityLabel} />;
  }

  return (
    <Card
      eyebrow={`Official CPCB index · ${lead ? officialRelayLabel(lead.relay) : 'data.gov.in'}`}
      title={`What CPCB reports for ${cityLabel}`}
    >
      {waiting ? (
        <Skeleton label="Loading the official feed" rows={4} />
      ) : error ? (
        <StatusMessage kind="error" title="Official feed unavailable" detail={error.message} />
      ) : !lead ? (
        <StatusMessage
          kind="empty"
          title={`No official readings stored for ${cityLabel}`}
          detail="The worker fetches CPCB's feed hourly. An empty panel means nothing was fetched, not that the air is clean."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <AqiChip aqi={lead.aqi} size="lg" />
            <div className="min-w-0 text-right">
              <p className="truncate text-sm font-medium text-ink">{lead.station_name}</p>
              <p className="text-xs text-ink-subtle">
                {lead.dominant_pollutant
                  ? `Set by ${pollutantLabel(lead.dominant_pollutant)} · `
                  : ''}
                {timeAgo(lead.reported_at)}
              </p>
            </div>
          </div>
          <SubIndices station={lead} />
          {(others.length > 0 || daily !== null) && (
            <ul className="mt-4 divide-y divide-border border-t border-border">
              {others.slice(0, OTHERS_SHOWN).map((station) => (
                <li key={station.station_name} className="flex items-center gap-3 py-2">
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                    {station.station_name}
                  </span>
                  <span className="figure hidden text-xs text-ink-subtle sm:inline">
                    {istDateTime(station.reported_at)}
                  </span>
                  <AqiChip aqi={station.aqi} />
                </li>
              ))}
              {daily !== null && <BulletinLine bulletin={daily} />}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

/** Each pollutant's sub-index at the headline station: the index is the largest of these. */
function SubIndices({ station }: { readonly station: OfficialStation }) {
  const entries = Object.entries(station.sub_indices).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-3">
      {entries.map(([pollutant, value]) => (
        <div key={pollutant} className="flex items-baseline gap-1.5">
          <dt className="text-xs text-ink-muted">{pollutantLabel(pollutant as Pollutant)}</dt>
          <dd className="figure text-[13px] text-ink">{Math.round(value)}</dd>
        </div>
      ))}
      {!isRecent(station.reported_at) ? (
        <p className="w-full text-xs text-ink-subtle">
          CPCB&apos;s feed has carried nothing new for this station since{' '}
          {istDateTime(station.reported_at)} IST. The figures above are its last report, not
          today&apos;s air. AirWatch checks every hour and updates as soon as a new one arrives.
        </p>
      ) : station.aqi === null ? (
        <p className="w-full text-xs text-ink-subtle">
          Too few pollutants reported in the last 3 hours for CPCB to state an overall index.
        </p>
      ) : (
        station.oldest_reported_at !== station.reported_at && (
          <p className="w-full text-xs text-ink-subtle">
            CPCB publishes this station&apos;s pollutants an hour or so apart; each one&apos;s
            latest sub-index is combined, the oldest from {istDateTime(station.oldest_reported_at)}{' '}
            IST.
          </p>
        )
      )}
    </dl>
  );
}
