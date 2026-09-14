import type { components } from '@/lib/api-types';

export type RegionalModel = components['schemas']['RegionalModelResponse'];
export type ModelComparison = components['schemas']['ModelComparisonResponse'];

/**
 * How far the model can be trusted in this city, in one sentence.
 *
 * The comparison is what makes a modelled number readable: the same 20 µg/m³
 * means something different where the model is known to read half of what the
 * monitors do. With no monitors to check against, that is said instead.
 */
export function describeBias(comparison: ModelComparison): string {
  const { pairs, pairs_needed: needed, stations, median_ratio: ratio } = comparison;
  if (pairs === 0 || ratio === null) {
    return 'No monitor here reported in the last fortnight to check the model against, so treat it as a rough regional guide.';
  }
  const monitors = `${String(stations)} monitor${stations === 1 ? '' : 's'}`;
  if (!comparison.is_established) {
    return `Only ${String(pairs)} monitor hours to compare so far (${String(needed)} needed), too few to judge the model here.`;
  }
  const direction =
    ratio < 1
      ? `reads about ${ratio.toFixed(1)}× what the monitors measure — low`
      : `reads about ${ratio.toFixed(1)}× what the monitors measure — high`;
  return `Over the last fortnight the model ${direction} (median of ${String(pairs)} hourly pairs from ${monitors}).`;
}
