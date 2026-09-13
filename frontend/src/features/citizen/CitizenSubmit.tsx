import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { isWithinIndia } from '@/lib/geo';
import type { SubmissionOutcome } from '@/hooks/useCitizen';
import { useCitizen } from '@/hooks/useCitizen';

/** Where the submitter's position came from, which changes how much to trust it. */
type PositionSource = 'device' | 'manual' | null;

/**
 * The citizen submission screen.
 *
 * The design problem here is not the upload. It is that a number produced from a
 * phone photograph looks exactly like a number produced from a ~1 crore
 * instrument once both are on a map, and this screen is where that confusion
 * would start. So the hierarchy is deliberate: the haze index is presented as
 * the measurement, a derived concentration appears only when one can be derived,
 * and the calibration state is stated on the screen rather than buried.
 *
 * A refusal is treated as a useful answer and shown with the reason, because
 * every condition that gets a photo refused -- darkness, blur, over-exposure --
 * would otherwise have made clean air look dirty.
 */
export function CitizenSubmit() {
  const { reports, calibration, error, isLoading, isSubmitting, submit } = useCitizen();

  const [file, setFile] = useState<File | null>(null);
  const [position, setPosition] = useState<{
    longitude: number;
    latitude: number;
  } | null>(null);
  const [source, setSource] = useState<PositionSource>(null);
  const [locating, setLocating] = useState(false);
  const [locationProblem, setLocationProblem] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<SubmissionOutcome | null>(null);

  const locate = useCallback(() => {
    setLocationProblem(null);
    if (!('geolocation' in navigator)) {
      setLocationProblem('This browser cannot report a location. Enter coordinates instead.');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (found) => {
        const candidate = {
          longitude: found.coords.longitude,
          latitude: found.coords.latitude,
        };
        // Checked here as well as on the server. A position outside the covered
        // area is far more likely to be a browser default or a transposed pair
        // than a real submission, and saying so now saves a round trip.
        if (!isWithinIndia([candidate.longitude, candidate.latitude])) {
          setLocationProblem(
            'That position is outside the area this deployment covers. Check it before submitting.',
          );
        }
        setPosition(candidate);
        setSource('device');
        setLocating(false);
      },
      (cause) => {
        setLocationProblem(`Could not read a location: ${cause.message}`);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, []);

  const canSubmit = file !== null && position !== null && !isSubmitting;

  const send = useCallback(() => {
    if (file === null || position === null) return;
    void submit({
      file,
      longitude: position.longitude,
      latitude: position.latitude,
      // The file's own modified time is the closest thing a browser exposes to
      // a capture time without parsing EXIF, and for a photo taken to be
      // submitted the two are the same moment.
      capturedAt: new Date(file.lastModified),
    }).then((result) => {
      setOutcome(result);
      if (result?.kind === 'accepted') setFile(null);
    });
  }, [file, position, submit]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4 sm:p-6">
        <PageHeader
          title="Contribute a photograph"
          description={
            'A photograph cannot measure PM2.5. It can measure how much contrast the atmosphere has removed, and that is what this returns. Photographs taken near a reference monitor also build the relation that lets photographs taken far from one mean something.'
          }
        />

        {calibration && (
          <div
            className={`rounded border p-3 text-sm ${
              calibration.is_calibrated
                ? 'border-ok/30 bg-ok-subtle text-ok'
                : 'border-warn/30 bg-warn-subtle text-warn'
            }`}
          >
            <p className="font-medium">
              {calibration.is_calibrated
                ? `Calibrated from ${String(calibration.pairs)} co-located submissions`
                : `Not yet calibrated — ${String(calibration.pairs)} of ${String(
                    calibration.pairs_needed,
                  )} pairs`}
            </p>
            <p className="mt-1">{calibration.explanation}</p>
          </div>
        )}

        <section className="rounded-[--radius-card] border border-border bg-surface p-4">
          <label className="block text-sm font-medium" htmlFor="photo">
            Photograph
          </label>
          <p className="mb-2 text-xs text-ink-muted">
            An outdoor scene with something distant in it, taken in daylight. A blurred, dark or
            over-exposed frame will be refused — each of those makes clean air look dirty.
          </p>
          <input
            id="photo"
            type="file"
            accept="image/*"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setOutcome(null);
            }}
            className="block w-full text-sm"
          />

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button onClick={locate} isBusy={locating} busyLabel="Locating…">
              Use my location
            </Button>
            {position && (
              <span className="text-xs text-ink-muted">
                {position.latitude.toFixed(4)}, {position.longitude.toFixed(4)}
                {source === 'device' ? ' (from this device)' : ''}
              </span>
            )}
          </div>

          {locationProblem && (
            <p className="mt-2 rounded bg-warn-subtle px-2 py-1 text-xs text-warn">
              {locationProblem}
            </p>
          )}

          <div className="mt-4">
            <Button
              variant="primary"
              size="md"
              onClick={send}
              disabled={!canSubmit}
              isBusy={isSubmitting}
              busyLabel="Measuring…"
            >
              Submit photograph
            </Button>
          </div>
          {!canSubmit && !isSubmitting && (
            <p className="mt-2 text-xs text-ink-subtle">
              A photograph and a position are both needed before this can be submitted.
            </p>
          )}
        </section>

        {outcome?.kind === 'rejected' && (
          <StatusMessage
            kind="empty"
            title="This photograph could not be measured"
            detail={outcome.rejection.detail}
          />
        )}

        {outcome?.kind === 'accepted' && <SubmissionResult outcome={outcome} />}

        {error && (
          <StatusMessage
            kind="error"
            title="Could not reach the submission service"
            detail={error.message}
            {...(error.requestId ? { requestId: error.requestId } : {})}
          />
        )}

        <section>
          <h3 className="text-sm font-semibold">Recent submissions</h3>
          {isLoading ? (
            <div className="mt-2">
              <StatusMessage kind="loading" title="Loading submissions…" />
            </div>
          ) : reports.length === 0 ? (
            <div className="mt-2">
              <StatusMessage
                kind="empty"
                title="No submissions in the last day"
                detail="This tier only has data when people contribute it, so an empty list here means nobody has, not that the air is clean."
              />
            </div>
          ) : (
            <ul className="mt-2 divide-y divide-border rounded-[--radius-card] border border-border bg-surface">
              {reports.slice(0, 12).map((report) => (
                <li key={report.report_id} className="flex items-center justify-between px-3 py-2">
                  <span className="text-sm">
                    haze {report.haze_index.toFixed(2)}
                    {report.had_reference && (
                      <span className="ml-2 rounded bg-ok-subtle px-1.5 py-0.5 text-xs text-ok">
                        also calibrates
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-ink-subtle">
                    {report.position.latitude.toFixed(3)}, {report.position.longitude.toFixed(3)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

/** What came back from an accepted photograph. */
function SubmissionResult({ outcome }: { readonly outcome: SubmissionOutcome }) {
  if (outcome.kind !== 'accepted') return null;
  const { report } = outcome;

  return (
    <div className="rounded-[--radius-card] border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold">Measured</h3>

      <p className="mt-2 text-sm">
        Atmospheric haze <strong>{report.haze_index.toFixed(2)}</strong> on a 0–1 scale, where 0 is
        perfectly clear air. This is what the photograph established.
      </p>

      {report.estimate ? (
        <p className="mt-2 text-sm">
          Estimated PM2.5 <strong>{report.estimate.value.toFixed(0)} µg/m³</strong> ±{' '}
          {report.estimate.uncertainty.toFixed(0)}
          {report.estimate.is_extrapolating && (
            <span className="ml-1 text-warn">
              — outside the range the relation was fitted across, so treat it as an extrapolation
            </span>
          )}
        </p>
      ) : (
        <p className="mt-2 rounded bg-warn-subtle px-2 py-1 text-sm text-warn">
          No concentration can be derived from this yet. Your submission still counts: it is one of
          the pairs that will make that possible.
        </p>
      )}

      {report.reference && (
        <p className="mt-2 text-sm text-ink">
          Nearest monitor, {(report.reference.distance_m / 1000).toFixed(1)} km away, reported{' '}
          <strong>{report.reference.value.toFixed(0)} µg/m³</strong>
          {report.reference.agrees === true && ' — consistent with this photograph'}
          {report.reference.agrees === false && ' — which this photograph does not match'}
        </p>
      )}
      {!report.reference && (
        <p className="mt-2 text-sm text-ink">
          No reference monitor was within range, which is exactly the gap this tier exists to fill.
        </p>
      )}
    </div>
  );
}
