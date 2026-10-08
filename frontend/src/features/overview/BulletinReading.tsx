import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import type { CityBulletin, OfficialStation } from '@/hooks/useSources';
import { pollutantLabel } from '@/lib/scope';
import { istDateTime } from '@/lib/time';

/**
 * CPCB's daily bulletin leading the official card, when it is the newest
 * official figure for the city.
 *
 * That happens when no hourly figure is reaching AirWatch at all -- Kanpur in
 * October 2026, with data.gov.in down and OpenAQ silent. The bulletin is still
 * CPCB's own statement of the day's air, so it leads, marked plainly as a
 * once-a-day 24-hour average rather than an hourly reading.
 */
export function BulletinReading({
  bulletin,
  official,
  cityLabel,
}: {
  readonly bulletin: CityBulletin;
  /** CPCB's last hourly report for the city's worst station, however old, if there is one. */
  readonly official: OfficialStation | undefined;
  readonly cityLabel: string;
}) {
  const prominent = bulletin.prominent_pollutants.map((pollutant) => pollutantLabel(pollutant));

  return (
    <Card
      eyebrow="CPCB daily bulletin · 24-hour average"
      title={`What CPCB reports for ${cityLabel}`}
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <AqiChip aqi={bulletin.aqi} size="lg" />
        <div className="min-w-0 text-right">
          <p className="truncate text-sm font-medium text-ink">
            {cityLabel} · {bulletin.stations_reporting} of {bulletin.stations_total} stations
          </p>
          <p className="text-xs text-ink-subtle">
            {prominent.length > 0 ? `Set by ${prominent.join(', ')} · ` : ''}
            24 hours to {istDateTime(bulletin.averaged_until)}
          </p>
        </div>
      </div>
      <p className="mt-4 border-t border-border pt-3 text-xs text-ink-subtle">
        CPCB’s daily bulletin averages the city’s reporting stations over the 24 hours to{' '}
        {istDateTime(bulletin.averaged_until)} IST, once a day.{' '}
        {official
          ? `CPCB’s hourly station feed has not updated for ${cityLabel} since ${istDateTime(official.reported_at)} IST, so this is the newest official figure.`
          : `No hourly station figure for ${cityLabel} is reaching AirWatch, so this is the newest official figure.`}
      </p>
      <ul className="mt-4 divide-y divide-border border-t border-border">
        {official && (
          <li className="flex items-center gap-3 py-2">
            <span className="min-w-0 flex-1 text-xs text-ink-subtle">
              CPCB’s last hourly report: {official.station_name},{' '}
              {istDateTime(official.reported_at)} IST
            </span>
            <AqiChip aqi={official.aqi} />
          </li>
        )}
        <li className="py-2 text-xs text-ink-subtle">
          <a
            href={bulletin.source_url}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2 hover:text-ink"
          >
            The bulletin as CPCB published it
          </a>
        </li>
      </ul>
    </Card>
  );
}
