import { CircleMarker, Popup } from 'react-leaflet';

import type { Hotspot } from '@/hooks/useAnalysis';
import { hotspotRadius } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';

interface HotspotMarkersProps {
  readonly hotspots: readonly Hotspot[];
  readonly onSelect?: (hotspot: Hotspot) => void;
}

/**
 * Detected hotspots, sized by how far above their neighbourhood they sat.
 *
 * Size tracks the standardised excess, not the concentration. A hotspot is a
 * place worse than its surroundings predict, so a citywide bad day produces no
 * large markers -- which is the behaviour that distinguishes this from a
 * threshold alarm.
 */
export function HotspotMarkers({ hotspots, onSelect }: HotspotMarkersProps) {
  return (
    <>
      {hotspots.map((hotspot) => (
        <CircleMarker
          key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`}
          center={toLeaflet([hotspot.position.longitude, hotspot.position.latitude])}
          radius={hotspotRadius(hotspot.peak_z)}
          pathOptions={{
            color: '#d1495b',
            weight: 2,
            fillColor: '#d1495b',
            fillOpacity: 0.2,
          }}
          eventHandlers={
            onSelect
              ? {
                  click: () => {
                    onSelect(hotspot);
                  },
                }
              : {}
          }
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{hotspot.station_name}</p>
              <p className="mt-1">
                {hotspot.peak_observed.toFixed(0)} µg/m³ against a neighbourhood at{' '}
                {hotspot.peak_expected.toFixed(0)}
              </p>
              <p className="mt-1 text-xs text-neutral-600">
                excess {hotspot.peak_excess.toFixed(0)} µg/m³ · {hotspot.peak_z.toFixed(1)}× the
                expected error · {hotspot.intervals}h
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
