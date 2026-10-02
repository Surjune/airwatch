import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Resource, StationReading, StationsResponse } from '@/hooks/useAnalysis';
import type { RegionalModel } from '@/lib/regional-model';

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
    origin: 'openaq',
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

const NO_MODEL: Resource<RegionalModel> = { data: null, error: null, isLoading: false };

const MODEL: Resource<RegionalModel> = {
  data: {
    city: 'coimbatore',
    pollutant: 'pm10',
    unit: 'µg/m³',
    source: 'CAMS global atmospheric composition forecast (Copernicus), via Open-Meteo',
    grid_point: { longitude: 77, latitude: 11 },
    latest: { observed_at: new Date().toISOString(), value: 9.7, is_forecast: false },
    next_day_peak: 18.8,
    outlook_peak: 18.8,
    hours: [],
    comparison: {
      pairs: 185,
      pairs_needed: 24,
      stations: 1,
      median_ratio: 0.69,
      median_difference: -7.1,
      is_established: true,
    },
    notice: 'Modelled, not measured.',
  },
  error: null,
  isLoading: false,
};

const THREE_DAYS_AGO = new Date(Date.now() - 3 * 24 * 3_600_000).toISOString();

describe('MonitorReadings', () => {
  it("sets each monitor's day against WHO's 24-hour guideline", () => {
    render(
      <MonitorReadings stations={loaded([reading({})])} model={NO_MODEL} pollutantLabel="PM2.5" />,
    );

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
        model={NO_MODEL}
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
        model={NO_MODEL}
        pollutantLabel="PM2.5"
      />,
    );

    expect(screen.getByText('24 h avg within WHO')).toBeInTheDocument();
  });

  it('shows no comparison for a pollutant WHO sets no daily level for', () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ who_multiple: null })], null)}
        model={NO_MODEL}
        pollutantLabel="O3"
      />,
    );

    expect(screen.queryByText(/WHO/)).not.toBeInTheDocument();
  });

  it("offers the model's current value while every monitor is silent", () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ observed_at: THREE_DAYS_AGO })])}
        model={MODEL}
        pollutantLabel="PM10"
      />,
    );

    expect(screen.getByText('Meanwhile · CAMS regional model')).toBeInTheDocument();
    expect(screen.getByText('10 µg/m³')).toBeInTheDocument();
    expect(screen.getByText(/reads about 0\.7× what the monitors measure/)).toBeInTheDocument();
    // The monitor's last reading is still listed, with its age.
    expect(screen.getByText(/3 days ago/)).toBeInTheDocument();
  });

  it('keeps the model out of the way while a monitor is reporting', () => {
    render(
      <MonitorReadings stations={loaded([reading({})])} model={MODEL} pollutantLabel="PM10" />,
    );

    expect(screen.queryByText('Meanwhile · CAMS regional model')).not.toBeInTheDocument();
  });

  it('still offers the model for a city with no monitor at all', () => {
    render(<MonitorReadings stations={loaded([])} model={MODEL} pollutantLabel="PM10" />);

    expect(screen.getByText('Meanwhile · CAMS regional model')).toBeInTheDocument();
    expect(screen.getByText('No monitor has reported PM10 recently')).toBeInTheDocument();
  });

  it('marks a backup reading and credits where it came from', () => {
    render(
      <MonitorReadings
        stations={loaded([reading({ origin: 'waqi' })])}
        model={NO_MODEL}
        pollutantLabel="PM2.5"
      />,
    );

    expect(screen.getByText(/via aqicn\.org/, { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText(/World Air Quality Index Project/)).toBeInTheDocument();
    expect(screen.getByText('Reference monitors · OpenAQ · aqicn.org')).toBeInTheDocument();
  });

  it('says nothing about the backup feed while OpenAQ is reporting', () => {
    render(
      <MonitorReadings stations={loaded([reading({})])} model={NO_MODEL} pollutantLabel="PM2.5" />,
    );

    expect(screen.queryByText(/aqicn/)).not.toBeInTheDocument();
  });
});
