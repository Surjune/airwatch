import { CircleMarker, Popup } from 'react-leaflet';

import type { StationReading } from '@/hooks/useAnalysis';
import { aqiColour } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';
import { timeAgo } from '@/lib/time';

/**
 * Low-cost sensors, drawn so they can never be mistaken for monitors.
 *
 * A hollow ring in the band colour rather than a filled dot: close enough to be
 * read at a glance, visibly different from a reference station, and the popup
 * says in words that the value is uncalibrated.
 */
export function LowCostMarkers({ readings }: { readonly readings: readonly StationReading[] }) {
  return (
    <>
      {readings.map((reading) => (
        <CircleMarker
          key={`sensor-${String(reading.station_id)}`}
          center={toLeaflet([reading.position.longitude, reading.position.latitude])}
          radius={5}
          pathOptions={{
            color: aqiColour(reading.aqi),
            weight: 2.5,
            fillColor: '#ffffff',
            fillOpacity: 0.85,
            dashArray: '2 2',
          }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{reading.name}</p>
              <p className="mt-0.5 text-xs font-medium text-warn">Low-cost sensor · uncalibrated</p>
              <p className="mt-1">
                {reading.value.toFixed(0)} {reading.unit} as reported
              </p>
              <p className="mt-1 text-xs text-ink-subtle">
                Optical sensors read high in humid air. Not used for hotspots or forecasts. Reported{' '}
                {timeAgo(reading.observed_at)}.
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
