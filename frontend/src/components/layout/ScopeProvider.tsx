import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { useCities } from '@/hooks/useAnalysis';
import { readLinked, ScopeContext, type CityKey, type Pollutant, type Scope } from '@/lib/scope';

/**
 * Where the chosen city and pollutant are remembered between visits.
 *
 * Versioned: the key changed when the default moved from Coimbatore to Delhi,
 * so every browser that visited before opens on Delhi once, and remembers
 * whatever it picks from then on.
 */
const STORAGE_KEY = 'airwatch.scope.v2';

/**
 * The city a first visit opens on. Delhi, because its dense network of
 * reference monitors keeps every screen live -- current readings, hotspots
 * with their likely sources, corridor forecasts. Coimbatore, which rests on a
 * single monitor that reports intermittently, is one pick away.
 */
const DEFAULT_CITY: CityKey = 'delhi';

/**
 * The pollutant shown before the city list has said what each city's monitors
 * report. Only a placeholder: an unchosen pollutant follows the city.
 */
const FALLBACK_POLLUTANT: Pollutant = 'pm25';

interface Stored {
  readonly city: CityKey;
  /**
   * Null until someone picks one, meaning the city's own default: a link to
   * Coimbatore must open on the PM10 its monitor reports, not on Delhi's PM2.5.
   */
  readonly pollutant: Pollutant | null;
}

function readStored(): Stored {
  const linked = readLinked(window.location.search);
  if (linked.city) {
    return { city: linked.city, pollutant: linked.pollutant ?? null };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Stored>;
      if (parsed.city) return { city: parsed.city, pollutant: parsed.pollutant ?? null };
    }
  } catch {
    // Storage can be unavailable (private windows, blocked site data); the
    // defaults are a correct view on their own.
  }
  return { city: DEFAULT_CITY, pollutant: null };
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

  // A new city opens on the pollutant its own monitors report, so the choice is
  // cleared rather than carried over.
  const setCity = useCallback((city: CityKey) => {
    const next: Stored = { city, pollutant: null };
    writeStored(next);
    setStored(next);
  }, []);

  const setPollutant = useCallback((pollutant: Pollutant) => {
    setStored((previous) => {
      const next = { ...previous, pollutant };
      writeStored(next);
      return next;
    });
  }, []);

  const scope = useMemo<Scope>(() => {
    const current = cities.find((item) => item.city === stored.city) ?? null;
    return {
      city: stored.city,
      pollutant: stored.pollutant ?? current?.default_pollutant ?? FALLBACK_POLLUTANT,
      current,
      cities,
      setCity,
      setPollutant,
    };
  }, [stored, cities, setCity, setPollutant]);

  return <ScopeContext.Provider value={scope}>{children}</ScopeContext.Provider>;
}
