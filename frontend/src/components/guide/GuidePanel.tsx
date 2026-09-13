import { X } from 'lucide-react';
import { useEffect, useId, useMemo, useRef } from 'react';

import { GuideControls } from '@/components/guide/GuideControls';
import { GuideTranscript } from '@/components/guide/GuideTranscript';
import type { Screen } from '@/components/layout/navigation';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { useGuide } from '@/hooks/useGuide';
import { useGuidePlayer } from '@/hooks/useGuidePlayer';
import { GUIDE_LANGUAGES, type GuideLanguage, type GuideSection } from '@/lib/guide';
import { GUIDE_MESSAGES } from '@/lib/guide-messages';

interface GuidePanelProps {
  readonly screen: Screen;
  readonly language: GuideLanguage;
  readonly onLanguageChange: (language: GuideLanguage) => void;
  readonly onClose: () => void;
}

const NO_SECTIONS: readonly GuideSection[] = [];

/**
 * The spoken guide to the open screen.
 *
 * Not a modal. The guide describes the page behind it, so the page stays visible
 * and usable while it plays: beside it on a desktop, above the screen tabs on a
 * phone. Changing screen while it is open loads that screen's guide.
 */
export function GuidePanel({ screen, language, onLanguageChange, onClose }: GuidePanelProps) {
  const titleId = useId();
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const messages = GUIDE_MESSAGES[language];
  const guide = useGuide(screen.key, language, true);
  const sections = guide.data?.sections ?? NO_SECTIONS;
  const player = useGuidePlayer(sections);
  const isSpeaking = player.status !== 'idle' && player.status !== 'error';

  const languageOptions = useMemo(
    () => GUIDE_LANGUAGES.map((option) => ({ key: option.key, label: option.label })),
    [],
  );

  // Opening the guide, or choosing its language, is asking to hear it, so it
  // starts once the words arrive. Moving to another screen with it open loads
  // that screen's guide without talking over the page being looked at.
  const startWhenLoaded = useRef(true);
  const { play } = player;
  useEffect(() => {
    if (sections.length === 0 || !startWhenLoaded.current) return;
    startWhenLoaded.current = false;
    // Without a voice there is nothing to start, and trying would report every
    // paragraph as broken when the deployment simply has no key.
    if (guide.data?.voice_available) play(0);
  }, [sections, play, guide.data]);

  const changeLanguage = (next: GuideLanguage) => {
    startWhenLoaded.current = true;
    onLanguageChange(next);
  };

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-[1200] flex max-h-[68dvh] flex-col rounded-t-lg border-t border-border bg-surface shadow-overlay lg:inset-x-auto lg:bottom-auto lg:right-4 lg:top-[4.4rem] lg:max-h-[calc(100dvh-5.5rem)] lg:w-[26rem] lg:rounded-card lg:border"
    >
      <div className="shrink-0 space-y-3 border-b border-border px-4 pb-4 pt-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="eyebrow" lang={language}>
              {messages.eyebrow}
            </p>
            <h2
              id={titleId}
              ref={headingRef}
              tabIndex={-1}
              lang={language}
              className="mt-0.5 text-[17px] font-semibold tracking-tight text-ink outline-none"
            >
              {guide.data?.title ?? screen.label}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={messages.close}
            className="-mr-1 flex size-9 shrink-0 items-center justify-center rounded-sm text-ink-muted hover:bg-surface-sunken hover:text-ink"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <SegmentedControl
          label={messages.chooseLanguage}
          options={languageOptions}
          value={language}
          onChange={changeLanguage}
        />

        <GuideControls
          status={player.status}
          current={player.current}
          total={sections.length}
          progress={player.progress}
          heading={sections[player.current]?.heading}
          messages={messages}
          disabled={sections.length === 0}
          onPlay={() => {
            player.play();
          }}
          onPause={player.pause}
        />
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-2 py-3" lang={language}>
        {guide.error ? (
          <div className="px-2">
            <StatusMessage kind="error" title={messages.loadFailed} detail={guide.error.message} />
          </div>
        ) : guide.isLoading || !guide.data ? (
          <div className="px-2">
            <Skeleton label={messages.loading} rows={4} />
          </div>
        ) : (
          <>
            {!guide.data.voice_available && (
              <div className="px-2">
                <StatusMessage kind="empty" title={messages.voiceUnavailable} />
              </div>
            )}
            {player.status === 'error' && (
              <div className="px-2">
                <StatusMessage kind="error" title={messages.clipFailed} />
              </div>
            )}
            <p className="px-3 text-xs text-ink-subtle">{messages.jumpHint}</p>
            <GuideTranscript
              sections={sections}
              language={language}
              current={player.current}
              isSpeaking={isSpeaking}
              onSelect={player.play}
            />
            <p className="px-3 pt-1 text-[11px] text-ink-subtle">{guide.data.voice}</p>
          </>
        )}
      </div>
    </div>
  );
}
