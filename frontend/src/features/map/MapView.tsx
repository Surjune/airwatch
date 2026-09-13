import { MapContainer, TileLayer, ZoomControl } from 'react-leaflet';

import { FitCity } from '@/components/map/FitCity';
import { HotspotMarkers } from '@/components/map/HotspotMarkers';
import { LowCostMarkers } from '@/components/map/LowCostMarkers';
import { ResidentReadingMarkers } from '@/components/map/ResidentReadingMarkers';
import { SatelliteLayer } from '@/components/map/SatelliteLayer';
import { StationMarkers } from '@/components/map/StationMarkers';
import { Legend } from '@/components/ui/Legend';
import type { Hotspot, StationReading } from '@/hooks/useAnalysis';
import type { SensorReading } from '@/hooks/useCitizenSensors';
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
  /** Uncalibrated community network sensors, drawn apart from the monitors. */
  readonly sensors: readonly StationReading[];
  /** Readings residents submitted from their own sensors. */
  readonly residents: readonly SensorReading[];
  /** Satellite cells to draw, when that layer is on. */
  readonly satellite: {
    readonly cells: Satellite['cells'];
    readonly product: SatelliteProduct;
  } | null;
}

/**
 * The live map: monitors coloured by index, hotspots ringed by excess, and the
 * less certain tiers drawn in shapes that cannot be confused with a monitor.
 */
export function MapView({
  readings,
  hotspots,
  centre,
  radiusM,
  pollutantLabel,
  sensors,
  residents,
  satellite,
}: MapViewProps) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={toLeaflet(centre)}
        zoom={DEFAULT_ZOOM}
        className="h-full w-full"
        scrollWheelZoom
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="topright" />
        <FitCity centre={centre} radiusM={radiusM} />
        {satellite && <SatelliteLayer cells={satellite.cells} product={satellite.product} />}
        <LowCostMarkers readings={sensors} />
        <ResidentReadingMarkers readings={residents} />
        <StationMarkers readings={readings} />
        <HotspotMarkers hotspots={hotspots} />
      </MapContainer>

      {/* Above Leaflet's panes. At the top on a phone, where the hotspot sheet
          occupies the bottom; at the bottom on a desktop, clear of the zoom. */}
      <div className="pointer-events-none absolute left-2 top-2 z-[1000] w-56 rounded-card border border-border bg-surface/95 px-3 py-2.5 shadow-raised backdrop-blur sm:w-72 lg:bottom-4 lg:left-4 lg:top-auto lg:w-80">
        <Legend pollutantLabel={pollutantLabel} />
        <ul className="mt-2 hidden space-y-1 border-t border-border pt-2 text-[11px] leading-snug text-ink-muted sm:block">
          <li className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-full bg-band-good ring-1 ring-surface" />
            Reference monitor, filled by band
          </li>
          <li className="flex items-center gap-2">
            <span
              aria-hidden
              className="size-2.5 rounded-full border-2 border-dashed border-ink-muted"
            />
            Community sensor, uncalibrated
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 border-2 border-ink-muted" />
            Resident’s sensor, as reported
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden className="size-3 rounded-full border-2 border-signal" />
            Hotspot, sized by excess over neighbours
          </li>
        </ul>
      </div>
    </div>
  );
}
