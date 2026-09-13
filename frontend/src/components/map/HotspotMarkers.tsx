import { CircleMarker, Popup } from 'react-leaflet';

import type { Hotspot } from '@/hooks/useAnalysis';
import { hotspotRadius } from '@/lib/aqi';
import { toLeaflet } from '@/lib/geo';

/** The signal colour from the design tokens, as Leaflet needs a literal. */
const SIGNAL = '#c24a1c';

/**
 * Detected hotspots, sized by how far above their neighbourhood they sat.
 *
 * Size tracks the standardised excess, not the concentration. A hotspot is a
 * place worse than its surroundings predict, so a citywide bad day produces no
 * large rings -- which is what distinguishes this from a threshold alarm.
 */
export function HotspotMarkers({ hotspots }: { readonly hotspots: readonly Hotspot[] }) {
  return (
    <>
      {hotspots.map((hotspot) => (
        <CircleMarker
          key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`}
          center={toLeaflet([hotspot.position.longitude, hotspot.position.latitude])}
          radius={hotspotRadius(hotspot.peak_z)}
          pathOptions={{ color: SIGNAL, weight: 2.5, fillColor: SIGNAL, fillOpacity: 0.12 }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-medium">{hotspot.station_name}</p>
              <p className="figure mt-1">
                {hotspot.peak_observed.toFixed(0)} µg/m³ vs {hotspot.peak_expected.toFixed(0)}{' '}
                predicted
              </p>
              <p className="mt-1 text-xs text-ink-muted">
                excess {hotspot.peak_excess.toFixed(0)} µg/m³ · {hotspot.peak_z.toFixed(1)}× the
                expected error · {hotspot.intervals} h
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
