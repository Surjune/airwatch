import { Headphones } from 'lucide-react';
import { useCallback, useRef, useState } from 'react';

import { GuideIntro } from '@/components/guide/GuideIntro';
import { GuidePanel } from '@/components/guide/GuidePanel';
import type { Screen } from '@/components/layout/navigation';
import {
  guideIntroSeen,
  markGuideIntroSeen,
  preferredGuideLanguage,
  rememberGuideLanguage,
  type GuideLanguage,
} from '@/lib/guide';

/**
 * The masthead's "Listen" control, and the spoken guide it opens.
 *
 * On every screen, because every screen is someone's first: a resident arriving
 * from a link to the contribution form needs the explanation there, not on an
 * overview they never saw.
 */
export function VoiceGuide({ screen }: { readonly screen: Screen }) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [language, setLanguage] = useState<GuideLanguage>(() => preferredGuideLanguage());
  const [showIntro, setShowIntro] = useState(() => !guideIntroSeen());

  const chooseLanguage = useCallback((next: GuideLanguage) => {
    setLanguage(next);
    rememberGuideLanguage(next);
  }, []);

  const open = useCallback(() => {
    markGuideIntroSeen();
    setShowIntro(false);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    buttonRef.current?.focus();
  }, []);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={isOpen}
        aria-label="Listen to a guide to this page"
        onClick={isOpen ? close : open}
        className={`inline-flex min-h-8 items-center gap-1.5 rounded-[4px] border px-2 text-[13px] font-medium transition-colors sm:px-2.5 ${
          isOpen
            ? 'border-ink bg-ink text-paper'
            : 'border-border-strong bg-surface text-ink hover:border-ink/40'
        }`}
      >
        <Headphones aria-hidden className="size-4" />
        <span className="hidden sm:inline">Listen</span>
      </button>

      {showIntro && !isOpen && (
        <GuideIntro
          onChoose={(next) => {
            chooseLanguage(next);
            open();
          }}
          onDismiss={() => {
            markGuideIntroSeen();
            setShowIntro(false);
          }}
        />
      )}

      {isOpen && (
        <GuidePanel
          screen={screen}
          language={language}
          onLanguageChange={chooseLanguage}
          onClose={close}
        />
      )}
    </>
  );
}
