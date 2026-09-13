import type { CityKey } from '@/lib/scope';

export interface Corridor {
  readonly key: string;
  readonly name: string;
  readonly note: string;
  /** `lon,lat` vertices separated by `;`. */
  readonly points: string;
}

/**
 * Economic corridors worth forecasting in each city, as `lon,lat` polylines.
 *
 * Chosen because pollution follows these rather than administrative lines:
 * freight moves along them, industry clusters beside them, and a person
 * commuting one of them accumulates most of their daily dose on it. Vertices are
 * approximate waypoints along each road, not a surveyed centreline.
 */
export const CORRIDORS: Record<CityKey, readonly Corridor[]> = {
  delhi: [
    {
      key: 'dwarka-anand-vihar',
      name: 'Dwarka → Anand Vihar',
      note: 'West to east across Delhi, ending at the bus terminal and rail yard.',
      points: '77.03,28.59;77.21,28.61;77.32,28.65',
    },
    {
      key: 'nh48',
      name: 'NH-48 industrial belt',
      note: 'Delhi south-west into the Gurugram manufacturing corridor.',
      points: '77.21,28.61;77.10,28.50;77.03,28.42',
    },
    {
      key: 'ghaziabad',
      name: 'Delhi → Ghaziabad',
      note: 'Eastward into the Indo-Gangetic industrial belt.',
      points: '77.21,28.63;77.32,28.66;77.45,28.67',
    },
  ],
  kanpur: [
    {
      key: 'gt-road',
      name: 'Panki → Jajmau (GT Road)',
      note: 'Across the city from the Panki power station to the Jajmau tannery cluster.',
      points: '80.27,26.47;80.33,26.45;80.40,26.43',
    },
  ],
  coimbatore: [
    {
      key: 'trichy-road-sidco',
      name: 'Ukkadam → SIDCO Kurichi',
      note: 'South from Ukkadam past the Kurichi industrial estate, ending at the city’s reporting monitor.',
      points: '76.961,10.989;76.970,10.960;76.979,10.942',
    },
    {
      key: 'avinashi-road',
      name: 'Gandhipuram → Airport',
      note: 'East along Avinashi Road through Peelamedu to the airport.',
      points: '76.963,11.017;77.001,11.026;77.043,11.030',
    },
    {
      key: 'mettupalayam-road',
      name: 'Gandhipuram → Thudiyalur',
      note: 'North-west along Mettupalayam Road through Saibaba Colony.',
      points: '76.963,11.017;76.943,11.030;76.940,11.080',
    },
  ],
};

/** Horizons the forecast was validated at, in hours. */
export const HORIZONS = [
  { key: '24', label: '24 h' },
  { key: '48', label: '48 h' },
  { key: '72', label: '72 h' },
] as const;

export type HorizonKey = (typeof HORIZONS)[number]['key'];
