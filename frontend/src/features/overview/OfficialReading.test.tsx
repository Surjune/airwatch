import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Resource } from '@/hooks/useAnalysis';
import type { OfficialAqi, OfficialStation } from '@/hooks/useSources';

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

describe('OfficialReading', () => {
  it('says a silent station has stopped reporting, rather than blaming the last few hours', () => {
    const threeDaysAgo = new Date(Date.now() - 72 * HOUR_MS).toISOString();
    render(
      <OfficialReading
        official={loaded([
          station({ reported_at: threeDaysAgo, oldest_reported_at: threeDaysAgo }),
        ])}
        cityLabel="Coimbatore"
      />,
    );

    expect(screen.getByText(/has not reported to CPCB since/)).toBeInTheDocument();
    expect(screen.queryByText(/Too few pollutants/)).not.toBeInTheDocument();
  });

  it('explains a missing index when a reporting station sent too few pollutants', () => {
    render(<OfficialReading official={loaded([station({})])} cityLabel="Coimbatore" />);

    expect(screen.getByText(/Too few pollutants reported in the last 3 hours/)).toBeInTheDocument();
    expect(screen.queryByText(/has not reported to CPCB since/)).not.toBeInTheDocument();
  });
});
