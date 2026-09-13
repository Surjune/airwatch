import { describe, expect, it } from 'vitest';

import { MONITORS_FOR_DETECTION, tierState } from './tiers';

describe('tierState', () => {
  it('is checking while the count is unknown', () => {
    expect(tierState(undefined, 1)).toBe('loading');
  });

  it('reports nothing for an empty tier, never a quiet healthy one', () => {
    expect(tierState(0, 1)).toBe('none');
  });

  it('reports nothing when the request failed, whatever was cached', () => {
    expect(tierState(12, 1, true)).toBe('none');
  });

  it('calls one working monitor thin, because detection needs neighbours', () => {
    expect(tierState(1, MONITORS_FOR_DETECTION)).toBe('thin');
  });

  it('is contributing at the threshold', () => {
    expect(tierState(MONITORS_FOR_DETECTION, MONITORS_FOR_DETECTION)).toBe('live');
  });
});
