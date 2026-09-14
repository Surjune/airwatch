import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Alert } from '@/hooks/useAlerts';

import { AlertCard } from './AlertCard';

function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    alert_id: 7,
    status: 'sent',
    authority_id: 1,
    authority_name: 'DPCC East',
    hotspot_id: 3,
    station_name: 'Anand Vihar',
    position: { longitude: 77.3152, latitude: 28.6469 },
    pollutant: 'pm25',
    first_seen_at: '2026-09-12T08:00:00Z',
    last_seen_at: '2026-09-12T11:00:00Z',
    peak_observed: 381,
    peak_expected: 40,
    peak_excess: 341,
    peak_z: 6.2,
    sent_at: '2026-09-12T11:05:00Z',
    delivered_at: '2026-09-12T11:05:02Z',
    delivery_error: null,
    acknowledged_at: null,
    resolved_at: null,
    resolution_note: null,
    kind: 'local',
    source_name: null,
    source_confidence: null,
    ...overrides,
  };
}

function renderCard(alert: Alert, props: { isOverdue?: boolean; isBusy?: boolean } = {}) {
  const onAcknowledge = vi.fn();
  const onResolve = vi.fn();
  render(
    <AlertCard
      alert={alert}
      isOverdue={props.isOverdue ?? false}
      isBusy={props.isBusy ?? false}
      onAcknowledge={onAcknowledge}
      onResolve={onResolve}
    />,
  );
  return { onAcknowledge, onResolve };
}

/** The controls that change an alert's trail, as opposed to reading it. */
const ACTIONS = /Acknowledge|Resolve|Close alert/;

describe('AlertCard', () => {
  it('leads with the comparison, not the bare concentration', () => {
    renderCard(makeAlert());
    expect(screen.getByText('381 µg/m³')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('341 µg/m³')).toBeInTheDocument();
  });

  it('says when it is asking a neighbour to act on a source on its ground', () => {
    renderCard(
      makeAlert({
        kind: 'coordination',
        authority_name: 'Ghaziabad District',
        source_name: 'Brick kiln cluster',
        source_confidence: 0.72,
      }),
    );
    expect(screen.getByText(/coordination request/i)).toBeInTheDocument();
    expect(screen.getByText('Brick kiln cluster')).toBeInTheDocument();
    expect(screen.getByText(/72% plausible/)).toBeInTheDocument();
    expect(screen.getByText(/not an established cause/i)).toBeInTheDocument();
  });

  it('does not describe a local alert as a coordination request', () => {
    renderCard(makeAlert());
    expect(screen.queryByText(/coordination request/i)).not.toBeInTheDocument();
  });

  it('names ground no station covers instead of leaving the title blank', () => {
    renderCard(makeAlert({ station_name: null }));
    expect(screen.getByRole('heading', { name: 'Unmonitored location' })).toBeInTheDocument();
  });

  it('flags an alert past its deadline', () => {
    renderCard(makeAlert(), { isOverdue: true });
    expect(screen.getByText(/past its response deadline/i)).toBeInTheDocument();
  });

  it('does not flag an alert still within its deadline', () => {
    renderCard(makeAlert());
    expect(screen.queryByText(/past its response deadline/i)).not.toBeInTheDocument();
  });

  it('distinguishes a recorded alert that reached nobody', () => {
    renderCard(makeAlert({ delivered_at: null, delivery_error: 'endpoint returned 503' }));
    expect(screen.getByText('not delivered')).toBeInTheDocument();
    expect(screen.getByText(/delivery failed: endpoint returned 503/i)).toBeInTheDocument();
  });

  it('acknowledges by alert id', () => {
    const { onAcknowledge } = renderCard(makeAlert());
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }));
    expect(onAcknowledge).toHaveBeenCalledWith(7);
  });

  it('prevents a double submission while a request is in flight', () => {
    renderCard(makeAlert(), { isBusy: true });
    expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Resolve' })).toBeDisabled();
  });

  it('refuses to resolve without a note', () => {
    const { onResolve } = renderCard(makeAlert());
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    const close = screen.getByRole('button', { name: 'Close alert' });
    expect(close).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } });
    expect(close).toBeDisabled();
    expect(onResolve).not.toHaveBeenCalled();
  });

  it('resolves with the note once one is written', () => {
    const { onResolve } = renderCard(makeAlert());
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Waste fire put out.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Close alert' }));

    expect(onResolve).toHaveBeenCalledWith(7, 'Waste fire put out.');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows a read-only viewer the trail without any actions', () => {
    render(
      <AlertCard
        alert={makeAlert({ delivered_at: null })}
        isOverdue
        isBusy={false}
        canAct={false}
        onAcknowledge={vi.fn()}
        onResolve={vi.fn()}
      />,
    );
    expect(screen.getByText(/past its response deadline/i)).toBeInTheDocument();
    expect(screen.getByText('not delivered')).toBeInTheDocument();
    // Reading aids such as the Gemini brief remain; what is withheld is changing the trail.
    expect(screen.queryByRole('button', { name: ACTIONS })).not.toBeInTheDocument();
  });

  it('shows the resolution and offers no further actions once resolved', () => {
    renderCard(
      makeAlert({ status: 'resolved', delivered_at: null, resolution_note: 'Kiln sealed.' }),
    );
    expect(screen.getByText('Kiln sealed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: ACTIONS })).not.toBeInTheDocument();
    expect(screen.queryByText('not delivered')).not.toBeInTheDocument();
  });
});
