import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { useCities } from '@/hooks/useAnalysis';
import { ScopeContext, type CityKey, type Pollutant, type Scope } from '@/lib/scope';

/** Where the chosen city and pollutant are remembered between visits. */
const STORAGE_KEY = 'airwatch.scope';

/**
 * The city a first visit opens on. Coimbatore, because that is where this
 * deployment's users and evaluators are -- the place they can check a reading
 * against the air outside their own window.
 */
const DEFAULT_CITY: CityKey = 'coimbatore';
const DEFAULT_POLLUTANT: Pollutant = 'pm10';

interface Stored {
  readonly city: CityKey;
  readonly pollutant: Pollutant;
}

function readStored(): Stored {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Stored>;
      if (parsed.city && parsed.pollutant)
        return { city: parsed.city, pollutant: parsed.pollutant };
    }
  } catch {
    // Storage can be unavailable (private windows, blocked site data); the
    // defaults are a correct view on their own.
  }
  return { city: DEFAULT_CITY, pollutant: DEFAULT_POLLUTANT };
}

function writeStored(value: Stored): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Remembering the choice is a convenience; losing it changes nothing shown.
  }
}

/** Holds the city and pollutant every screen is scoped to. */
export function ScopeProvider({ children }: { readonly children: ReactNode }) {
  const { data } = useCities();
  const [stored, setStored] = useState<Stored>(readStored);

  const cities = useMemo(() => data?.cities ?? [], [data]);

  const setCity = useCallback(
    (city: CityKey) => {
      const pollutant = cities.find((item) => item.city === city)?.default_pollutant;
      setStored((previous) => {
        const next = { city, pollutant: pollutant ?? previous.pollutant };
        writeStored(next);
        return next;
      });
    },
    [cities],
  );

  const setPollutant = useCallback((pollutant: Pollutant) => {
    setStored((previous) => {
      const next = { ...previous, pollutant };
      writeStored(next);
      return next;
    });
  }, []);

  const scope = useMemo<Scope>(
    () => ({
      city: stored.city,
      pollutant: stored.pollutant,
      current: cities.find((item) => item.city === stored.city) ?? null,
      cities,
      setCity,
      setPollutant,
    }),
    [stored, cities, setCity, setPollutant],
  );

  return <ScopeContext.Provider value={scope}>{children}</ScopeContext.Provider>;
}
