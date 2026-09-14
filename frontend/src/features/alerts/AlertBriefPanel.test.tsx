import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AlertBriefPanel } from './AlertBriefPanel';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AlertBriefPanel', () => {
  it('asks for nothing until someone wants the brief', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<AlertBriefPanel alertId={7} />);

    expect(screen.getByRole('button', { name: /Summarise with Gemini/ })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the brief, its suggested step and how it was checked', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      json({
        alert_id: 7,
        summary: 'PM2.5 at Khora read 74 µg/m³ against 20 predicted.',
        suggested_action: 'Inspect the Ghazipur landfill for surface fires.',
        model: 'gemini-3.6-flash',
        generated_at: '2026-09-14T10:00:00Z',
        notice: 'Every number in it was checked against those figures.',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<AlertBriefPanel alertId={7} />);
    fireEvent.click(screen.getByRole('button', { name: /Summarise with Gemini/ }));

    expect(await screen.findByText(/74 µg\/m³ against 20 predicted/)).toBeInTheDocument();
    expect(screen.getByText(/Inspect the Ghazipur landfill/)).toBeInTheDocument();
    expect(screen.getByText(/checked against those figures/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/v1/alerts/7/brief');
  });

  it('says why when a brief could not be shown', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json(
          {
            error: {
              code: 'ai_output_ungrounded',
              message:
                'Gemini’s brief stated figures this alert does not contain, so it was discarded.',
            },
          },
          502,
        ),
      ),
    );

    render(<AlertBriefPanel alertId={7} />);
    fireEvent.click(screen.getByRole('button', { name: /Summarise with Gemini/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/discarded/);
  });
});
