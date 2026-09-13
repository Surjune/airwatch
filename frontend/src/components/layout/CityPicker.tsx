import { ChevronDown, MapPin } from 'lucide-react';
import { useId } from 'react';

import { useScope, type CityKey } from '@/lib/scope';

/**
 * Choose the city every screen shows.
 *
 * Lives in the masthead on every screen and every width, so the place a number
 * describes is never more than a glance away.
 */
export function CityPicker() {
  const { city, cities, setCity } = useScope();
  const id = useId();

  return (
    <div className="relative flex items-center">
      <label htmlFor={id} className="sr-only">
        City
      </label>
      <MapPin aria-hidden className="pointer-events-none absolute left-2 size-3.5 text-signal" />
      <select
        id={id}
        value={city}
        disabled={cities.length === 0}
        onChange={(event) => {
          setCity(event.target.value as CityKey);
        }}
        className="min-h-8 appearance-none rounded-[4px] border border-border-strong bg-surface py-1 pl-7 pr-7 text-[13px] font-semibold text-ink hover:border-ink/40"
      >
        {cities.length === 0 ? (
          <option value={city}>Loading…</option>
        ) : (
          cities.map((option) => (
            <option key={option.city} value={option.city}>
              {option.label}
            </option>
          ))
        )}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute right-2 size-3.5 text-ink-subtle"
      />
    </div>
  );
}
