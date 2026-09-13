import { Polygon, Tooltip } from 'react-leaflet';

import type { Satellite, SatelliteProduct } from '@/hooks/useSources';
import { toLeaflet } from '@/lib/geo';
import { formatColumn } from '@/lib/satellite';

/** Lowest and highest fill opacity, so the least loaded cell still reads as observed. */
const MIN_OPACITY = 0.08;
const MAX_OPACITY = 0.55;

/** One hue, the interaction accent, well away from every CPCB band colour. */
const SATELLITE_HUE = '#28457a';

interface SatelliteLayerProps {
  readonly cells: Satellite['cells'];
  readonly product: SatelliteProduct;
}

/**
 * Each coarse satellite cell's latest value, shaded relative to the others.
 *
 * Shaded by rank within the city rather than on the AQI scale, in a single hue
 * distinct from the CPCB bands: a column density is not a ground concentration,
 * and borrowing the AQI colours would invite reading it as one. Cells with no
 * observation are simply not drawn.
 */
export function SatelliteLayer({ cells, product }: SatelliteLayerProps) {
  const values = cells.map((cell) => cell.value);
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;

  return (
    <>
      {cells.map((cell) => {
        const share = (cell.value - low) / span;
        return (
          <Polygon
            key={cell.h3_cell}
            positions={cell.boundary.map((vertex) =>
              toLeaflet([vertex.longitude, vertex.latitude]),
            )}
            pathOptions={{
              color: SATELLITE_HUE,
              weight: 0.5,
              opacity: 0.35,
              fillColor: SATELLITE_HUE,
              fillOpacity: MIN_OPACITY + share * (MAX_OPACITY - MIN_OPACITY),
            }}
          >
            <Tooltip sticky>
              {formatColumn(product, cell.value)} · {cell.observed_on} · {cell.pixel_count} pixels
            </Tooltip>
          </Polygon>
        );
      })}
    </>
  );
}
