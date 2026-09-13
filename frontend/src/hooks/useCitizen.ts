import { useCallback, useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get, request } from '@/lib/api-client';
import type { ComplaintCategory } from '@/lib/complaints';
import { deviceId } from '@/lib/device';

export type Submission = components['schemas']['SubmissionResponse'];
export type Rejection = components['schemas']['RejectionResponse'];
export type CalibrationStatus = components['schemas']['CalibrationStatusResponse'];
export type CitizenReportsResponse = components['schemas']['CitizenReportsResponse'];
export type CitizenReport = components['schemas']['CitizenReportSummary'];

/** What a submission attempt produced. */
export type SubmissionOutcome =
  | { readonly kind: 'accepted'; readonly report: Submission }
  | { readonly kind: 'rejected'; readonly rejection: Rejection };

/** Fields the submitter supplies alongside the photograph. */
export interface SubmissionInput {
  readonly file: File;
  readonly longitude: number;
  readonly latitude: number;
  readonly capturedAt: Date;
  /** What the resident saw, for their complaint report. */
  readonly category?: ComplaintCategory | null;
  readonly description?: string;
}

export interface CitizenTier {
  readonly reports: readonly CitizenReport[];
  readonly calibration: CalibrationStatus | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
  readonly isSubmitting: boolean;
  readonly submit: (input: SubmissionInput) => Promise<SubmissionOutcome | null>;
  readonly refresh: () => void;
}

/**
 * Drive the citizen submission screen.
 *
 * A rejected photograph is returned as an outcome, not thrown. Rejection is the
 * expected path for a blurred or dark photo, and the submitter needs the reason
 * in order to retake it -- so treating it as an error would lose exactly the
 * information that makes the refusal useful.
 */
export function useCitizen(windowHours = 24): CitizenTier {
  const [reports, setReports] = useState<readonly CitizenReport[]>([]);
  const [calibration, setCalibration] = useState<CalibrationStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);

  const refresh = useCallback(() => {
    setReloadCount((count) => count + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);

    get<CitizenReportsResponse>('/citizen/reports', {
      signal: controller.signal,
      searchParams: { window_hours: windowHours },
    })
      .then((body) => {
        setReports(body.reports);
        setCalibration(body.calibration);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(toApiError(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [reloadCount, windowHours]);

  const submit = useCallback(
    async (input: SubmissionInput): Promise<SubmissionOutcome | null> => {
      setIsSubmitting(true);
      try {
        const form = new FormData();
        form.append('photo', input.file);
        form.append('longitude', String(input.longitude));
        form.append('latitude', String(input.latitude));
        form.append('captured_at', input.capturedAt.toISOString());
        form.append('device_id', deviceId());
        if (input.category) form.append('category', input.category);
        if (input.description?.trim()) form.append('description', input.description.trim());

        const report = await request<Submission>('/citizen/reports', {
          method: 'POST',
          formData: form,
        });
        setError(null);
        refresh();
        return { kind: 'accepted', report };
      } catch (cause: unknown) {
        const failure = toApiError(cause);
        const rejection = asRejection(failure);
        if (rejection) {
          // Expected, not exceptional: the submitter gets told why and can retake.
          return { kind: 'rejected', rejection };
        }
        setError(failure);
        return null;
      } finally {
        setIsSubmitting(false);
      }
    },
    [refresh],
  );

  return { reports, calibration, error, isLoading, isSubmitting, submit, refresh };
}

/**
 * A refused photograph arrives as a 422 whose body is the rejection itself
 * rather than the standard error envelope, so it is recognised by shape.
 *
 * Checked structurally rather than by status code alone: a 422 from ordinary
 * request validation is a different thing and should surface as an error, not
 * as advice about how to retake the photo.
 */
function asRejection(failure: ApiError): Rejection | null {
  const payload: unknown = failure.body;
  if (typeof payload !== 'object' || payload === null) return null;

  const candidate = payload as { reason?: unknown; detail?: unknown };
  if (typeof candidate.reason === 'string' && typeof candidate.detail === 'string') {
    return { accepted: false, reason: candidate.reason, detail: candidate.detail };
  }
  return null;
}

function toApiError(cause: unknown): ApiError {
  return cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0);
}
