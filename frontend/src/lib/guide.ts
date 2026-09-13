import type { components } from '@/lib/api-types';

export type GuideLanguage = components['schemas']['GuideLanguage'];
export type Guide = components['schemas']['GuideResponse'];
export type GuideSection = components['schemas']['GuideSectionResponse'];

export interface GuideLanguageOption {
  readonly key: GuideLanguage;
  /** The language's name in its own script, which is what its speaker looks for. */
  readonly label: string;
  /** The English name, for assistive technology reading an English interface. */
  readonly englishName: string;
}

/** The languages the spoken guide is written in. */
export const GUIDE_LANGUAGES: readonly GuideLanguageOption[] = [
  { key: 'en', label: 'English', englishName: 'English' },
  { key: 'hi', label: 'हिन्दी', englishName: 'Hindi' },
  { key: 'ta', label: 'தமிழ்', englishName: 'Tamil' },
];

const LANGUAGE_STORAGE_KEY = 'airwatch.guide-language';
const INTRO_STORAGE_KEY = 'airwatch.guide-intro-seen';

function isGuideLanguage(value: string | null): value is GuideLanguage {
  return GUIDE_LANGUAGES.some((option) => option.key === value);
}

/**
 * The language to open the guide in.
 *
 * A choice made here before wins. Otherwise the browser's own languages are
 * asked, so a phone set to Tamil opens the guide in Tamil without anyone having
 * to find the switch in a language they may not read.
 */
export function preferredGuideLanguage(
  browserLanguages: readonly string[] = navigator.languages,
): GuideLanguage {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isGuideLanguage(stored)) return stored;
  } catch {
    // Storage blocked; fall through to the browser's languages.
  }
  for (const tag of browserLanguages) {
    const primary = tag.split('-')[0]?.toLowerCase() ?? null;
    if (isGuideLanguage(primary)) return primary;
  }
  return 'en';
}

export function rememberGuideLanguage(language: GuideLanguage): void {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Not remembered; the choice still holds for this visit.
  }
}

/** Whether this browser has already been offered the guide once. */
export function guideIntroSeen(): boolean {
  try {
    return localStorage.getItem(INTRO_STORAGE_KEY) !== null;
  } catch {
    // Without storage the offer would reappear on every screen, so treat it as seen.
    return true;
  }
}

export function markGuideIntroSeen(): void {
  try {
    localStorage.setItem(INTRO_STORAGE_KEY, '1');
  } catch {
    // Nothing to do; see guideIntroSeen.
  }
}
