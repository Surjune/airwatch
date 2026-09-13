import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ScopeContext, type Scope } from '@/lib/scope';

import { SensorReadingForm } from './SensorReadingForm';

const SCOPE: Scope = {
  city: 'coimbatore',
  pollutant: 'pm10',
  current: {
    city: 'coimbatore',
    label: 'Coimbatore',
    centre: { longitude: 76.9558, latitude: 11.0168 },
    radius_m: 40_000,
    default_pollutant: 'pm10',
  },
  cities: [],
  setCity: vi.fn(),
  setPollutant: vi.fn(),
};

function renderForm(onSubmit = vi.fn()) {
  render(
    <ScopeContext.Provider value={SCOPE}>
      <SensorReadingForm isSubmitting={false} onSubmit={onSubmit} />
    </ScopeContext.Provider>,
  );
  return onSubmit;
}

function fillPosition() {
  fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: '10.9425' } });
  fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: '76.9790' } });
}

describe('SensorReadingForm', () => {
  it('cannot be submitted until the reading, the model and a position are given', () => {
    renderForm();
    const submit = screen.getByRole('button', { name: /submit reading/i });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/reading, µg\/m³/i), { target: { value: '48' } });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/sensor model/i), {
      target: { value: 'AirGradient ONE' },
    });
    expect(submit).toBeDisabled();

    fillPosition();
    expect(submit).toBeEnabled();
  });

  it('sends the reading as the sensor showed it, with a timezone-aware time', () => {
    const onSubmit = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'PM10' }));
    fireEvent.change(screen.getByLabelText(/reading, µg\/m³/i), { target: { value: '61.5' } });
    fireEvent.change(screen.getByLabelText(/sensor model/i), {
      target: { value: '  Atmotube PRO ' },
    });
    fillPosition();
    fireEvent.click(screen.getByRole('button', { name: /submit reading/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(body).toMatchObject({
      pollutant: 'pm10',
      value_ugm3: 61.5,
      sensor_model: 'Atmotube PRO',
      latitude: 10.9425,
      longitude: 76.979,
    });
    expect(body.observed_at).toMatch(/Z$/);
  });

  it('refuses a negative reading before it reaches the server', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText(/reading, µg\/m³/i), { target: { value: '-4' } });
    fireEvent.change(screen.getByLabelText(/sensor model/i), {
      target: { value: 'AirGradient ONE' },
    });
    fillPosition();
    expect(screen.getByRole('button', { name: /submit reading/i })).toBeDisabled();
  });
});
