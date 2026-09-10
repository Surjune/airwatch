import { MapContainer, TileLayer } from 'react-leaflet';

import { HotspotMarkers } from '@/components/map/HotspotMarkers';
import { StationMarkers } from '@/components/map/StationMarkers';
import type { Hotspot, StationReading } from '@/hooks/useAnalysis';
import { aqiBands } from '@/lib/aqi';
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
        <HotspotMarkers hotspots={hotspots} {...(onSelectHotspot ? { onSelect: onSelectHotspot } : {})} />
      </MapContainer>

      <div className="pointer-events-none absolute bottom-4 left-4 z-[1000] rounded bg-white/95 p-3 text-xs shadow">
        <p className="mb-2 font-medium">CPCB band</p>
        {aqiBands().map((band) => (
          <div key={band.name} className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: band.colour }}
            />
            <span>{band.name}</span>
          </div>
        ))}
        <p className="mt-2 max-w-[13rem] border-t border-neutral-200 pt-2 text-neutral-600">
          Rings mark places dirtier than their neighbourhood predicts, sized by excess — not by how
          dirty the city is.
        </p>
      </div>
    </div>
  );
}
