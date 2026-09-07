import { useEffect, useState } from 'react';

import { ApiError, get } from '@/lib/api-client';

/** Configuration state of one upstream data source, as reported by the API. */
export interface UpstreamStatus {
  readonly provider: string;
  readonly configured: boolean;
  readonly required_env_var: string;
}

/** The API's health and configuration summary. */
export interface HealthReport {
  readonly status: 'ok';
  readonly environment: string;
  readonly version: string;
  readonly h3_resolution: number;
  readonly upstreams: readonly UpstreamStatus[];
}

/** What {@link useHealth} exposes to a component. */
export interface HealthState {
  readonly report: HealthReport | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
}

/**
 * Fetch the API health report once on mount.
 *
 * Kept as a hook so no component contains fetch logic of its own.
 */
export function useHealth(): HealthState {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    get<HealthReport>('/health', { signal: controller.signal })
      .then((result) => {
        setReport(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        // An aborted request is the component unmounting, not a failure.
        if (controller.signal.aborted) {
          return;
        }
        setError(
          cause instanceof ApiError
            ? cause
            : new ApiError('unknown_error', 'The health check failed.', 0),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, []);

  return { report, error, isLoading };
}
