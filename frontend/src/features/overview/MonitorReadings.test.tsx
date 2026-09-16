import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Resource, StationReading, StationsResponse } from '@/hooks/useAnalysis';

import { MonitorReadings } from './MonitorReadings';

function reading(overrides: Partial<StationReading>): StationReading {
  return {
    station_id: 1,
    name: 'Anand Vihar',
    position: { longitude: 77.31, latitude: 28.65 },
    h3_cell: '883da1336bfffff',
    observed_at: new Date().toISOString(),
    value: 62,
    unit: 'ug/m3',
    aqi: 107,
    category: 'Moderate',
    daily_mean: 48,
    daily_mean_hours: 24,
    who_multiple: 3.2,
    ...overrides,
  };
}

function loaded(
  readings: StationReading[],
  guideline: number | null = 15,
): Resource<StationsResponse> {
  return {
    data: {
      pollutant: 'pm25',
      station_count: readings.length,
      who_guideline_24h: guideline,
      daily_mean_min_hours: 18,
      readings,
    },
    error: null,
    isLoading: false,
  };
}

describe('MonitorReadings', () => {
  it("sets each monitor's day against WHO's 24-hour guideline", () => {
    render(<MonitorReadings stations={loaded([reading({})])} pollutantLabel="PM2.5" />);

    expect(screen.getByText('24 h avg 3.2× WHO')).toBeInTheDocument();
    expect(
      screen.getByText(
        "Average over the last 24 hours: 48 µg/m³, 3.2× WHO's 24-hour guideline of 15 µg/m³.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/guideline for a 24-hour average of PM2.5 is 15/)).toBeInTheDocument();
  });

  it('compares nothing for a monitor without a full day of readings', () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ daily_mean: null, daily_mean_hours: 6, who_multiple: null })])}
        pollutantLabel="PM2.5"
      />,
    );

    expect(screen.queryByText(/24 h avg/)).not.toBeInTheDocument();
    expect(screen.getByText(/once it has readings for\s+18 of them/)).toBeInTheDocument();
  });

  it('says so when a day stayed within the guideline', () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ daily_mean: 12, who_multiple: 0.8 })])}
        pollutantLabel="PM2.5"
      />,
    );

    expect(screen.getByText('24 h avg within WHO')).toBeInTheDocument();
  });

  it('shows no comparison for a pollutant WHO sets no daily level for', () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ who_multiple: null })], null)}
        pollutantLabel="O3"
      />,
    );

    expect(screen.queryByText(/WHO/)).not.toBeInTheDocument();
  });
});
