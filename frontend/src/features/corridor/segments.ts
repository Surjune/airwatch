/** A gap wider than this multiple of the median sampling step is unsupported ground. */
const GAP_MULTIPLE = 1.5;

export interface ForecastSample {
  readonly distance_along_km: number;
  readonly value: number;
  readonly uncertainty: number;
  readonly upper_bound: number;
  readonly category: string;
  /** Sub-indices, which is what a band colour is read from -- never the concentration. */
  readonly aqi: number;
  readonly upper_bound_aqi: number;
}

export interface StripSegment<T extends ForecastSample = ForecastSample> {
  readonly point: T;
  /** True when the network supported nothing between this sample and the last. */
  readonly gapBefore: boolean;
}

/**
 * Mark where a forecast strip must show unknown ground.
 *
 * Samples are evenly spaced where the network supports an estimate, and missing
 * where it does not. A jump wider than the usual step therefore means a stretch
 * with no forecast at all, which has to be drawn as unknown rather than letting
 * two coloured samples look continuous across it.
 */
export function markGaps<T extends ForecastSample>(points: readonly T[]): StripSegment<T>[] {
  const steps: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const current = points[index];
    const previous = points[index - 1];
    if (current && previous) steps.push(current.distance_along_km - previous.distance_along_km);
  }
  steps.sort((a, b) => a - b);
  const median = steps[Math.floor(steps.length / 2)] ?? 1;

  return points.map((point, index) => {
    const previous = index > 0 ? points[index - 1] : undefined;
    return {
      point,
      gapBefore:
        previous !== undefined &&
        point.distance_along_km - previous.distance_along_km > median * GAP_MULTIPLE,
    };
  });
}
