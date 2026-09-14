import { describe, expect, it } from 'vitest';

import { rankRecent } from './readings';

const NOW = new Date('2026-09-14T06:00:00Z');

const reading = (name: string, aqi: number, observed_at: string) => ({ name, aqi, observed_at });

describe('rankRecent', () => {
  it('ranks recent readings worst first', () => {
    const { recent } = rankRecent(
      [reading('clean', 60, '2026-09-14T05:30:00Z'), reading('bad', 210, '2026-09-14T04:30:00Z')],
      NOW,
    );

    expect(recent.map((item) => item.name)).toEqual(['bad', 'clean']);
  });

  it('leaves out a monitor that went quiet days ago, however high its last value', () => {
    const { recent, staleCount } = rankRecent(
      [reading('stale', 241, '2026-09-11T04:30:00Z'), reading('now', 108, '2026-09-14T05:30:00Z')],
      NOW,
    );

    expect(recent.map((item) => item.name)).toEqual(['now']);
    expect(staleCount).toBe(1);
  });

  it('keeps a reading exactly at the limit', () => {
    const { recent } = rankRecent([reading('edge', 90, '2026-09-14T00:00:00Z')], NOW, 6);

    expect(recent).toHaveLength(1);
  });
});
