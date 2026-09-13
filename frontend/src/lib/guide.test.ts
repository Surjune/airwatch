import { afterEach, describe, expect, it } from 'vitest';

import {
  guideIntroSeen,
  markGuideIntroSeen,
  preferredGuideLanguage,
  rememberGuideLanguage,
} from './guide';

afterEach(() => {
  localStorage.clear();
});

describe('preferredGuideLanguage', () => {
  it('opens in the language the browser asks for first', () => {
    expect(preferredGuideLanguage(['ta-IN', 'en-GB'])).toBe('ta');
    expect(preferredGuideLanguage(['hi'])).toBe('hi');
  });

  it('skips languages it has no guide in', () => {
    expect(preferredGuideLanguage(['fr-FR', 'hi-IN'])).toBe('hi');
  });

  it('falls back to English', () => {
    expect(preferredGuideLanguage(['de-DE'])).toBe('en');
    expect(preferredGuideLanguage([])).toBe('en');
  });

  it('keeps a choice made here over what the browser says', () => {
    rememberGuideLanguage('ta');
    expect(preferredGuideLanguage(['hi-IN'])).toBe('ta');
  });

  it('ignores a stored value that is not a guide language', () => {
    localStorage.setItem('airwatch.guide-language', 'klingon');
    expect(preferredGuideLanguage(['hi-IN'])).toBe('hi');
  });
});

describe('the first-visit offer', () => {
  it('is made once', () => {
    expect(guideIntroSeen()).toBe(false);
    markGuideIntroSeen();
    expect(guideIntroSeen()).toBe(true);
  });
});
