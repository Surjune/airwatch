import { describe, expect, it } from 'vitest';

import { describeBias, type ModelComparison } from './regional-model';

const BASE: ModelComparison = {
  pairs: 0,
  pairs_needed: 24,
  stations: 0,
  median_ratio: null,
  median_difference: null,
  is_established: false,
};

describe('describeBias', () => {
  it('says there is nothing to check the model against', () => {
    expect(describeBias(BASE)).toMatch(/No monitor here reported/);
  });

  it('refuses to judge the model on a short record', () => {
    const text = describeBias({ ...BASE, pairs: 6, stations: 1, median_ratio: 0.4 });

    expect(text).toMatch(/Only 6 monitor hours/);
    expect(text).toMatch(/24 needed/);
  });

  it('states a low-reading model as low, with its sample', () => {
    const text = describeBias({
      ...BASE,
      pairs: 312,
      stations: 1,
      median_ratio: 0.46,
      median_difference: -30,
      is_established: true,
    });

    expect(text).toMatch(/0\.5× what the monitors measure — low/);
    expect(text).toMatch(/312 hourly pairs from 1 monitor\)/);
  });

  it('states a high-reading model as high', () => {
    expect(
      describeBias({ ...BASE, pairs: 40, stations: 3, median_ratio: 1.8, is_established: true }),
    ).toMatch(/1\.8× .* — high .*3 monitors/);
  });
});
