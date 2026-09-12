import { useCallback, useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get, post } from '@/lib/api-client';

export type Alert = components['schemas']['AlertResponse'];
export type AlertsResponse = components['schemas']['AlertsResponse'];
export type DispatchResponse = components['schemas']['DispatchResponse'];
export type SlaBreach = components['schemas']['SlaBreachResponse'];
export type SlaBreachesResponse = components['schemas']['SlaBreachesResponse'];
export type AlertStatus = components['schemas']['AlertStatus'];

/** The alert inbox, with the actions an operator can take on it. */
export interface AlertConsole {
  readonly alerts: readonly Alert[];
  readonly breaches: readonly SlaBreach[];
  readonly error: ApiError | null;
  readonly isLoading: boolean;
  /** True while a write is in flight, so a button cannot be double-submitted. */
  readonly isBusy: boolean;
  readonly acknowledge: (alertId: number) => Promise<void>;
  readonly resolve: (alertId: number, note: string) => Promise<void>;
  readonly dispatch: () => Promise<DispatchResponse | null>;
  readonly refresh: () => void;
}

/**
 * Drive the authority console.
 *
 * Reads the inbox and the overdue list together, because an operator needs both
 * to decide what to open first: the inbox says what is worst, the breach list
 * says what has been ignored, and those are rarely the same alert.
 *
 * Every write refetches rather than patching local state. The server decides
 * whether a transition was legal -- resolving without a note is refused there,
 * not here -- so the response to a write is the server's view, and guessing at
 * it locally would let the console display a state the database never reached.
 */
export function useAlerts(windowHours = 720): AlertConsole {
  const [alerts, setAlerts] = useState<readonly Alert[]>([]);
  const [breaches, setBreaches] = useState<readonly SlaBreach[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);

  const refresh = useCallback(() => {
    setReloadCount((count) => count + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);

    Promise.all([
      get<AlertsResponse>('/alerts', { signal: controller.signal }),
      get<SlaBreachesResponse>('/alerts/sla-breaches', { signal: controller.signal }),
    ])
      .then(([inbox, overdue]) => {
        setAlerts(inbox.alerts);
        setBreaches(overdue.breaches);
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
  }, [reloadCount]);

  const runWrite = useCallback(
    async (work: () => Promise<void>): Promise<void> => {
      setIsBusy(true);
      try {
        await work();
        setError(null);
        refresh();
      } catch (cause: unknown) {
        setError(toApiError(cause));
      } finally {
        setIsBusy(false);
      }
    },
    [refresh],
  );

  const acknowledge = useCallback(
    (alertId: number) =>
      runWrite(async () => {
        await post<Alert>(`/alerts/${String(alertId)}/acknowledge`, undefined);
      }),
    [runWrite],
  );

  const resolve = useCallback(
    (alertId: number, note: string) =>
      runWrite(async () => {
        await post<Alert>(`/alerts/${String(alertId)}/resolve`, { note });
      }),
    [runWrite],
  );

  const dispatch = useCallback(async (): Promise<DispatchResponse | null> => {
    setIsBusy(true);
    try {
      const outcome = await post<DispatchResponse>('/alerts/dispatch', undefined, {
        searchParams: { window_hours: windowHours },
      });
      setError(null);
      refresh();
      return outcome;
    } catch (cause: unknown) {
      setError(toApiError(cause));
      return null;
    } finally {
      setIsBusy(false);
    }
  }, [refresh, windowHours]);

  return { alerts, breaches, error, isLoading, isBusy, acknowledge, resolve, dispatch, refresh };
}

function toApiError(cause: unknown): ApiError {
  return cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0);
}
