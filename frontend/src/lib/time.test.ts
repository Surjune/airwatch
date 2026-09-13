import { describe, expect, it } from 'vitest';

import { istDateTime, timeAgo } from './time';

describe('istDateTime', () => {
  it('shifts UTC to India Standard Time', () => {
    // 18:30 UTC is midnight the next day in IST (UTC+05:30).
    expect(istDateTime('2026-09-12T18:30:00Z')).toMatch(/13 Sept?.*12:00\s?am/i);
  });
});

describe('timeAgo', () => {
  const now = new Date('2026-09-13T12:00:00Z');

  it.each([
    ['2026-09-13T11:59:45Z', 'just now'],
    ['2026-09-13T11:35:00Z', '25 min ago'],
    ['2026-09-13T09:00:00Z', '3 h ago'],
    ['2026-09-10T12:00:00Z', '3 days ago'],
  ])('describes %s as %s', (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });
});
