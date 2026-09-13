import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiStatus } from './ApiStatus';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ApiStatus', () => {
  it('shows the connection state while the API is being checked', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
    render(<ApiStatus />);
    expect(screen.getByRole('status')).toHaveTextContent('Connecting');
  });

  it('says the API is unreachable rather than showing a quiet state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')));
    render(<ApiStatus />);
    expect(await screen.findByText(/API unreachable\./)).toBeInTheDocument();
  });
});
