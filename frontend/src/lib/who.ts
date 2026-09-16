/**
 * Wording for how a monitor's day compares with WHO's 2021 guideline.
 *
 * The API states the multiple only for a full day's average set against WHO's
 * 24-hour level, so nothing here compares an hourly reading with a daily
 * guideline; this only puts the figure into words.
 */

/** From this multiple up, a decimal adds nothing: "12×", not "12.4×". */
const WHOLE_FROM = 10;

/** How many times WHO's guideline a figure is: "3.2×", or "12×" once it is large. */
export function formatMultiple(multiple: number): string {
  const tenths = Math.round(multiple * 10) / 10;
  return tenths >= WHOLE_FROM ? `${String(Math.round(multiple))}×` : `${tenths.toFixed(1)}×`;
}

/** Whether a day's average stayed within WHO's 24-hour guideline. */
export function withinGuideline(multiple: number): boolean {
  return multiple < 1;
}

/** The short label shown beside a reading. */
export function whoLabel(multiple: number): string {
  return withinGuideline(multiple)
    ? '24 h avg within WHO'
    : `24 h avg ${formatMultiple(multiple)} WHO`;
}

/** The full sentence behind the label. */
export function whoSentence(
  dailyMean: number,
  multiple: number,
  guideline: number,
  unit: string,
): string {
  const average = `Average over the last 24 hours: ${dailyMean.toFixed(0)} ${unit}`;
  const level = `WHO's 24-hour guideline of ${String(guideline)} ${unit}`;
  return withinGuideline(multiple)
    ? `${average}, within ${level}.`
    : `${average}, ${formatMultiple(multiple)} ${level}.`;
}
