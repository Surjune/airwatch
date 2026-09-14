import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { Resource, StationsResponse } from '@/hooks/useAnalysis';
import { rankRecent, RECENT_READING_HOURS } from '@/lib/readings';
import { timeAgo } from '@/lib/time';

/** Rows shown: enough to see the pattern, few enough to read at a glance. */
const SHOWN = 6;

/**
 * The latest hourly reading at each reference monitor, highest first, among the
 * monitors that have reported recently.
 *
 * This is the one place the overview ranks by concentration, and it says so: it
 * answers "where is the air worst", which a resident asks, and is kept apart from
 * hotspots, which answer "where is something unexpected happening".
 */
export function MonitorReadings({
  stations,
  pollutantLabel,
}: {
  readonly stations: Resource<StationsResponse>;
  readonly pollutantLabel: string;
}) {
  const all = stations.data?.readings ?? [];
  const { recent, staleCount } = rankRecent(all);
  // With nothing recent at all, the old readings are still better than an empty
  // card -- shown newest first, so their age is the first thing read.
  const readings =
    recent.length > 0
      ? recent
      : [...all].sort((a, b) => b.observed_at.localeCompare(a.observed_at));

  return (
    <Card
      eyebrow="Reference monitors · OpenAQ"
      title={`Latest ${pollutantLabel} at each monitor`}
      description={
        recent.length > 0
          ? `Reported in the last ${String(RECENT_READING_HOURS)} hours, highest first`
          : `No monitor has reported in the last ${String(RECENT_READING_HOURS)} hours; the most recent readings are shown with their age`
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
      ) : readings.length === 0 ? (
        <div className="p-4">
          <StatusMessage
            kind="empty"
            title={`No monitor has reported ${pollutantLabel} recently`}
            detail="That is a gap in monitoring, not clean air. Try the other pollutant: some sites report only one."
          />
        </div>
      ) : (
        <ol className="divide-y divide-border">
          {readings.slice(0, SHOWN).map((reading, index) => (
            <li key={reading.station_id} className="flex items-center gap-3 px-4 py-2.5 sm:px-5">
              <span className="figure w-4 shrink-0 text-xs text-ink-subtle">{index + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">{reading.name}</p>
                <p className="text-xs text-ink-subtle">
                  {reading.category} · {timeAgo(reading.observed_at)}
                </p>
              </div>
              <span className="figure shrink-0 text-right text-[13px] text-ink-muted">
                {reading.value.toFixed(0)}
                <span className="ml-0.5 text-[11px]">µg/m³</span>
              </span>
              <span className="w-12 shrink-0 text-right">
                <AqiChip aqi={reading.aqi} />
              </span>
            </li>
          ))}
          {recent.length > 0 && staleCount > 0 && (
            <li className="px-4 py-2.5 text-xs text-ink-subtle sm:px-5">
              {staleCount} {staleCount === 1 ? 'monitor has' : 'monitors have'} not reported in the
              last {RECENT_READING_HOURS} hours and {staleCount === 1 ? 'is' : 'are'} left out of
              this ranking.
            </li>
          )}
        </ol>
      )}
    </Card>
  );
}
