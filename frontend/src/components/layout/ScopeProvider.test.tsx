import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CitiesResponse } from '@/hooks/useAnalysis';
import { useScope } from '@/lib/scope';

import { ScopeProvider } from './ScopeProvider';

const listed = vi.hoisted(() => ({ cities: null as CitiesResponse | null }));

vi.mock('@/hooks/useAnalysis', () => ({
  useCities: () => ({ data: listed.cities, error: null, isLoading: false }),
}));

const CITIES: CitiesResponse = {
  cities: [
    {
      city: 'delhi',
      label: 'Delhi-NCR',
      centre: { longitude: 77.209, latitude: 28.6139 },
      radius_m: 40_000,
      default_pollutant: 'pm25',
    },
    {
      city: 'coimbatore',
      label: 'Coimbatore',
      centre: { longitude: 76.9558, latitude: 11.0168 },
      radius_m: 40_000,
      default_pollutant: 'pm10',
    },
  ],
};

function Shown() {
  const { city, pollutant, setCity } = useScope();
  return (
    <>
      <p>
        {city} {pollutant}
      </p>
      <button
        type="button"
        onClick={() => {
          setCity('coimbatore');
        }}
      >
        Coimbatore
      </button>
    </>
  );
}

function renderScope() {
  render(
    <ScopeProvider>
      <Shown />
    </ScopeProvider>,
  );
}

describe('ScopeProvider', () => {
  beforeEach(() => {
    listed.cities = CITIES;
    window.localStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('opens a first visit on Delhi and PM2.5', () => {
    renderScope();

    expect(screen.getByText('delhi pm25')).toBeInTheDocument();
  });

  it('opens on Delhi even where the old Coimbatore default was remembered', () => {
    window.localStorage.setItem(
      'airwatch.scope',
      JSON.stringify({ city: 'coimbatore', pollutant: 'pm10' }),
    );

    renderScope();

    expect(screen.getByText('delhi pm25')).toBeInTheDocument();
  });

  it('keeps a city and pollutant picked since', () => {
    window.localStorage.setItem(
      'airwatch.scope.v2',
      JSON.stringify({ city: 'coimbatore', pollutant: 'pm25' }),
    );

    renderScope();

    expect(screen.getByText('coimbatore pm25')).toBeInTheDocument();
  });

  it('follows a link that names a city and pollutant', () => {
    window.history.replaceState(null, '', '/?city=coimbatore&pollutant=pm25');

    renderScope();

    expect(screen.getByText('coimbatore pm25')).toBeInTheDocument();
  });

  it("opens a link naming only a city on that city's own pollutant", () => {
    // Coimbatore's monitor reports PM10; opening it on PM2.5 shows an empty page.
    window.history.replaceState(null, '', '/?city=coimbatore');

    renderScope();

    expect(screen.getByText('coimbatore pm10')).toBeInTheDocument();
  });

  it("switches to a new city's own pollutant, even after one was picked", async () => {
    window.localStorage.setItem(
      'airwatch.scope.v2',
      JSON.stringify({ city: 'delhi', pollutant: 'pm25' }),
    );
    renderScope();

    fireEvent.click(screen.getByRole('button', { name: 'Coimbatore' }));

    expect(await screen.findByText('coimbatore pm10')).toBeInTheDocument();
  });

  it('shows a placeholder pollutant until the city list arrives', () => {
    listed.cities = null;
    window.history.replaceState(null, '', '/?city=coimbatore');

    renderScope();

    expect(screen.getByText('coimbatore pm25')).toBeInTheDocument();
  });
});
