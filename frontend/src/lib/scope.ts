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
