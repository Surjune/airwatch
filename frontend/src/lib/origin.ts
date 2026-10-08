import type { components } from '@/lib/api-types';

/** Which relay a monitor reading came through. */
export type MeasurementOrigin = components['schemas']['MeasurementOrigin'];

/** True for a reading the backup feed supplied while OpenAQ was silent. */
export function isBackup(origin: MeasurementOrigin): boolean {
  return origin === 'waqi';
}

/** Where AirWatch read one of CPCB's official sub-indices. */
export type OfficialRelay = components['schemas']['OfficialRelay'];

/** How the official card names where CPCB's figure was read. */
export function officialRelayLabel(relay: OfficialRelay): string {
  return relay === 'tnpcb' ? 'via TNPCB' : 'data.gov.in';
}

/** The short tag shown beside a backup reading. */
export const BACKUP_TAG = 'via aqicn.org';

/**
 * The attribution WAQI's terms require, and what the conversion means.
 *
 * Shown wherever a backup reading is, because a figure converted from the US
 * AQI is approximate and must never pass for one CPCB published as it stands.
 */
export const BACKUP_NOTE =
  'Readings marked “via aqicn.org” come from CPCB’s monitors through the World Air Quality Index Project, while OpenAQ is not relaying them. They are converted from the US AQI back to µg/m³, so they are approximate, and are replaced by CPCB’s own figures once OpenAQ resumes.';
