import { Send } from 'lucide-react';
import { useId, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { LocationPicker, type PickedPosition } from '@/features/citizen/LocationPicker';
import type { SensorReadingInput } from '@/hooks/useCitizenSensors';
import { VIEW_POLLUTANTS, type Pollutant } from '@/lib/scope';

/** Instruments commonly owned in Indian cities, offered as suggestions only. */
const KNOWN_SENSORS = [
  'AirGradient ONE',
  'AirGradient Open Air',
  'PurpleAir PA-II',
  'Atmotube PRO',
  'Prana Air Sensible+',
  'Xiaomi Mi Air Purifier sensor',
] as const;

/** Shortest instrument name the API accepts. */
const MIN_MODEL_LENGTH = 2;

/** `datetime-local` wants minutes precision in local time: "2026-09-13T18:45". */
const LOCAL_MINUTES_LENGTH = 16;
const MS_PER_MINUTE = 60_000;

function localNow(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * MS_PER_MINUTE)
    .toISOString()
    .slice(0, LOCAL_MINUTES_LENGTH);
}

interface SensorReadingFormProps {
  readonly isSubmitting: boolean;
  readonly onSubmit: (input: SensorReadingInput) => void;
}

/**
 * Report what a household air-quality sensor is showing.
 *
 * Asks for the instrument by name because the bias differs between models, and a
 * correction can only ever be fitted per model if the model was recorded. The
 * time is when the sensor measured, defaulting to now, since a reading copied off
 * a display an hour later describes different air.
 */
export function SensorReadingForm({ isSubmitting, onSubmit }: SensorReadingFormProps) {
  const [pollutant, setPollutant] = useState<Pollutant>('pm25');
  const [value, setValue] = useState('');
  const [model, setModel] = useState('');
  const [observedAt, setObservedAt] = useState(localNow);
  const [position, setPosition] = useState<PickedPosition | null>(null);
  const ids = { value: useId(), model: useId(), time: useId(), list: useId() };

  const numeric = Number(value);
  const isValid =
    value.trim() !== '' &&
    Number.isFinite(numeric) &&
    numeric >= 0 &&
    model.trim().length >= MIN_MODEL_LENGTH &&
    observedAt !== '' &&
    position !== null;

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (!isValid) return;
        onSubmit({
          longitude: position.longitude,
          latitude: position.latitude,
          pollutant: pollutant === 'pm10' ? 'pm10' : 'pm25',
          value_ugm3: numeric,
          observed_at: new Date(observedAt).toISOString(),
          sensor_model: model.trim(),
        });
      }}
    >
      <fieldset>
        <legend className="text-xs font-medium text-ink-muted">What it measured</legend>
        <div className="mt-1.5 flex flex-wrap items-end gap-3">
          <SegmentedControl
            label="Pollutant"
            options={VIEW_POLLUTANTS}
            value={pollutant}
            onChange={setPollutant}
          />
          <label htmlFor={ids.value} className="block min-w-0 flex-1 basis-40">
            <span className="text-xs font-medium text-ink-muted">Reading, µg/m³</span>
            <input
              id={ids.value}
              type="number"
              inputMode="decimal"
              min={0}
              step="any"
              required
              value={value}
              onChange={(event) => {
                setValue(event.target.value);
              }}
              placeholder="e.g. 42"
              className="figure mt-1 min-h-10 w-full rounded-sm border border-border-strong bg-paper px-3 text-base text-ink"
            />
          </label>
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <label htmlFor={ids.model} className="block">
          <span className="text-xs font-medium text-ink-muted">Sensor model</span>
          <input
            id={ids.model}
            list={ids.list}
            required
            value={model}
            onChange={(event) => {
              setModel(event.target.value);
            }}
            placeholder="e.g. AirGradient ONE"
            className="mt-1 min-h-10 w-full rounded-sm border border-border-strong bg-paper px-3 text-sm text-ink"
          />
          <datalist id={ids.list}>
            {KNOWN_SENSORS.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <label htmlFor={ids.time} className="block">
          <span className="text-xs font-medium text-ink-muted">When it measured</span>
          <input
            id={ids.time}
            type="datetime-local"
            required
            value={observedAt}
            onChange={(event) => {
              setObservedAt(event.target.value);
            }}
            className="figure mt-1 min-h-10 w-full rounded-sm border border-border-strong bg-paper px-3 text-sm text-ink"
          />
        </label>
      </div>

      <div>
        <p className="text-xs font-medium text-ink-muted">Where the sensor is</p>
        <div className="mt-1.5">
          <LocationPicker position={position} onChange={setPosition} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <Button
          type="submit"
          variant="primary"
          size="md"
          disabled={!isValid}
          isBusy={isSubmitting}
          busyLabel="Comparing…"
        >
          <Send aria-hidden className="size-4" />
          Submit reading
        </Button>
        {!isValid && !isSubmitting && (
          <p className="text-xs text-ink-subtle">
            Add the reading, the sensor model and a position.
          </p>
        )}
      </div>
    </form>
  );
}
