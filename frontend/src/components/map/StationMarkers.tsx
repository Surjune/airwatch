import { CircleMarker, Popup } from 'react-leaflet';

import type { StationReading } from '@/hooks/useAnalysis';
import { aqiColour } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';
import { istDateTime } from '@/lib/time';

/** Radius of a monitor marker, in pixels: the largest of the non-hotspot marks. */
const MONITOR_RADIUS_PX = 7;

/** Every reference monitor, filled with the colour of its CPCB sub-index band. */
export function StationMarkers({ readings }: { readonly readings: readonly StationReading[] }) {
  return (
    <>
      {readings.map((reading) => (
        <CircleMarker
          key={reading.station_id}
          center={toLeaflet([reading.position.longitude, reading.position.latitude])}
          radius={MONITOR_RADIUS_PX}
          pathOptions={{
            color: '#1c1b17',
            weight: 1.25,
            fillColor: aqiColour(reading.aqi),
            fillOpacity: 0.95,
          }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{reading.name}</p>
              <p className="mt-0.5 text-xs font-medium text-ok">Reference monitor</p>
              <p className="figure mt-1">
                {reading.value.toFixed(0)} {reading.unit} · AQI {reading.aqi.toFixed(0)}
              </p>
              <p className="mt-1 text-xs text-ink-subtle">
                {reading.category} · {istDateTime(reading.observed_at)} IST
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
