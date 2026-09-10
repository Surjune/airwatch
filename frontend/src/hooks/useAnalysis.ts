import { useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';

export type StationsResponse = components['schemas']['StationsResponse'];
export type StationReading = components['schemas']['StationReadingResponse'];
export type HotspotsResponse = components['schemas']['HotspotsResponse'];
export type Hotspot = components['schemas']['HotspotResponse'];
export type Attribution = components['schemas']['AttributionResponse'];
export type CorridorForecast = components['schemas']['CorridorForecastResponse'];

/** What a data hook exposes. */
export interface Resource<T> {
  readonly data: T | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
}

/**
 * Fetch a resource once on mount.
 *
 * Shared so no component holds fetch logic of its own, and so every screen
 * distinguishes the three states that matter: loading, failed, and loaded. A
 * failed request must never render as an empty map, which reads as clean air.
 */
function useResource<T>(path: string, searchParams?: Record<string, string | number>): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const key = JSON.stringify(searchParams ?? {});

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);

    get<T>(path, { signal: controller.signal, ...(searchParams ? { searchParams } : {}) })
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => {
      controller.abort();
    };
    // searchParams is compared by value through `key`; including the object
    // itself would refetch on every render since a new literal is not ===.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);

  return { data, error, isLoading };
}

/** Latest reading at every station. */
export function useStations(pollutant = 'pm25'): Resource<StationsResponse> {
  return useResource<StationsResponse>('/stations', { pollutant });
}

/** Hotspots detected over a recent window. */
export function useHotspots(windowHours = 336, pollutant = 'pm25'): Resource<HotspotsResponse> {
  return useResource<HotspotsResponse>('/hotspots', {
    pollutant,
    window_hours: windowHours,
  });
}

/** Forecast along a corridor. */
export function useCorridorForecast(
  points: string,
  horizonHours = 24,
): Resource<CorridorForecast> {
  return useResource<CorridorForecast>('/forecast/corridor', {
    points,
    horizon_hours: horizonHours,
  });
}
