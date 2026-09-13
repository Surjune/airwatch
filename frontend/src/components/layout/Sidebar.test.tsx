import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SCREENS } from './navigation';
import { Sidebar } from './Sidebar';

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSidebar(onNavigate = vi.fn()) {
  // The API status panel inside the sidebar calls /health; keep it pending.
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
  render(<Sidebar active="alerts" onNavigate={onNavigate} />);
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

  it('shows the connection state while the API is being checked', () => {
    renderSidebar();
    expect(screen.getByRole('status')).toHaveTextContent('Connecting');
  });
});
