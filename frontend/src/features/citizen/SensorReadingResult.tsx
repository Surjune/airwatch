import { CircleCheck } from 'lucide-react';

import { AqiChip } from '@/components/ui/AqiChip';
import { ReportDownload } from '@/features/citizen/ReportDownload';
import type { SensorReadingAccepted } from '@/hooks/useCitizenSensors';

/** Percent, for presenting a relative difference. */
const PERCENT = 100;

/**
 * What came back from a submitted sensor reading.
 *
 * The comparison with the nearest monitor is the useful part, so it gets the
 * most space; the raw sub-index is labelled as raw, because an optical sensor's
 * number is not yet a number the network stands behind.
 */
export function SensorReadingResult({ accepted }: { readonly accepted: SensorReadingAccepted }) {
  const { reference, colocation } = accepted;
  const difference = reference?.relative_difference;

  return (
    <section className="rounded-card border border-ok/30 bg-surface p-4 sm:p-5" aria-live="polite">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ok">
        <CircleCheck aria-hidden className="size-4" />
        Reading recorded, exactly as reported
      </h2>

      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-ink-muted">Your sensor</dt>
          <dd className="figure mt-1 text-2xl font-medium text-ink">
            {accepted.value_ugm3.toFixed(0)} <span className="text-sm text-ink-muted">µg/m³</span>
          </dd>
          <p className="mt-1 flex items-center gap-2 text-xs text-ink-subtle">
            Raw index <AqiChip aqi={accepted.raw_aqi} /> · uncalibrated
          </p>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Nearest reference monitor</dt>
          {reference ? (
            <>
              <dd className="figure mt-1 text-2xl font-medium text-ink">
                {reference.value.toFixed(0)} <span className="text-sm text-ink-muted">µg/m³</span>
              </dd>
              <p className="mt-1 text-xs text-ink-subtle">
                {reference.station_name}, {(reference.distance_m / 1000).toFixed(1)} km away
                {difference != null &&
                  ` · your sensor reads ${Math.abs(difference * PERCENT).toFixed(0)}% ${difference >= 0 ? 'higher' : 'lower'}`}
              </p>
            </>
          ) : (
            <>
              <dd className="figure mt-1 text-2xl font-medium text-ink-subtle">—</dd>
              <p className="mt-1 text-xs text-ink-subtle">
                No monitor reported within 3 km at that time — exactly the ground this tier covers.
              </p>
            </>
          )}
        </div>
      </dl>

      <p className="mt-4 border-t border-border pt-3 text-[13px] leading-relaxed text-ink-muted">
        <span className="figure text-ink">
          {colocation.pairs}/{colocation.pairs_needed}
        </span>{' '}
        co-located readings towards measuring this tier’s bias. {colocation.explanation}
      </p>

      <ReportDownload reference={accepted.complaint_reference} />
    </section>
  );
}
