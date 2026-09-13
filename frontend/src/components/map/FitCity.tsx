import { latLng } from 'leaflet';
import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

import { toLeaflet, type LonLat } from '@/lib/geo';

interface FitCityProps {
  /** City centre, as (lon, lat). */
  readonly centre: LonLat;
  /** Radius of the city's view, in metres. */
  readonly radiusM: number;
}

/**
 * Frame the map on a city whenever the city changes.
 *
 * `MapContainer` only reads its centre on first render, so switching city would
 * otherwise leave the map looking at the previous one -- Delhi's stations under
 * a header that says Coimbatore.
 */
export function FitCity({ centre, radiusM }: FitCityProps) {
  const map = useMap();
  const [lon, lat] = centre;

  useEffect(() => {
    // A bounds square whose side is the view's diameter, in metres.
    map.fitBounds(latLng(toLeaflet([lon, lat])).toBounds(radiusM * 2), { animate: false });
  }, [map, lon, lat, radiusM]);

  return null;
}
