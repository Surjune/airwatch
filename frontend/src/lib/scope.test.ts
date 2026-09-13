import { describe, expect, it } from 'vitest';

import { readLinked } from './scope';

describe('readLinked', () => {
  it('reads a city and pollutant from a shared link', () => {
    expect(readLinked('?city=delhi&pollutant=pm25')).toEqual({ city: 'delhi', pollutant: 'pm25' });
  });

  it('ignores a city the API does not serve', () => {
    expect(readLinked('?city=atlantis')).toEqual({});
  });

  it('ignores a pollutant the dashboard cannot switch to', () => {
    expect(readLinked('?city=kanpur&pollutant=so2')).toEqual({ city: 'kanpur' });
  });

  it('returns nothing for a plain address', () => {
    expect(readLinked('')).toEqual({});
  });
});
