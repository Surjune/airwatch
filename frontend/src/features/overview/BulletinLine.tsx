import { AqiChip } from '@/components/ui/AqiChip';
import type { CityBulletin } from '@/hooks/useSources';
import { istDateTime } from '@/lib/time';

/**
 * CPCB's daily figure for the city, as one line under whichever card leads.
 *
 * It is the official number the news quotes, so it stays in view even while an
 * hourly figure leads, with the hour its average ran to beside it.
 */
export function BulletinLine({ bulletin }: { readonly bulletin: CityBulletin }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <span className="min-w-0 flex-1 text-xs text-ink-subtle">
        <a
          href={bulletin.source_url}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-ink"
        >
          CPCB’s daily bulletin
        </a>
        : 24-hour average to {istDateTime(bulletin.averaged_until)} IST,{' '}
        {bulletin.stations_reporting} of {bulletin.stations_total} stations
      </span>
      <AqiChip aqi={bulletin.aqi} />
    </li>
  );
}
