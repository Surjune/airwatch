import { MapContainer, TileLayer } from 'react-leaflet';

import { HotspotMarkers } from '@/components/map/HotspotMarkers';
import { StationMarkers } from '@/components/map/StationMarkers';
import type { Hotspot, StationReading } from '@/hooks/useAnalysis';
import { Legend } from '@/components/ui/Legend';
import { toLeaflet, type LonLat } from '@/lib/geo';

/** Delhi, as (lon, lat). Converted once, at this boundary. */
const DELHI: LonLat = [77.209, 28.6139];
const DEFAULT_ZOOM = 10;

interface MapViewProps {
  readonly readings: readonly StationReading[];
  readonly hotspots: readonly Hotspot[];
  readonly onSelectHotspot?: (hotspot: Hotspot) => void;
}

/** The live map: stations coloured by index, hotspots ringed by excess. */
export function MapView({ readings, hotspots, onSelectHotspot }: MapViewProps) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={toLeaflet(DELHI)}
        zoom={DEFAULT_ZOOM}
        className="h-full w-full"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <StationMarkers readings={readings} />
        <HotspotMarkers
          hotspots={hotspots}
          {...(onSelectHotspot ? { onSelect: onSelectHotspot } : {})}
        />
      </MapContainer>

      {/* Above Leaflet's panes, so it stays readable over any tile. On a phone only the
          colour scale is shown: the ring explanation is already in the header strap, and
          repeating it here would cover half the map. */}
      <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] max-w-[calc(100%-1.5rem)] rounded-card border border-border bg-surface/95 px-3.5 py-3 shadow-overlay backdrop-blur sm:max-w-sm">
        <Legend />
        <p className="mt-2 hidden border-t border-border pt-2 text-xs leading-relaxed text-ink-muted sm:block">
          Rings mark places dirtier than their neighbourhood predicts, sized by excess — not by how
          dirty the city is.
        </p>
      </div>
    </div>
  );
}
