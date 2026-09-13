import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { useOfficialAqi } from '@/hooks/useSources';
import { aqiColour } from '@/lib/aqi';
import { pollutantLabel, type CityKey } from '@/lib/scope';
import { istDateTime, timeAgo } from '@/lib/time';

const SHOWN = 6;

/**
 * What CPCB itself published most recently for each station in the city.
 *
 * Shown beside AirWatch's own figures so a reader can check one against the
 * other. An AQI is stated only where CPCB would state one; a station reporting
 * too few pollutants shows its sub-indices without an overall number.
 */
export function OfficialAqiCard({
  city,
  cityLabel,
}: {
  readonly city: CityKey;
  readonly cityLabel: string;
}) {
  const { data, error, isLoading } = useOfficialAqi(city);
  const stations = data?.stations.slice(0, SHOWN) ?? [];
  const latest = data?.stations[0]?.reported_at;

  return (
    <Card
      title="Official CPCB AQI"
      description={
        latest
          ? `As published on data.gov.in · updated ${timeAgo(latest)}`
          : 'As published on data.gov.in'
      }
    >
      {error ? (
        <StatusMessage kind="error" title="Official feed unavailable" detail={error.message} />
      ) : isLoading ? (
        <Skeleton label="Loading the official feed" rows={3} />
      ) : stations.length === 0 ? (
        <StatusMessage
          kind="empty"
          title={`No official readings stored for ${cityLabel}`}
          detail="Run npm run official:coimbatore, or let the worker fetch it. An empty list means nothing was fetched, not that the air is clean."
        />
      ) : (
        <ul className="divide-y divide-border">
          {stations.map((station) => (
            <li
              key={station.station_name}
              className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0"
            >
              <span
                className="flex h-10 w-12 shrink-0 flex-col items-center justify-center rounded-md text-white"
                style={{
                  background:
                    station.aqi !== null ? aqiColour(station.aqi) : 'var(--color-ink-subtle)',
                }}
                title={station.category ?? 'No AQI stated'}
              >
                <span className="text-sm font-semibold leading-none">
                  {station.aqi !== null ? Math.round(station.aqi) : '—'}
                </span>
                <span className="mt-0.5 text-[9px] uppercase tracking-wide opacity-90">AQI</span>
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{station.station_name}</p>
                <p className="truncate text-xs text-ink-subtle">
                  {station.category ?? 'Too few pollutants reported for an AQI'}
                  {station.dominant_pollutant
                    ? ` · set by ${pollutantLabel(station.dominant_pollutant)}`
                    : ''}{' '}
                  · {istDateTime(station.reported_at)} IST
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
