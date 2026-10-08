/** Milliseconds in an hour, for comparing reading ages. */
const MS_PER_HOUR = 3_600_000;

/**
 * Oldest reading, in hours, that counts as "right now".
 *
 * OpenAQ relays some stations hours late, so an hour would leave too few; a
 * reading several days old, which some stations serve until they report again,
 * describes different air altogether.
 */
export const RECENT_READING_HOURS = 6;

/**
 * Oldest CPCB daily bulletin, in hours past the 4 pm its average runs to, that
 * still counts as current: the next one runs to 4 pm the following day and
 * appears some time after, so a day and a few hours.
 */
export const BULLETIN_RECENT_HOURS = 30;

/** Whether a reading is recent enough to describe the air now. */
export function isRecent(
  observedAt: string,
  now: Date = new Date(),
  maxAgeHours: number = RECENT_READING_HOURS,
): boolean {
  return (now.getTime() - new Date(observedAt).getTime()) / MS_PER_HOUR <= maxAgeHours;
}

export interface Ranked<T> {
  /** Readings recent enough to compare, worst first. */
  readonly recent: readonly T[];
  /** How many monitors last reported longer ago than that. */
  readonly staleCount: number;
}

/**
 * Rank monitors by how bad their air is now, leaving out the ones gone quiet.
 *
 * A station that stopped reporting three days ago keeps its last value, and
 * ranked by concentration alone it can top a list headed "right now" -- a
 * reading about air that has long since blown away.
 */
export function rankRecent<T extends { readonly aqi: number; readonly observed_at: string }>(
  readings: readonly T[],
  now: Date = new Date(),
  maxAgeHours: number = RECENT_READING_HOURS,
): Ranked<T> {
  const recent = readings.filter((reading) => isRecent(reading.observed_at, now, maxAgeHours));
  return {
    recent: [...recent].sort((a, b) => b.aqi - a.aqi),
    staleCount: readings.length - recent.length,
  };
}
