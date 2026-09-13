import { describe, expect, it } from 'vitest';

import { markGaps } from './segments';

const sample = (km: number) => ({
  distance_along_km: km,
  value: 40,
  uncertainty: 10,
  upper_bound: 50,
  category: 'Satisfactory',
  aqi: 67,
  upper_bound_aqi: 83,
});

describe('markGaps', () => {
  it('draws evenly spaced samples as continuous', () => {
    const segments = markGaps([0, 1, 2, 3].map(sample));
    expect(segments.some((segment) => segment.gapBefore)).toBe(false);
  });

  it('marks the stretch the network could not support', () => {
    const segments = markGaps([0, 1, 2, 6, 7].map(sample));
    expect(segments.map((segment) => segment.gapBefore)).toEqual([
      false,
      false,
      false,
      true,
      false,
    ]);
  });

  it('never marks the first sample, which has nothing before it', () => {
    expect(markGaps([sample(4)])[0]?.gapBefore).toBe(false);
  });

  it('returns nothing for an empty forecast', () => {
    expect(markGaps([])).toEqual([]);
  });
});
