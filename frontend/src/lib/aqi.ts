/**
 * CPCB AQI colour scale and banding.
 *
 * The single place a concentration becomes a colour. Duplicating this in a
 * component is how two views of the same reading end up disagreeing.
 */

/** One CPCB band. */
interface Band {
  readonly floor: number;
  readonly name: string;
  readonly colour: string;
}

/** CPCB band lower bounds, matching `core/constants.py`. */
const BANDS: readonly Band[] = [
    { floor: 0, name: 'Good', colour: '#3ba272' },
    { floor: 51, name: 'Satisfactory', colour: '#8bc34a' },
    { floor: 101, name: 'Moderate', colour: '#e2b93b' },
    { floor: 201, name: 'Poor', colour: '#e07b39' },
    { floor: 301, name: 'Very Poor', colour: '#d1495b' },
    { floor: 401, name: 'Severe', colour: '#8b2635' },
  ];

/** The band an AQI value falls in. Defaults to the cleanest, which is band zero. */
function bandFor(aqi: number): Band {
  let match = FALLBACK_BAND;
  for (const band of BANDS) {
    if (aqi >= band.floor) match = band;
  }
  return match;
}

/**
 * Used when a value falls below every band floor, which cannot happen for a
 * non-negative AQI but keeps the lookup total rather than reaching for a
 * non-null assertion on an indexed access.
 */
const FALLBACK_BAND: Band = { floor: 0, name: 'Good', colour: '#3ba272' };

/** Colour for an AQI value. */
export function aqiColour(aqi: number): string {
  return bandFor(aqi).colour;
}

/** Band name for an AQI value. */
export function aqiBand(aqi: number): string {
  return bandFor(aqi).name;
}

/** Every band, for rendering a legend. */
export function aqiBands(): readonly Band[] {
  return BANDS;
}

/**
 * Marker radius for a hotspot's severity.
 *
 * Scaled on the standardised excess rather than the concentration, because a
 * hotspot is defined by how far above its neighbourhood it sits, not by how
 * dirty the whole city happens to be.
 */
export function hotspotRadius(zScore: number): number {
  const MIN = 8;
  const MAX = 26;
  return Math.min(MAX, MIN + zScore * 1.2);
}
