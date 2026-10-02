import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { WhoBadge } from '@/components/ui/WhoBadge';
import { ModelStandIn } from '@/features/overview/ModelStandIn';
import type { Resource, StationsResponse } from '@/hooks/useAnalysis';
import { BACKUP_NOTE, BACKUP_TAG, isBackup } from '@/lib/origin';
import type { RegionalModel } from '@/lib/regional-model';
import { rankRecent, RECENT_READING_HOURS } from '@/lib/readings';
import { timeAgo } from '@/lib/time';

/** Rows shown: enough to see the pattern, few enough to read at a glance. */
const SHOWN = 6;

/** Unit the dashboard's pollutants, PM2.5 and PM10, are read in. */
const UNIT = 'µg/m³';

/**
 * The latest hourly reading at each reference monitor, highest first, among the
 * monitors that have reported recently.
 *
 * This is the one place the overview ranks by concentration, and it says so: it
 * answers "where is the air worst", which a resident asks, and is kept apart from
 * hotspots, which answer "where is something unexpected happening".
 *
 * Beside each reading, the monitor's last 24 hours are set against WHO's
 * 24-hour guideline -- a day's average against a daily level, never the hour's
 * reading against it.
 */
export function MonitorReadings({
  stations,
  model,
  pollutantLabel,
}: {
  readonly stations: Resource<StationsResponse>;
  /** The regional model, offered in place of a current reading when no monitor has one. */
  readonly model: Resource<RegionalModel>;
  readonly pollutantLabel: string;
}) {
  const all = stations.data?.readings ?? [];
  const guideline = stations.data?.who_guideline_24h ?? null;
  const { recent, staleCount } = rankRecent(all);
  // With nothing recent at all, the old readings are still better than an empty
  // card -- shown newest first, so their age is the first thing read.
  const readings =
    recent.length > 0
      ? recent
      : [...all].sort((a, b) => b.observed_at.localeCompare(a.observed_at));

  const nothingRecent = recent.length === 0;
  const shown = readings.slice(0, SHOWN);
  const anyBackup = shown.some((reading) => isBackup(reading.origin));

  return (
    <Card
      eyebrow={
        anyBackup ? 'Reference monitors · OpenAQ · aqicn.org' : 'Reference monitors · OpenAQ'
      }
      title={`Latest ${pollutantLabel} at each monitor`}
      description={
        nothingRecent
          ? `No monitor has reported in the last ${String(RECENT_READING_HOURS)} hours. AirWatch checks every hour and shows new readings as soon as they arrive`
          : `Reported in the last ${String(RECENT_READING_HOURS)} hours, highest first`
      }
      flush
    >
      {stations.error ? (
        <div className="p-4">
          <StatusMessage
            kind="error"
            title="Stations unavailable"
            detail={stations.error.message}
          />
        </div>
      ) : stations.isLoading ? (
        <div className="p-4">
          <Skeleton label="Loading stations" rows={5} />
        </div>
      ) : (
        <>
          {nothingRecent && <ModelStandIn model={model} pollutantLabel={pollutantLabel} />}
          {readings.length === 0 ? (
            <div className="p-4">
              <StatusMessage
                kind="empty"
                title={`No monitor has reported ${pollutantLabel} recently`}
                detail="That is a gap in monitoring, not clean air. Try the other pollutant: some sites report only one."
              />
            </div>
          ) : (
            <ol className="divide-y divide-border">
              {shown.map((reading, index) => (
                <li
                  key={reading.station_id}
                  className="flex items-center gap-3 px-4 py-2.5 sm:px-5"
                >
                  <span className="figure w-4 shrink-0 text-xs text-ink-subtle">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{reading.name}</p>
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-subtle">
                      <span>
                        {reading.category} · {timeAgo(reading.observed_at)}
                        {isBackup(reading.origin) && ` · ${BACKUP_TAG}`}
                      </span>
                      {guideline !== null &&
                        reading.daily_mean !== null &&
                        reading.who_multiple !== null && (
                          <WhoBadge
                            dailyMean={reading.daily_mean}
                            multiple={reading.who_multiple}
                            guideline={guideline}
                            unit={UNIT}
                          />
                        )}
                    </p>
                  </div>
                  <span className="figure shrink-0 text-right text-[13px] text-ink-muted">
                    {reading.value.toFixed(0)}
                    <span className="ml-0.5 text-[11px]">{UNIT}</span>
                  </span>
                  <span className="w-12 shrink-0 text-right">
                    <AqiChip aqi={reading.aqi} />
                  </span>
                </li>
              ))}
              {anyBackup && (
                <li className="px-4 py-2.5 text-xs text-ink-subtle sm:px-5">{BACKUP_NOTE}</li>
              )}
              {recent.length > 0 && staleCount > 0 && (
                <li className="px-4 py-2.5 text-xs text-ink-subtle sm:px-5">
                  {staleCount} {staleCount === 1 ? 'monitor has' : 'monitors have'} not reported in
                  the last {RECENT_READING_HOURS} hours and {staleCount === 1 ? 'is' : 'are'} left
                  out of this ranking.
                </li>
              )}
              {guideline !== null && stations.data && (
                <li className="px-4 py-2.5 text-xs text-ink-subtle sm:px-5">
                  WHO&apos;s 2021 guideline for a 24-hour average of {pollutantLabel} is {guideline}{' '}
                  {UNIT}. It is health guidance, much stricter than India&apos;s legal limit. Each
                  monitor&apos;s last 24 hours are compared with it once it has readings for{' '}
                  {stations.data.daily_mean_min_hours} of them.
                </li>
              )}
            </ol>
          )}
        </>
      )}
    </Card>
  );
}
