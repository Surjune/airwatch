import { CircleMarker, Popup } from 'react-leaflet';

import type { StationReading } from '@/hooks/useAnalysis';
import { aqiColour } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';

interface StationMarkersProps {
  readonly readings: readonly StationReading[];
}

/** Every monitoring station, coloured by its CPCB sub-index. */
export function StationMarkers({ readings }: StationMarkersProps) {
  return (
    <>
      {readings.map((reading) => (
        <CircleMarker
          key={reading.station_id}
          center={toLeaflet([reading.position.longitude, reading.position.latitude])}
          radius={6}
          pathOptions={{
            color: '#ffffff',
            weight: 1,
            fillColor: aqiColour(reading.aqi),
            fillOpacity: 0.9,
          }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{reading.name}</p>
              <p className="mt-1">
                {reading.value.toFixed(0)} {reading.unit} · AQI {reading.aqi.toFixed(0)} (
                {reading.category})
              </p>
              <p className="mt-1 text-xs text-ink-subtle">
                {new Date(reading.observed_at).toLocaleString()}
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
