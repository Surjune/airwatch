import { LocateFixed, MapPin } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { isWithinIndia } from '@/lib/geo';

export interface PickedPosition {
  readonly longitude: number;
  readonly latitude: number;
  readonly source: 'device' | 'manual';
}

interface LocationPickerProps {
  readonly position: PickedPosition | null;
  readonly onChange: (position: PickedPosition | null) => void;
}

const LAT_RANGE = { min: -90, max: 90 };
const LON_RANGE = { min: -180, max: 180 };

/**
 * Where the photograph was taken: from the device, or typed in.
 *
 * Manual entry exists because location permission is often refused or
 * unavailable on a desktop, and a submitter without it previously had no way to
 * submit at all. Both paths are checked against the covered area before sending,
 * since a position outside it is far more likely to be a browser default or a
 * transposed pair than a real photograph.
 */
export function LocationPicker({ position, onChange }: LocationPickerProps) {
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');

  const accept = useCallback(
    (candidate: PickedPosition) => {
      setProblem(
        isWithinIndia([candidate.longitude, candidate.latitude])
          ? null
          : 'That position is outside the area this deployment covers. Check it before submitting.',
      );
      onChange(candidate);
    },
    [onChange],
  );

  const locate = useCallback(() => {
    setProblem(null);
    if (!('geolocation' in navigator)) {
      setProblem('This browser cannot report a location. Enter coordinates below instead.');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (found) => {
        setLocating(false);
        accept({
          longitude: found.coords.longitude,
          latitude: found.coords.latitude,
          source: 'device',
        });
      },
      (cause) => {
        setLocating(false);
        setProblem(`Could not read a location (${cause.message}). Enter coordinates below.`);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, [accept]);

  const applyManual = (nextLat: string, nextLon: string) => {
    setLatitude(nextLat);
    setLongitude(nextLon);
    const lat = Number(nextLat);
    const lon = Number(nextLon);
    const valid =
      nextLat.trim() !== '' &&
      nextLon.trim() !== '' &&
      lat >= LAT_RANGE.min &&
      lat <= LAT_RANGE.max &&
      lon >= LON_RANGE.min &&
      lon <= LON_RANGE.max;
    if (valid) accept({ latitude: lat, longitude: lon, source: 'manual' });
    else onChange(null);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={locate} isBusy={locating} busyLabel="Locating…">
          <LocateFixed aria-hidden className="size-3.5" />
          Use my location
        </Button>
        {position && (
          <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
            <MapPin aria-hidden className="size-3.5 text-accent" />
            {position.latitude.toFixed(4)}, {position.longitude.toFixed(4)}
            {position.source === 'device' ? ' · from this device' : ' · entered by hand'}
          </span>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <CoordinateField
          label="Latitude"
          placeholder="28.6139"
          value={latitude}
          onChange={(value) => {
            applyManual(value, longitude);
          }}
        />
        <CoordinateField
          label="Longitude"
          placeholder="77.2090"
          value={longitude}
          onChange={(value) => {
            applyManual(latitude, value);
          }}
        />
      </div>

      {problem && (
        <p role="alert" className="mt-2 rounded-md bg-warn-subtle px-2.5 py-1.5 text-xs text-warn">
          {problem}
        </p>
      )}
    </div>
  );
}

function CoordinateField({
  label,
  placeholder,
  value,
  onChange,
}: {
  readonly label: string;
  readonly placeholder: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-ink-muted">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="any"
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="mt-1 w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-ink-subtle"
      />
    </label>
  );
}
