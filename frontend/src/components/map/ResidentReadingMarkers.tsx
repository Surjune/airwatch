import { divIcon } from 'leaflet';
import { Marker, Popup } from 'react-leaflet';

import type { SensorReading } from '@/hooks/useCitizenSensors';
import { aqiColour } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';
import { timeAgo } from '@/lib/time';

/** Side of the square marker, in pixels. */
const MARKER_PX = 12;

/**
 * Readings residents submitted from their own sensors, as small squares.
 *
 * A square rather than a circle, so a resident's reading is never mistaken for a
 * monitor (filled circle) or a community network sensor (dashed ring). The popup
 * says in words that the value is as reported and compares it with the monitor
 * it was checked against.
 */
export function ResidentReadingMarkers({
  readings,
}: {
  readonly readings: readonly SensorReading[];
}) {
  return (
    <>
      {readings.map((reading) => (
        <Marker
          key={`resident-${String(reading.reading_id)}`}
          position={toLeaflet([reading.position.longitude, reading.position.latitude])}
          icon={divIcon({
            className: '',
            iconSize: [MARKER_PX, MARKER_PX],
            html: `<span style="display:block;width:${String(MARKER_PX)}px;height:${String(MARKER_PX)}px;background:#fffdf8;border:3px solid ${aqiColour(reading.raw_aqi)};box-shadow:0 0 0 1px rgba(28,27,23,.35)"></span>`,
          })}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{reading.sensor_model}</p>
              <p className="mt-0.5 text-xs font-medium text-warn">
                Resident’s sensor · as reported
              </p>
              <p className="figure mt-1">{reading.value_ugm3.toFixed(0)} µg/m³</p>
              <p className="mt-1 text-xs text-ink-subtle">
                {reading.reference_station_name && reading.reference_value !== null
                  ? `${reading.reference_station_name} read ${reading.reference_value.toFixed(0)} µg/m³ nearby at the time.`
                  : 'No reference monitor was in range to compare with.'}{' '}
                Submitted {timeAgo(reading.observed_at)}. Not used in any estimate.
              </p>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}
