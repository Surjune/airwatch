import { Headphones, X } from 'lucide-react';

import { GUIDE_LANGUAGES, type GuideLanguage } from '@/lib/guide';

/** The invitation in each language, written for someone who reads only that one. */
const INVITATIONS: Readonly<Record<GuideLanguage, string>> = {
  en: 'Listen in English',
  hi: 'हिन्दी में सुनें',
  ta: 'தமிழில் கேளுங்கள்',
};

interface GuideIntroProps {
  readonly onChoose: (language: GuideLanguage) => void;
  readonly onDismiss: () => void;
}

/**
 * A one-time offer of the spoken guide, on a first visit.
 *
 * Each language offers itself in its own script, so a Tamil reader who cannot
 * read the English sentence above still recognises the button meant for them,
 * and one press both chooses the language and starts the guide.
 */
export function GuideIntro({ onChoose, onDismiss }: GuideIntroProps) {
  return (
    <div
      role="region"
      aria-label="Voice guide"
      className="absolute right-3 top-full z-[1150] mt-2 w-[min(20rem,calc(100vw-1.5rem))] rounded-card border border-border bg-surface p-4 shadow-overlay sm:right-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow">New here</p>
          <p className="mt-1 text-[14px] font-semibold leading-snug text-ink">
            Hear how each page works, read aloud.
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Not now"
          className="-mr-1 -mt-1 flex size-8 shrink-0 items-center justify-center rounded-sm text-ink-subtle hover:bg-surface-sunken hover:text-ink"
        >
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <ul className="mt-3 grid gap-2">
        {GUIDE_LANGUAGES.map((option) => (
          <li key={option.key}>
            <button
              type="button"
              lang={option.key}
              onClick={() => {
                onChoose(option.key);
              }}
              className="flex min-h-10 w-full items-center gap-2 rounded-[4px] border border-border-strong px-3 text-left text-sm font-medium text-ink hover:border-ink/40 hover:bg-paper"
            >
              <Headphones aria-hidden className="size-3.5 shrink-0 text-signal" />
              {INVITATIONS[option.key]}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
