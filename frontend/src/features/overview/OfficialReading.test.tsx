import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Resource } from '@/hooks/useAnalysis';
import type { LiveIndex, LiveStation, OfficialAqi, OfficialStation } from '@/hooks/useSources';
import { BACKUP_NOTE } from '@/lib/origin';

import { OfficialReading } from './OfficialReading';

const HOUR_MS = 3_600_000;

function station(overrides: Partial<OfficialStation>): OfficialStation {
  const reportedAt = new Date(Date.now() - HOUR_MS).toISOString();
  return {
    station_name: 'SIDCO Kurichi, Coimbatore - TNPCB',
    position: { longitude: 76.979, latitude: 10.9425 },
    reported_at: reportedAt,
    oldest_reported_at: reportedAt,
    sub_indices: { co: 48, o3: 19 },
    aqi: null,
    category: null,
    dominant_pollutant: null,
    ...overrides,
  };
}

function loaded(stations: OfficialStation[]): Resource<OfficialAqi> {
  return {
    data: {
      city: 'coimbatore',
      source: 'CPCB real-time AQI, published on data.gov.in',
      station_count: stations.length,
      stations,
    },
    error: null,
    isLoading: false,
  };
}

function liveStation(overrides: Partial<LiveStation>): LiveStation {
  const observedAt = new Date(Date.now() - HOUR_MS).toISOString();
  return {
    station_id: 7,
    name: 'Anand Vihar, New Delhi - DPCC',
    position: { longitude: 77.3152, latitude: 28.6468 },
    observed_at: observedAt,
    oldest_observed_at: observedAt,
    aqi: 231,
    category: 'Poor',
    dominant_pollutant: 'pm25',
    sub_indices: { pm25: 231, pm10: 134 },
    origins: ['waqi'],
    ...overrides,
  };
}

function live(stations: LiveStation[]): Resource<LiveIndex> {
  return {
    data: {
      city: 'delhi',
      basis: 'Worked out by AirWatch, not published by CPCB.',
      station_count: stations.length,
      stations,
    },
    error: null,
    isLoading: false,
  };
}

const NO_LIVE = live([]);

describe('OfficialReading', () => {
  it('says a silent station has stopped reporting, rather than blaming the last few hours', () => {
    const threeDaysAgo = new Date(Date.now() - 72 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([
          station({ reported_at: threeDaysAgo, oldest_reported_at: threeDaysAgo }),
        ])}
        live={NO_LIVE}
        cityLabel="Coimbatore"
      />,
    );

    expect(screen.getByText(/has not reported to CPCB since/)).toBeInTheDocument();
    expect(screen.queryByText(/Too few pollutants/)).not.toBeInTheDocument();
  });

  it('explains a missing index when a reporting station sent too few pollutants', () => {
    render(
      <OfficialReading official={loaded([station({})])} live={NO_LIVE} cityLabel="Coimbatore" />,
    );

    expect(screen.getByText(/Too few pollutants reported in the last 3 hours/)).toBeInTheDocument();
    expect(screen.queryByText(/has not reported to CPCB since/)).not.toBeInTheDocument();
  });

  it('leads with the monitors’ live index while CPCB’s figure is out of date', () => {
    const lastWeek = new Date(Date.now() - 168 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([station({ reported_at: lastWeek, aqi: 154, category: 'Moderate' })])}
        live={live([liveStation({})])}
        cityLabel="Delhi-NCR"
      />,
    );

    expect(screen.getByText('What the monitors show for Delhi-NCR now')).toBeInTheDocument();
    expect(screen.getByText('Anand Vihar, New Delhi - DPCC')).toBeInTheDocument();
    expect(screen.getByText(/This figure is AirWatch’s own/)).toBeInTheDocument();
    expect(screen.getByText(/CPCB’s last official index/)).toBeInTheDocument();
    expect(screen.getByText(BACKUP_NOTE)).toBeInTheDocument();
  });

  it('keeps CPCB’s own figure while it is current', () => {
    render(
      <OfficialReading
        official={loaded([station({ aqi: 154, category: 'Moderate' })])}
        live={live([liveStation({})])}
        cityLabel="Delhi-NCR"
      />,
    );

    expect(screen.getByText('What CPCB reports for Delhi-NCR')).toBeInTheDocument();
    expect(screen.queryByText(/AirWatch’s own/)).not.toBeInTheDocument();
  });

  it('keeps CPCB’s last report, marked as old, when no monitor is current either', () => {
    const lastWeek = new Date(Date.now() - 168 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([station({ reported_at: lastWeek, oldest_reported_at: lastWeek })])}
        live={live([liveStation({ observed_at: lastWeek, oldest_observed_at: lastWeek })])}
        cityLabel="Kanpur"
      />,
    );

    expect(screen.getByText('What CPCB reports for Kanpur')).toBeInTheDocument();
    expect(screen.getByText(/has not reported to CPCB since/)).toBeInTheDocument();
  });
});
