import { describe, expect, it } from 'vitest';

import {
  distanceM,
  fromLeaflet,
  isWithinIndia,
  polygonToLeaflet,
  ringToLeaflet,
  toLeaflet,
  type LonLat,
} from './geo';

/** API order: [longitude, latitude]. */
const DELHI: LonLat = [77.209, 28.6139];
const COIMBATORE: LonLat = [76.9558, 11.0168];

describe('coordinate order', () => {
  it('flips API order to Leaflet order', () => {
    expect(toLeaflet(DELHI)).toEqual([28.6139, 77.209]);
  });

  it('flips Leaflet order back to API order', () => {
    expect(fromLeaflet([28.6139, 77.209])).toEqual([77.209, 28.6139]);
  });

  it('round-trips without drift', () => {
    expect(fromLeaflet(toLeaflet(COIMBATORE))).toEqual(COIMBATORE);
  });

  it('converts a ring', () => {
    expect(ringToLeaflet([DELHI, COIMBATORE])).toEqual([
      [28.6139, 77.209],
      [11.0168, 76.9558],
    ]);
  });

  it('converts every ring of a polygon', () => {
    const polygon = polygonToLeaflet([[DELHI, COIMBATORE, DELHI]]);
    expect(polygon).toHaveLength(1);
    expect(polygon[0]).toHaveLength(3);
    expect(polygon[0]?.[0]).toEqual([28.6139, 77.209]);
  });
});

describe('distanceM', () => {
  it('is zero from a point to itself', () => {
    expect(distanceM(COIMBATORE, COIMBATORE)).toBe(0);
  });

  it('measures Delhi to Coimbatore at about 1,960 km', () => {
    // The published great-circle distance is ~1,960 km; a swapped coordinate
    // pair would put it thousands of kilometres out.
    expect(distanceM(DELHI, COIMBATORE) / 1000).toBeCloseTo(1960, -2);
  });

  it('is symmetric', () => {
    expect(distanceM(DELHI, COIMBATORE)).toBeCloseTo(distanceM(COIMBATORE, DELHI), 6);
  });
});

describe('isWithinIndia', () => {
  it('accepts Indian cities', () => {
    expect(isWithinIndia(DELHI)).toBe(true);
    expect(isWithinIndia(COIMBATORE)).toBe(true);
  });

  it('rejects a transposed coordinate', () => {
    // Delhi with its pair swapped is a legal WGS84 position, so only a regional
    // bound catches it. Without this check it would render silently in the wrong
    // hemisphere of the map.
    expect(isWithinIndia([28.6139, 77.209])).toBe(false);
  });

  it('rejects a coordinate in another country', () => {
    expect(isWithinIndia([-0.1276, 51.5072])).toBe(false);
  });
});
