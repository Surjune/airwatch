import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ScopeContext, type Scope } from '@/lib/scope';

import { SCREENS } from './navigation';
import { Sidebar } from './Sidebar';

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSidebar(onNavigate = vi.fn(), setCity = vi.fn()) {
  // The API status panel inside the sidebar calls /health; keep it pending.
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
  const scope: Scope = {
    city: 'coimbatore',
    pollutant: 'pm10',
    current: null,
    cities: [
      {
        city: 'coimbatore',
        label: 'Coimbatore',
        centre: { longitude: 76.9558, latitude: 11.0168 },
        radius_m: 40_000,
        default_pollutant: 'pm10',
      },
      {
        city: 'delhi',
        label: 'Delhi-NCR',
        centre: { longitude: 77.209, latitude: 28.6139 },
        radius_m: 40_000,
        default_pollutant: 'pm25',
      },
    ],
    setCity,
    setPollutant: vi.fn(),
  };
  render(
    <ScopeContext.Provider value={scope}>
      <Sidebar active="alerts" onNavigate={onNavigate} />
    </ScopeContext.Provider>,
  );
  return onNavigate;
}

describe('Sidebar', () => {
  it('links to every screen by its URL', () => {
    renderSidebar();
    for (const item of SCREENS) {
      expect(screen.getByRole('link', { name: new RegExp(item.label) })).toHaveAttribute(
        'href',
        `#/${item.key}`,
      );
    }
  });

  it('marks only the open screen as current', () => {
    renderSidebar();
    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent('Authority console');
  });

  it('navigates in place on a plain click', () => {
    const onNavigate = renderSidebar();
    fireEvent.click(screen.getByRole('link', { name: /Live map/ }));
    expect(onNavigate).toHaveBeenCalledWith('map');
  });

  it('leaves a modified click to the browser, so a screen can open in a new tab', () => {
    const onNavigate = renderSidebar();
    fireEvent.click(screen.getByRole('link', { name: /Live map/ }), { ctrlKey: true });
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it('offers every city and switches when one is chosen', () => {
    const setCity = vi.fn();
    renderSidebar(vi.fn(), setCity);

    const picker = screen.getByLabelText('City');
    expect(picker).toHaveValue('coimbatore');
    expect(screen.getByRole('option', { name: 'Delhi-NCR' })).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: 'delhi' } });
    expect(setCity).toHaveBeenCalledWith('delhi');
  });

  it('shows the connection state while the API is being checked', () => {
    renderSidebar();
    expect(screen.getByRole('status')).toHaveTextContent('Connecting');
  });
});
