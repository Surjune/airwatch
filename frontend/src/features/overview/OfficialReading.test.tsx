import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Resource } from '@/hooks/useAnalysis';
import type {
  Bulletin,
  CityBulletin,
  LiveIndex,
  LiveStation,
  OfficialAqi,
  OfficialStation,
} from '@/hooks/useSources';
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
    relay: 'data.gov.in',
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

function dailyLine(overrides: Partial<CityBulletin>): CityBulletin {
  return {
    day: '2026-10-08',
    averaged_until: new Date(Date.now() - 5 * HOUR_MS).toISOString(),
    aqi: 44,
    category: 'Good',
    prominent_pollutants: ['pm25', 'no2'],
    stations_reporting: 2,
    stations_total: 4,
    source_url: 'https://cpcb.gov.in/upload/Downloads/AQI_Bulletin_20261008.pdf',
    ...overrides,
  };
}

function bulletin(line: CityBulletin | null): Resource<Bulletin> {
  return {
    data: { city: 'kanpur', source: 'CPCB daily AQI bulletin', bulletin: line },
    error: null,
    isLoading: false,
  };
}

const NO_BULLETIN = bulletin(null);

describe('OfficialReading', () => {
  it('says a silent station has stopped reporting, rather than blaming the last few hours', () => {
    const threeDaysAgo = new Date(Date.now() - 72 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([
          station({ reported_at: threeDaysAgo, oldest_reported_at: threeDaysAgo }),
        ])}
        live={NO_LIVE}
        bulletin={NO_BULLETIN}
        cityLabel="Coimbatore"
      />,
    );

    expect(screen.getByText(/carried nothing new for this station since/)).toBeInTheDocument();
    expect(screen.queryByText(/Too few pollutants/)).not.toBeInTheDocument();
  });

  it('explains a missing index when a reporting station sent too few pollutants', () => {
    render(
      <OfficialReading
        official={loaded([station({})])}
        live={NO_LIVE}
        bulletin={NO_BULLETIN}
        cityLabel="Coimbatore"
      />,
    );

    expect(screen.getByText(/Too few pollutants reported in the last 3 hours/)).toBeInTheDocument();
    expect(
      screen.queryByText(/carried nothing new for this station since/),
    ).not.toBeInTheDocument();
  });

  it('leads with the monitors’ live index while CPCB’s figure is out of date', () => {
    const lastWeek = new Date(Date.now() - 168 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([station({ reported_at: lastWeek, aqi: 154, category: 'Moderate' })])}
        live={live([liveStation({})])}
        bulletin={NO_BULLETIN}
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
        bulletin={NO_BULLETIN}
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
        bulletin={NO_BULLETIN}
        cityLabel="Kanpur"
      />,
    );

    expect(screen.getByText('What CPCB reports for Kanpur')).toBeInTheDocument();
    expect(screen.getByText(/carried nothing new for this station since/)).toBeInTheDocument();
  });

  it('leads with CPCB’s daily bulletin when no hourly figure is current', () => {
    const lastWeek = new Date(Date.now() - 168 * HOUR_MS).toISOString();
    const yesterday = new Date(Date.now() - 24 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([station({ reported_at: lastWeek, aqi: 120, category: 'Moderate' })])}
        live={live([liveStation({ observed_at: yesterday, oldest_observed_at: yesterday })])}
        bulletin={bulletin(dailyLine({}))}
        cityLabel="Kanpur"
      />,
    );

    expect(screen.getByText('CPCB daily bulletin · 24-hour average')).toBeInTheDocument();
    expect(screen.getByText(/2 of 4 stations/)).toBeInTheDocument();
    expect(screen.getByText(/so this is the newest official figure/)).toBeInTheDocument();
    expect(screen.getByText(/CPCB’s last hourly report/)).toBeInTheDocument();
  });

  it('keeps CPCB’s last report when the bulletin is out of date too', () => {
    const lastWeek = new Date(Date.now() - 168 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([station({ reported_at: lastWeek, oldest_reported_at: lastWeek })])}
        live={NO_LIVE}
        bulletin={bulletin(dailyLine({ averaged_until: lastWeek }))}
        cityLabel="Kanpur"
      />,
    );

    expect(screen.getByText('What CPCB reports for Kanpur')).toBeInTheDocument();
    expect(screen.queryByText('CPCB daily bulletin · 24-hour average')).not.toBeInTheDocument();
    expect(screen.getByText(/carried nothing new for this station since/)).toBeInTheDocument();
  });

  it('names TNPCB as the relay, and keeps the bulletin in view under a current figure', () => {
    render(
      <OfficialReading
        official={loaded([station({ aqi: 51, category: 'Satisfactory', relay: 'tnpcb' })])}
        live={NO_LIVE}
        bulletin={bulletin(dailyLine({}))}
        cityLabel="Coimbatore"
      />,
    );

    expect(screen.getByText('Official CPCB index · via TNPCB')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'CPCB’s daily bulletin' })).toHaveAttribute(
      'href',
      'https://cpcb.gov.in/upload/Downloads/AQI_Bulletin_20261008.pdf',
    );
  });
});
