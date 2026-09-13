import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StatusMessage } from './StatusMessage';

describe('StatusMessage', () => {
  it('announces a failure as an alert, so it interrupts', () => {
    render(<StatusMessage kind="error" title="Could not load" detail="Upstream timed out." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load');
    expect(screen.getByRole('alert')).toHaveTextContent('Upstream timed out.');
  });

  it.each(['loading', 'empty'] as const)('announces %s politely as a status', (kind) => {
    render(<StatusMessage kind={kind} title="Nothing yet" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('gives each state its own glyph, so colour is never the only signal', () => {
    const glyphs = (['loading', 'error', 'empty'] as const).map((kind) => {
      const { container, unmount } = render(<StatusMessage kind={kind} title="t" />);
      const glyph = container.querySelector('[aria-hidden]')?.textContent;
      unmount();
      return glyph;
    });
    expect(new Set(glyphs).size).toBe(3);
  });

  it('shows the request id so a failure can be traced in the logs', () => {
    render(<StatusMessage kind="error" title="Failed" requestId="req-abc123" />);
    expect(screen.getByText('req-abc123')).toBeInTheDocument();
  });

  it('omits the request line when there is no id', () => {
    render(<StatusMessage kind="error" title="Failed" />);
    expect(screen.queryByText(/^request/)).not.toBeInTheDocument();
  });
});
