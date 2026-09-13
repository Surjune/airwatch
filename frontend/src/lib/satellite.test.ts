import { describe, expect, it } from 'vitest';

import { formatColumn } from './satellite';

describe('formatColumn', () => {
  it('shows a column density in micromoles per square metre', () => {
    // 2.07e-5 mol/m² is 20.7 µmol/m², a typical tropospheric NO2 column.
    expect(formatColumn('no2', 2.07e-5)).toBe('20.7 µmol/m²');
  });

  it('shows the aerosol index as the dimensionless number it is', () => {
    expect(formatColumn('aerosol_index', -0.4321)).toBe('-0.43');
  });
});
