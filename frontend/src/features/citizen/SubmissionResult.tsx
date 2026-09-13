import { CircleCheck } from 'lucide-react';

import { ReportDownload } from '@/features/citizen/ReportDownload';
import type { SubmissionOutcome } from '@/hooks/useCitizen';

/**
 * What came back from an accepted photograph.
 *
 * The haze index is presented as the measurement and any concentration as a
 * derivation from it, because that is the order of what is actually known.
 */
export function SubmissionResult({ outcome }: { readonly outcome: SubmissionOutcome }) {
  if (outcome.kind !== 'accepted') return null;
  const { report } = outcome;

  return (
    <section className="rounded-card border border-ok/30 bg-surface p-4 sm:p-5" aria-live="polite">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ok">
        <CircleCheck aria-hidden className="size-4" />
        Photograph measured
      </h2>

      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium text-ink-subtle">Atmospheric haze</dt>
          <dd className="figure mt-0.5 text-2xl font-medium text-ink">
            {report.haze_index.toFixed(2)}
          </dd>
          <p className="text-xs text-ink-muted">0 is perfectly clear air, 1 fully obscured</p>
        </div>
        <div>
          <dt className="text-xs font-medium text-ink-subtle">Estimated PM2.5</dt>
          {report.estimate ? (
            <>
              <dd className="figure mt-0.5 text-2xl font-medium text-ink">
                {report.estimate.value.toFixed(0)}
                <span className="ml-1 text-sm font-normal text-ink-muted">
                  ± {report.estimate.uncertainty.toFixed(0)} µg/m³
                </span>
              </dd>
              {report.estimate.is_extrapolating && (
                <p className="text-xs text-warn">
                  Outside the range the relation was fitted across — an extrapolation
                </p>
              )}
            </>
          ) : (
            <>
              <dd className="figure mt-0.5 text-2xl font-medium text-ink-subtle">—</dd>
              <p className="text-xs text-ink-muted">
                Not derivable yet. This submission is one of the pairs that will make it possible.
              </p>
            </>
          )}
        </div>
      </dl>

      <p className="mt-4 border-t border-border pt-3 text-sm text-ink-muted">
        {report.reference ? (
          <>
            Nearest monitor, {(report.reference.distance_m / 1000).toFixed(1)} km away, reported{' '}
            <strong className="text-ink">{report.reference.value.toFixed(0)} µg/m³</strong>
            {report.reference.agrees === true && ' — consistent with this photograph.'}
            {report.reference.agrees === false && ' — which this photograph does not match.'}
          </>
        ) : (
          'No reference monitor was within range, which is exactly the gap this tier exists to fill.'
        )}
      </p>

      <ReportDownload reference={report.complaint_reference} />
    </section>
  );
}
