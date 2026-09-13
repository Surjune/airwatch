import type { components } from '@/lib/api-types';

export type ComplaintCategory = components['schemas']['ComplaintCategory'];

/** Longest description the API accepts, matching COMPLAINT_DESCRIPTION_MAX_LENGTH. */
export const DESCRIPTION_MAX_LENGTH = 500;

/**
 * What a resident can say they saw, worded as the office reading the complaint
 * would recognise it. The same categories the PDF report prints.
 */
export const COMPLAINT_CATEGORIES = [
  { key: 'open_burning', label: 'Burning waste' },
  { key: 'industrial_smoke', label: 'Industrial smoke' },
  { key: 'construction_dust', label: 'Construction dust' },
  { key: 'vehicle_exhaust', label: 'Vehicle exhaust' },
  { key: 'crop_residue_burning', label: 'Crop burning' },
  { key: 'road_dust', label: 'Road dust' },
  { key: 'other', label: 'Something else' },
] as const satisfies readonly { key: ComplaintCategory; label: string }[];

export function categoryLabel(category: ComplaintCategory | null | undefined): string {
  return COMPLAINT_CATEGORIES.find((option) => option.key === category)?.label ?? 'Not stated';
}

/**
 * Hand a downloaded file to the browser as a save.
 *
 * An object URL on a temporary link, revoked straight after, so the PDF is never
 * given a shareable address and does not linger in memory.
 */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
