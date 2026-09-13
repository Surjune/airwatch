import { createContext, useContext } from 'react';

import type { components } from '@/lib/api-types';

export type City = components['schemas']['CityResponse'];
export type CityKey = components['schemas']['PilotCity'];
export type Pollutant = components['schemas']['Pollutant'];

/** The pollutants a dashboard view can switch between. */
export const VIEW_POLLUTANTS = [
  { key: 'pm25', label: 'PM2.5' },
  { key: 'pm10', label: 'PM10' },
] as const satisfies readonly { key: Pollutant; label: string }[];

/** Every city key the API serves, so a value from a link can be checked before use. */
const CITY_KEYS: readonly CityKey[] = ['delhi', 'kanpur', 'coimbatore'];

/**
 * A city and pollutant named in the address, as in `/?city=delhi&pollutant=pm25`.
 *
 * Lets a view be shared -- "look at the Delhi map" -- and wins over what the
 * browser remembered, because a link someone sent is a statement about what to
 * look at. An unknown value is ignored rather than trusted.
 */
export function readLinked(search: string): { city?: CityKey; pollutant?: Pollutant } {
  const params = new URLSearchParams(search);
  const city = CITY_KEYS.find((key) => key === params.get('city'));
  const pollutant = VIEW_POLLUTANTS.find((option) => option.key === params.get('pollutant'))?.key;
  return { ...(city ? { city } : {}), ...(pollutant ? { pollutant } : {}) };
}

export function pollutantLabel(pollutant: Pollutant): string {
  return (
    VIEW_POLLUTANTS.find((option) => option.key === pollutant)?.label ?? pollutant.toUpperCase()
  );
}

/** What every screen is currently looking at. */
export interface Scope {
  readonly city: CityKey;
  readonly pollutant: Pollutant;
  /** The full record for the selected city, once the list has loaded. */
  readonly current: City | null;
  readonly cities: readonly City[];
  /** Switching city also switches to the pollutant that city's monitors report. */
  readonly setCity: (city: CityKey) => void;
  readonly setPollutant: (pollutant: Pollutant) => void;
}

export const ScopeContext = createContext<Scope | null>(null);

/**
 * The city and pollutant the dashboard is scoped to.
 *
 * Throws outside the provider rather than falling back to a default city: a
 * screen that silently showed Delhi while the header said Coimbatore would be
 * wrong in the most misleading way available.
 */
export function useScope(): Scope {
  const scope = useContext(ScopeContext);
  if (!scope) throw new Error('useScope must be used inside ScopeProvider.');
  return scope;
}
