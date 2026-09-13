import { Send } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { LocationPicker, type PickedPosition } from '@/features/citizen/LocationPicker';
import { PhotoDropzone } from '@/features/citizen/PhotoDropzone';
import { RecentSubmissions } from '@/features/citizen/RecentSubmissions';
import { SubmissionResult } from '@/features/citizen/SubmissionResult';
import type { SubmissionOutcome } from '@/hooks/useCitizen';
import { useCitizen } from '@/hooks/useCitizen';

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
  const [position, setPosition] = useState<PickedPosition | null>(null);
  const [outcome, setOutcome] = useState<SubmissionOutcome | null>(null);

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
      <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4 sm:p-6 lg:p-8">
        <PageHeader
          title="Contribute a photograph"
          description="A photograph cannot measure PM2.5. It can measure how much contrast the atmosphere has removed, and that is what this returns. Photographs taken near a reference monitor also build the relation that lets photographs taken far from one mean something."
        />

        {calibration && (
          <StatusMessage
            kind={calibration.is_calibrated ? 'success' : 'empty'}
            title={
              calibration.is_calibrated
                ? `Calibrated from ${String(calibration.pairs)} co-located submissions`
                : `Not yet calibrated — ${String(calibration.pairs)} of ${String(calibration.pairs_needed)} pairs`
            }
            detail={calibration.explanation}
          />
        )}

        <Card
          title="1. Photograph"
          description="An outdoor daylight scene with something distant in it. Blurred, dark or over-exposed frames are refused — each makes clean air look dirty."
        >
          <PhotoDropzone
            file={file}
            onChange={(next) => {
              setFile(next);
              setOutcome(null);
            }}
          />
        </Card>

        <Card
          title="2. Where it was taken"
          description="Used to compare against the nearest monitor"
        >
          <LocationPicker position={position} onChange={setPosition} />
        </Card>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            size="md"
            onClick={send}
            disabled={!canSubmit}
            isBusy={isSubmitting}
            busyLabel="Measuring…"
          >
            <Send aria-hidden className="size-4" />
            Submit photograph
          </Button>
          {!canSubmit && !isSubmitting && (
            <p className="text-xs text-ink-subtle">Add a photograph and a position to submit.</p>
          )}
        </div>

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

        <RecentSubmissions reports={reports} isLoading={isLoading} />
      </div>
    </div>
  );
}
