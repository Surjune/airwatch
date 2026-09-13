import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MyComplaints } from './MyComplaints';

const LIST = {
  complaint_count: 1,
  note: 'Submissions made from this browser.',
  complaints: [
    {
      reference: 'AW-S-000042',
      kind: 'sensor',
      submitted_at: '2026-09-13T14:47:00Z',
      observed_at: '2026-09-13T14:45:00Z',
      category: 'open_burning',
      area: 'Coimbatore',
      headline: 'AirGradient ONE · 142 µg/m³ PM2.5',
      compared_with_monitor: true,
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('MyComplaints', () => {
  it('asks for this browser’s submissions by header, never in the URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(LIST));
    vi.stubGlobal('fetch', fetchMock);

    render(<MyComplaints />);

    expect(await screen.findByText('AW-S-000042')).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/citizen/complaints');
    expect((init.headers as Record<string, string>)['X-Device-ID']).toMatch(/^device-/);
  });

  it('says why the list can be empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ ...LIST, complaint_count: 0, complaints: [] })),
    );

    render(<MyComplaints />);

    expect(await screen.findByText(/nothing submitted from this browser yet/i)).toBeInTheDocument();
  });

  it('downloads the PDF for a submission', async () => {
    const pdf = new Response(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
      status: 200,
      headers: { 'Content-Disposition': 'attachment; filename="airwatch-AW-S-000042.pdf"' },
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(json(LIST)).mockResolvedValueOnce(pdf);
    vi.stubGlobal('fetch', fetchMock);
    const createUrl = vi.fn().mockReturnValue('blob:report');
    vi.stubGlobal('URL', { ...URL, createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    render(<MyComplaints />);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Download the PDF report for AW-S-000042' }),
    );

    await waitFor(() => {
      expect(click).toHaveBeenCalled();
    });
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/v1/citizen/complaints/AW-S-000042/pdf');
    expect(createUrl).toHaveBeenCalled();
  });

  it('reports a refused download instead of saving an error as a PDF', async () => {
    const refusal = json({ error: { code: 'not_found', message: 'No such complaint.' } }, 404);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(json(LIST)).mockResolvedValueOnce(refusal),
    );

    render(<MyComplaints />);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Download the PDF report for AW-S-000042' }),
    );

    expect(await screen.findByText(/could not be downloaded/i)).toBeInTheDocument();
  });
});
