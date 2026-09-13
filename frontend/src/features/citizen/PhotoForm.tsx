import { Send } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { ComplaintFields, type ComplaintInput } from '@/features/citizen/ComplaintFields';
import { LocationPicker, type PickedPosition } from '@/features/citizen/LocationPicker';
import { PhotoDropzone } from '@/features/citizen/PhotoDropzone';
import { SubmissionResult } from '@/features/citizen/SubmissionResult';
import type { CitizenTier, SubmissionOutcome } from '@/hooks/useCitizen';

const NO_COMPLAINT: ComplaintInput = { category: null, description: '' };

/**
 * Submit a photograph and see what it measured.
 *
 * A refusal is shown with its reason as a useful answer, because every condition
 * that gets a photo refused -- darkness, blur, over-exposure -- would otherwise
 * have made clean air look dirty.
 */
export function PhotoForm({ tier }: { readonly tier: CitizenTier }) {
  const [file, setFile] = useState<File | null>(null);
  const [position, setPosition] = useState<PickedPosition | null>(null);
  const [outcome, setOutcome] = useState<SubmissionOutcome | null>(null);
  const [complaint, setComplaint] = useState<ComplaintInput>(NO_COMPLAINT);
  const { submit, isSubmitting } = tier;

  const canSubmit = file !== null && position !== null && !isSubmitting;

  const send = useCallback(() => {
    if (file === null || position === null) return;
    void submit({
      file,
      longitude: position.longitude,
      latitude: position.latitude,
      // The file's modified time is the closest thing a browser exposes to a
      // capture time without parsing EXIF, and for a photo taken to be submitted
      // the two are the same moment.
      capturedAt: new Date(file.lastModified),
      category: complaint.category,
      description: complaint.description,
    }).then((result) => {
      setOutcome(result);
      if (result?.kind === 'accepted') {
        setFile(null);
        setComplaint(NO_COMPLAINT);
      }
    });
  }, [file, position, submit, complaint]);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-medium text-ink-muted">Photograph</p>
        <p className="mb-2 text-xs text-ink-subtle">
          An outdoor daylight scene with something distant in it. Blurred, dark or over-exposed
          frames are refused — each makes clean air look dirty.
        </p>
        <PhotoDropzone
          file={file}
          onChange={(next) => {
            setFile(next);
            setOutcome(null);
          }}
        />
      </div>

      <div>
        <p className="text-xs font-medium text-ink-muted">Where it was taken</p>
        <div className="mt-1.5">
          <LocationPicker position={position} onChange={setPosition} />
        </div>
      </div>

      <ComplaintFields value={complaint} onChange={setComplaint} />

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
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
    </div>
  );
}
