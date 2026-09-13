import type { components } from '@/lib/api-types';

type SatelliteProduct = components['schemas']['SatelliteProduct'];

/** Micromoles in a mole, for presenting column densities at a readable scale. */
const MICROMOL_PER_MOL = 1_000_000;

/** The products a view can switch between, with how each is described. */
export const SATELLITE_PRODUCTS = [
  {
    key: 'no2',
    label: 'NO₂',
    description: 'Tropospheric nitrogen dioxide — traffic and combustion',
  },
  {
    key: 'aerosol_index',
    label: 'Aerosol',
    description: 'Absorbing aerosol index — smoke and dust',
  },
  { key: 'co', label: 'CO', description: 'Carbon monoxide column — burning' },
  { key: 'so2', label: 'SO₂', description: 'Sulphur dioxide column — coal and smelting' },
] as const satisfies readonly { key: SatelliteProduct; label: string; description: string }[];

/**
 * Present a stored satellite value.
 *
 * Column densities are stored in mol/m² as delivered; they are shown in µmol/m²
 * only here, at the presentation boundary, because 0.0000207 is unreadable. The
 * aerosol index is dimensionless and shown as is.
 */
export function formatColumn(product: SatelliteProduct, value: number): string {
  if (product === 'aerosol_index') return value.toFixed(2);
  // mol/m² -> µmol/m²
  return `${(value * MICROMOL_PER_MOL).toFixed(1)} µmol/m²`;
}
