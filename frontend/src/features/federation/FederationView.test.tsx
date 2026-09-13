import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { components } from '@/lib/api-types';

import { FederationView } from './FederationView';

type FederationStatus = components['schemas']['FederationStatusResponse'];

function status(overrides: Partial<FederationStatus> = {}): FederationStatus {
  return {
    reporting_window_hours: 6,
    summary: 'No federated model is established as helping or harming either node.',
    coverage: [
      {
        node: 'delhi',
        stations: 64,
        reporting_stations: 58,
        silent_stations: 6,
        readings: 15103,
        latest_reading_at: '2026-09-13T02:00:00Z',
        is_unmonitored: false,
        is_stale: false,
      },
      {
        node: 'coimbatore',
        stations: 2,
        reporting_stations: 0,
        silent_stations: 2,
        readings: 0,
        latest_reading_at: null,
        is_unmonitored: true,
        is_stale: false,
      },
    ],
    transfer: [
      {
        node: 'kanpur',
        local_mae: 9.21,
        train_rows: 55,
        test_rows: 23,
        recommendation: 'no evidence either way: keep the local model',
        candidates: [
          {
            candidate: 'global',
            mae: 9.85,
            gain: -0.631,
            interval_low: -3.441,
            interval_high: 2.203,
            verdict: 'inconclusive',
          },
          {
            candidate: 'local head',
            mae: 8.91,
            gain: 0.303,
            interval_low: -1.606,
            interval_high: 2.115,
            verdict: 'inconclusive',
          },
        ],
      },
      {
        node: 'delhi',
        local_mae: 16.82,
        train_rows: 1719,
        test_rows: 493,
        recommendation: 'no evidence either way: keep the local model',
        candidates: [
          {
            candidate: 'fine-tuned',
            mae: 16.84,
            gain: -0.013,
            interval_low: -0.021,
            interval_high: -0.004,
            verdict: 'no_practical_difference',
          },
        ],
      },
    ],
    ...overrides,
  };
}

function respondWith(body: unknown, init: ResponseInit = { status: 200 }): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        ...init,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FederationView', () => {
  it('shows a loading state before the response arrives', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
    render(<FederationView />);
    expect(screen.getByText(/reading node coverage/i)).toBeInTheDocument();
  });

  it('reports a failure as an error, never as an empty federation', async () => {
    respondWith(
      { error: { code: 'database_unavailable', message: 'The database is not reachable.' } },
      { status: 503 },
    );
    render(<FederationView />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load federation/i);
    expect(screen.queryByText(/did federating help/i)).not.toBeInTheDocument();
  });

  it('keeps a genuine monitoring gap apart from a healthy node', async () => {
    respondWith(status());
    render(<FederationView />);

    const coimbatore = (await screen.findByText('coimbatore')).closest('tr');
    const delhi = screen.getAllByText('delhi')[0]?.closest('tr');
    expect(coimbatore).not.toBeNull();
    expect(within(coimbatore as HTMLElement).getByText('no data ever')).toBeInTheDocument();
    expect(within(delhi as HTMLElement).getByText('reporting')).toBeInTheDocument();
    expect(within(delhi as HTMLElement).getByText('6 silent')).toBeInTheDocument();
  });

  it('prints every gain with its interval and the verdict in words', async () => {
    respondWith(status());
    render(<FederationView />);

    const row = (await screen.findByText('global')).closest('tr') as HTMLElement;
    expect(within(row).getByText('-0.631')).toBeInTheDocument();
    expect(within(row).getByText('-3.441 to 2.203')).toBeInTheDocument();
    expect(within(row).getByText('inconclusive')).toBeInTheDocument();

    const better = screen.getByText('local head').closest('tr') as HTMLElement;
    expect(within(better).getByText('+0.303')).toBeInTheDocument();
    expect(screen.getByText('no practical difference')).toBeInTheDocument();
  });

  it('does not round away a difference the verdict depends on', async () => {
    respondWith(status());
    render(<FederationView />);
    expect(await screen.findByText('-0.021 to -0.004')).toBeInTheDocument();
  });

  it('warns about a thin holdout only where the holdout is thin', async () => {
    respondWith(status());
    render(<FederationView />);
    const warnings = await screen.findAllByText(/a holdout of \d+ rows/i);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toHaveTextContent('23 rows');
  });

  it('never invents a verdict the server did not send', async () => {
    const body = status();
    const kanpur = body.transfer[0];
    const candidate = kanpur?.candidates[0];
    if (!kanpur || !candidate) throw new Error('fixture is missing its first candidate');
    candidate.verdict = 'something_new';
    respondWith(body);

    render(<FederationView />);
    const row = (await screen.findByText('global')).closest('tr') as HTMLElement;
    expect(within(row).getByText('unknown')).toBeInTheDocument();
    expect(within(row).queryByText(/helped|harmed/)).not.toBeInTheDocument();
  });
});
