import { useCallback, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';

export type AlertBrief = components['schemas']['AlertBriefResponse'];

export interface AlertBriefState {
  readonly brief: AlertBrief | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
  readonly load: () => void;
}

/**
 * An alert's Gemini-written brief, fetched only when someone asks for it.
 *
 * Not loaded with the inbox: writing a brief takes several seconds the first
 * time, and a console listing forty alerts should not ask for forty.
 */
export function useAlertBrief(alertId: number): AlertBriefState {
  const [brief, setBrief] = useState<AlertBrief | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(() => {
    setIsLoading(true);
    setError(null);
    get<AlertBrief>(`/alerts/${String(alertId)}/brief`)
      .then(setBrief)
      .catch((cause: unknown) => {
        setError(
          cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0),
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [alertId]);

  return { brief, error, isLoading, load };
}
