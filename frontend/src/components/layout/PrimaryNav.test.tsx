import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SCREENS } from './navigation';
import { PrimaryNav } from './PrimaryNav';

function renderNav(variant: 'bar' | 'dock', onNavigate = vi.fn()) {
  render(<PrimaryNav active="alerts" onNavigate={onNavigate} variant={variant} />);
  return onNavigate;
}

describe.each(['bar', 'dock'] as const)('PrimaryNav (%s)', (variant) => {
  it('links to every screen by its URL', () => {
    renderNav(variant);
    for (const item of SCREENS) {
      expect(screen.getByRole('link', { name: new RegExp(item.label) })).toHaveAttribute(
        'href',
        `#/${item.key}`,
      );
    }
  });

  it('marks only the open screen as current', () => {
    renderNav(variant);
    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(/Authority console/);
  });

  it('navigates in place on a plain click', () => {
    const onNavigate = renderNav(variant);
    fireEvent.click(screen.getByRole('link', { name: /Live map/ }));
    expect(onNavigate).toHaveBeenCalledWith('map');
  });

  it('leaves a modified click to the browser, so a screen can open in a new tab', () => {
    const onNavigate = renderNav(variant);
    fireEvent.click(screen.getByRole('link', { name: /Live map/ }), { ctrlKey: true });
    expect(onNavigate).not.toHaveBeenCalled();
  });
});

describe('PrimaryNav (dock)', () => {
  it('uses the short label on a phone, where there is room for one word', () => {
    renderNav('dock');
    expect(screen.getByRole('link', { name: 'Authority console' })).toHaveTextContent('Alerts');
  });
});
