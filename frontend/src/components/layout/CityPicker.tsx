import { MapPin } from 'lucide-react';
import { useId } from 'react';

import { useScope, type CityKey } from '@/lib/scope';

/** Choose the city every screen shows. Lives in the chrome, so it is always one click away. */
export function CityPicker() {
  const { city, cities, setCity } = useScope();
  const id = useId();

  return (
    <div className="rounded-lg bg-chrome-raised px-3 py-2.5">
      <label
        htmlFor={id}
        className="text-[11px] font-semibold uppercase tracking-wider text-chrome-muted"
      >
        City
      </label>
      <div className="relative mt-1 flex items-center">
        <MapPin aria-hidden className="pointer-events-none absolute left-2 size-4 text-teal-300" />
        <select
          id={id}
          value={city}
          disabled={cities.length === 0}
          onChange={(event) => {
            setCity(event.target.value as CityKey);
          }}
          className="w-full appearance-none rounded-md border border-chrome-border bg-chrome py-1.5 pl-8 pr-8 text-sm font-medium text-chrome-ink"
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
        <span
          aria-hidden
          className="pointer-events-none absolute right-2.5 text-xs text-chrome-muted"
        >
          ▾
        </span>
      </div>
    </div>
  );
}
