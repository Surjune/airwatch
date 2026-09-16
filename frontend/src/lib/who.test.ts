import { describe, expect, it } from 'vitest';

import { formatMultiple, whoLabel, whoSentence } from './who';

describe('formatMultiple', () => {
  it('keeps one decimal for a small multiple', () => {
    expect(formatMultiple(3.24)).toBe('3.2×');
  });

  it('drops the decimal once the multiple is large', () => {
    expect(formatMultiple(12.4)).toBe('12×');
  });

  it('does not print 10.0× for a multiple that rounds up to ten', () => {
    expect(formatMultiple(9.96)).toBe('10×');
  });
});

describe('whoLabel', () => {
  it('says how many times the guideline a dirty day was', () => {
    expect(whoLabel(3.2)).toBe('24 h avg 3.2× WHO');
  });

  it('says a day within the guideline was within it', () => {
    expect(whoLabel(0.8)).toBe('24 h avg within WHO');
  });

  it('counts a day exactly at the guideline as not within it', () => {
    expect(whoLabel(1)).toBe('24 h avg 1.0× WHO');
  });
});

describe('whoSentence', () => {
  it('names the average, the multiple and the guideline', () => {
    expect(whoSentence(48, 3.2, 15, 'µg/m³')).toBe(
      "Average over the last 24 hours: 48 µg/m³, 3.2× WHO's 24-hour guideline of 15 µg/m³.",
    );
  });

  it('says a clean day was within the guideline', () => {
    expect(whoSentence(12, 0.8, 15, 'µg/m³')).toBe(
      "Average over the last 24 hours: 12 µg/m³, within WHO's 24-hour guideline of 15 µg/m³.",
    );
  });
});
