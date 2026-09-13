import { AqiChip } from '@/components/ui/AqiChip';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { CitizenSensorTier } from '@/hooks/useCitizenSensors';
import { timeAgo } from '@/lib/time';

const SHOWN = 10;

/** Residents' sensor readings in the city over the last day, beside the monitor each was checked against. */
export function RecentReadings({
  tier,
  cityLabel,
}: {
  readonly tier: CitizenSensorTier;
  readonly cityLabel: string;
}) {
  const readings = tier.data?.readings ?? [];

  return (
    <Card
      eyebrow="Last 24 hours"
      title={`Sensor readings in ${cityLabel}`}
      {...(tier.data ? { description: tier.data.note } : {})}
      flush
    >
      {tier.isLoading ? (
        <div className="p-4">
          <Skeleton label="Loading readings" rows={3} />
        </div>
      ) : readings.length === 0 ? (
        <div className="p-4">
          <StatusMessage
            kind="empty"
            title="No readings in the last day"
            detail="This tier only has data when residents contribute it, so an empty list means nobody has, not that the air is clean."
          />
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {readings.slice(0, SHOWN).map((reading) => (
            <li key={reading.reading_id} className="flex items-center gap-3 px-4 py-2.5 sm:px-5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">{reading.sensor_model}</p>
                <p className="truncate text-xs text-ink-subtle">
                  {reading.reference_value !== null
                    ? `${reading.reference_station_name ?? 'Monitor'} read ${reading.reference_value.toFixed(0)}`
                    : 'No monitor in range'}{' '}
                  · {timeAgo(reading.observed_at)}
                </p>
              </div>
              <span className="figure text-[13px] text-ink-muted">
                {reading.value_ugm3.toFixed(0)}
              </span>
              <AqiChip aqi={reading.raw_aqi} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
