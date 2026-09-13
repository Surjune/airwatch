import { useCallback, useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get, post } from '@/lib/api-client';
import { deviceId } from '@/lib/device';

export type SensorReadings = components['schemas']['SensorReadingsResponse'];
export type SensorReading = components['schemas']['SensorReadingSummary'];
export type SensorReadingAccepted = components['schemas']['SensorReadingAccepted'];
export type SensorReadingRequest = components['schemas']['SensorReadingRequest'];
export type Colocation = components['schemas']['ColocationResponse'];

/** Fields the submitter supplies; the device identifier is added here. */
export type SensorReadingInput = Omit<SensorReadingRequest, 'device_id'>;

export interface CitizenSensorTier {
  readonly data: SensorReadings | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
  readonly isSubmitting: boolean;
  readonly submit: (input: SensorReadingInput) => Promise<SensorReadingAccepted | null>;
}

/**
 * Readings residents have submitted from their own sensors, and a way to add one.
 *
 * A refused reading -- a value no ambient air reaches, a gas pollutant -- comes
 * back as a typed validation error whose message says what to fix, so it is
 * surfaced as the error rather than swallowed.
 */
export function useCitizenSensors(
  pollutant: string,
  city: string,
  windowHours = 24,
): CitizenSensorTier {
  const [data, setData] = useState<SensorReadings | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    get<SensorReadings>('/citizen/sensor-readings', {
      signal: controller.signal,
      searchParams: { pollutant, city, window_hours: windowHours },
    })
      .then((body) => {
        setData(body);
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
  }, [pollutant, city, windowHours, reloadCount]);

  const submit = useCallback(
    async (input: SensorReadingInput): Promise<SensorReadingAccepted | null> => {
      setIsSubmitting(true);
      try {
        const accepted = await post<SensorReadingAccepted>('/citizen/sensor-readings', {
          ...input,
          device_id: deviceId(),
        });
        setError(null);
        setReloadCount((count) => count + 1);
        return accepted;
      } catch (cause: unknown) {
        setError(toApiError(cause));
        return null;
      } finally {
        setIsSubmitting(false);
      }
    },
    [],
  );

  return { data, error, isLoading, isSubmitting, submit };
}

function toApiError(cause: unknown): ApiError {
  return cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0);
}
