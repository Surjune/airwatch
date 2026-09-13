/** How much a data tier is contributing in a city right now. */
export type TierState = 'live' | 'thin' | 'none' | 'loading';

/**
 * Reference monitors a city needs before a station can be judged against its
 * neighbours: the station itself plus the backend's minimum of three neighbours.
 * Below this, detection cannot run and the tier is thin however healthy each
 * monitor is.
 */
export const MONITORS_FOR_DETECTION = 4;

/**
 * How much a tier contributes, from a count of what it holds.
 *
 * @param count - What the tier holds in this city, or undefined while loading.
 * @param enough - The count at which the tier stops being thin.
 * @param failed - The request failed, so nothing can be said at all.
 */
export function tierState(count: number | undefined, enough: number, failed = false): TierState {
  if (failed) return 'none';
  if (count === undefined) return 'loading';
  if (count === 0) return 'none';
  return count >= enough ? 'live' : 'thin';
}
