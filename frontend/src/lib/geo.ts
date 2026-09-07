/**
 * Coordinate-order boundary between the API and Leaflet.
 *
 * The API, GeoJSON and PostGIS all use `[longitude, latitude]`. Leaflet uses
 * `[latitude, longitude]`. Every flip between the two happens in this file and
 * nowhere else — an ad-hoc swap inside a component is the bug that puts Delhi
 * in the Indian Ocean, and it is invisible until someone looks at the map.
 */

/** A position as the API delivers it: `[longitude, latitude]`. */
export type LonLat = readonly [number, number];

/** A position as Leaflet expects it: `[latitude, longitude]`. */
export type LatLng = readonly [number, number];

/** Convert an API position to a Leaflet position. */
export function toLeaflet([lon, lat]: LonLat): LatLng {
  return [lat, lon];
}

/** Convert a Leaflet position back to the API's order. */
export function fromLeaflet([lat, lon]: LatLng): LonLat {
  return [lon, lat];
}

/** Convert a ring of API positions to Leaflet order, for polygons and lines. */
export function ringToLeaflet(ring: readonly LonLat[]): LatLng[] {
  return ring.map(toLeaflet);
}

/**
 * Convert a GeoJSON Polygon's coordinates to Leaflet order.
 *
 * @param coordinates - Polygon rings, outer ring first, each in `[lon, lat]`.
 */
export function polygonToLeaflet(coordinates: readonly (readonly LonLat[])[]): LatLng[][] {
  return coordinates.map(ringToLeaflet);
}

/** Longitude and latitude bounds of mainland India plus its island territories. */
const INDIA_BOUNDS = {
  minLon: 68.0,
  maxLon: 97.5,
  minLat: 6.0,
  maxLat: 37.5,
} as const;

/**
 * Whether a position falls inside India's bounding box.
 *
 * A cheap guard for spotting a swapped pair before it reaches the map: Indian
 * longitudes (68–97.5) are outside the valid latitude range entirely, so a
 * transposed coordinate fails this check rather than rendering somewhere
 * plausible-looking.
 */
export function isWithinIndia([lon, lat]: LonLat): boolean {
  return (
    lon >= INDIA_BOUNDS.minLon &&
    lon <= INDIA_BOUNDS.maxLon &&
    lat >= INDIA_BOUNDS.minLat &&
    lat <= INDIA_BOUNDS.maxLat
  );
}
