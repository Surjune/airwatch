import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ScopeContext, type Scope } from '@/lib/scope';

import { CityPicker } from './CityPicker';

function scope(setCity = vi.fn()): Scope {
  return {
    city: 'coimbatore',
    pollutant: 'pm10',
    current: null,
    cities: [
      {
        city: 'coimbatore',
        label: 'Coimbatore',
        centre: { longitude: 76.9558, latitude: 11.0168 },
        radius_m: 40_000,
        default_pollutant: 'pm10',
      },
      {
        city: 'delhi',
        label: 'Delhi-NCR',
        centre: { longitude: 77.209, latitude: 28.6139 },
        radius_m: 40_000,
        default_pollutant: 'pm25',
      },
    ],
    setCity,
    setPollutant: vi.fn(),
  };
}

describe('CityPicker', () => {
  it('offers every city and switches when one is chosen', () => {
    const setCity = vi.fn();
    render(
      <ScopeContext.Provider value={scope(setCity)}>
        <CityPicker />
      </ScopeContext.Provider>,
    );

    const picker = screen.getByLabelText('City');
    expect(picker).toHaveValue('coimbatore');
    expect(screen.getByRole('option', { name: 'Delhi-NCR' })).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: 'delhi' } });
    expect(setCity).toHaveBeenCalledWith('delhi');
  });
});
