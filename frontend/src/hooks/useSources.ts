import { useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';
import type { RegionalModel } from '@/lib/regional-model';

import type { Resource } from './useAnalysis';

export type OfficialAqi = components['schemas']['OfficialAqiResponse'];
export type OfficialStation = components['schemas']['OfficialStationResponse'];
export type LowCostSensors = components['schemas']['LowCostSensorsResponse'];
export type Satellite = components['schemas']['SatelliteResponse'];
export type SatelliteProduct = components['schemas']['SatelliteProduct'];

/**
 * Fetch a resource whenever its parameters change.
 *
 * Kept separate from the analysis hooks because these sources are optional per
 * deployment: a city with no data.gov.in key or no Earth Engine account still
 * works, and each panel reports its own absence.
 */
function useQuery<T>(path: string, searchParams: Record<string, string | number>): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const key = JSON.stringify(searchParams);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    get<T>(path, { signal: controller.signal, searchParams })
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
    // searchParams is compared by value through `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);

  return { data, error, isLoading };
}

/** CPCB's latest published AQI for each station in a city. */
export function useOfficialAqi(city: string): Resource<OfficialAqi> {
  return useQuery<OfficialAqi>('/official-aqi', { city });
}

/** Uncalibrated low-cost sensor readings in a city. */
export function useLowCostSensors(pollutant: string, city: string): Resource<LowCostSensors> {
  return useQuery<LowCostSensors>('/sensors', { pollutant, city });
}

/** The CAMS regional model over a city: hours around now, peaks ahead, and its bias. */
export function useRegionalModel(city: string, pollutant: string): Resource<RegionalModel> {
  return useQuery<RegionalModel>('/regional-model', { city, pollutant });
}

/** A Sentinel-5P product over a city: its daily series and latest cell values. */
export function useSatellite(
  city: string,
  product: SatelliteProduct,
  days = 14,
): Resource<Satellite> {
  return useQuery<Satellite>('/satellite', { city, product, days });
}
