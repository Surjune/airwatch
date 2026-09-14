import type { components } from '@/lib/api-types';

export type PhotoReading = components['schemas']['PhotoReadingResponse'];
export type VisibleSource = components['schemas']['VisibleSource'];

/** How each of Gemini's readings is named to a resident, matching the PDF report. */
const LABELS: Readonly<Record<VisibleSource, string>> = {
  open_burning: 'Open burning of waste',
  industrial_smoke: 'Smoke or fumes from an industrial unit',
  construction_dust: 'Dust from construction or demolition',
  vehicle_exhaust: 'Vehicle exhaust',
  crop_residue_burning: 'Burning of crop residue',
  road_dust: 'Road dust',
  haze_without_visible_source: 'Haze, with no source visible in the frame',
  none_visible: 'No visible pollution',
  not_outdoor: 'Not a photograph of outdoor air',
};

export function visibleSourceLabel(source: VisibleSource): string {
  return LABELS[source];
}

/** Whether Gemini named something emitting, rather than haze, clear air or no scene at all. */
export function namesASource(source: VisibleSource): boolean {
  return !['haze_without_visible_source', 'none_visible', 'not_outdoor'].includes(source);
}

/** Gemini's own confidence, as a whole percentage. */
export function confidencePercent(reading: PhotoReading): string {
  return `${String(Math.round(reading.confidence * 100))}%`;
}
