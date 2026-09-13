import { MapContainer, TileLayer } from 'react-leaflet';

import { FitCity } from '@/components/map/FitCity';
import { HotspotMarkers } from '@/components/map/HotspotMarkers';
import { LowCostMarkers } from '@/components/map/LowCostMarkers';
import { SatelliteLayer } from '@/components/map/SatelliteLayer';
import { StationMarkers } from '@/components/map/StationMarkers';
import { Legend } from '@/components/ui/Legend';
import type { Hotspot, StationReading } from '@/hooks/useAnalysis';
import type { Satellite, SatelliteProduct } from '@/hooks/useSources';
import { toLeaflet, type LonLat } from '@/lib/geo';

const DEFAULT_ZOOM = 10;

interface MapViewProps {
  readonly readings: readonly StationReading[];
  readonly hotspots: readonly Hotspot[];
  /** Centre of the city in view, as (lon, lat). */
  readonly centre: LonLat;
  /** Radius of the city's view, in metres. */
  readonly radiusM: number;
  readonly pollutantLabel: string;
  /** Uncalibrated low-cost sensors, drawn apart from the monitors. */
  readonly sensors: readonly StationReading[];
  /** Satellite cells to draw, when that layer is on. */
  readonly satellite: {
    readonly cells: Satellite['cells'];
    readonly product: SatelliteProduct;
  } | null;
  readonly onSelectHotspot?: (hotspot: Hotspot) => void;
}

/** The live map: stations coloured by index, hotspots ringed by excess. */
export function MapView({
  readings,
  hotspots,
  centre,
  radiusM,
  pollutantLabel,
  sensors,
  satellite,
  onSelectHotspot,
}: MapViewProps) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={toLeaflet(centre)}
        zoom={DEFAULT_ZOOM}
        className="h-full w-full"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitCity centre={centre} radiusM={radiusM} />
        {satellite && <SatelliteLayer cells={satellite.cells} product={satellite.product} />}
        <LowCostMarkers readings={sensors} />
        <StationMarkers readings={readings} />
        <HotspotMarkers
          hotspots={hotspots}
          {...(onSelectHotspot ? { onSelect: onSelectHotspot } : {})}
        />
      </MapContainer>

      {/* Above Leaflet's panes, so it stays readable over any tile. On a phone only the
          colour scale is shown, so the legend does not cover half the map. */}
      <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] max-w-[calc(100%-1.5rem)] rounded-card border border-border bg-surface/95 px-3.5 py-3 shadow-overlay backdrop-blur sm:max-w-sm">
        <Legend pollutantLabel={pollutantLabel} />
        <p className="mt-2 hidden border-t border-border pt-2 text-xs leading-relaxed text-ink-muted sm:block">
          Rings mark places dirtier than their neighbourhood predicts, sized by excess — not by how
          dirty the city is. Dashed hollow dots are uncalibrated low-cost sensors.
          {satellite && ' Purple cells are the Sentinel-5P column, shaded relative to each other.'}
        </p>
      </div>
    </div>
  );
}
