import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useHashRoute } from './useHashRoute';

const KEYS = ['overview', 'map', 'alerts'] as const;

afterEach(() => {
  window.location.hash = '';
});

describe('useHashRoute', () => {
  it('falls back to the default when there is no hash', () => {
    const { result } = renderHook(() => useHashRoute(KEYS, 'overview'));
    expect(result.current[0]).toBe('overview');
  });

  it('opens the screen named in the URL, so a link lands where it points', () => {
    window.location.hash = '#/alerts';
    const { result } = renderHook(() => useHashRoute(KEYS, 'overview'));
    expect(result.current[0]).toBe('alerts');
  });

  it('ignores a hash that names no screen', () => {
    window.location.hash = '#/admin';
    const { result } = renderHook(() => useHashRoute(KEYS, 'overview'));
    expect(result.current[0]).toBe('overview');
  });

  it('writes navigation to the URL and follows it, so back and forward work', () => {
    const { result } = renderHook(() => useHashRoute(KEYS, 'overview'));

    act(() => {
      result.current[1]('map');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });

    expect(window.location.hash).toBe('#/map');
    expect(result.current[0]).toBe('map');
  });
});
