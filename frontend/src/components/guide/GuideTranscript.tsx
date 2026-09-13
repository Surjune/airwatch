import { Volume2 } from 'lucide-react';
import { useEffect, useRef } from 'react';

import type { GuideLanguage, GuideSection } from '@/lib/guide';

interface GuideTranscriptProps {
  readonly sections: readonly GuideSection[];
  readonly language: GuideLanguage;
  /** The paragraph being spoken, highlighted so the listener can read along. */
  readonly current: number;
  readonly isSpeaking: boolean;
  readonly onSelect: (index: number) => void;
}

/**
 * Everything the voice says, as text.
 *
 * Complete on its own: the guide has to work with the sound off, for someone
 * who is hard of hearing, and when speech cannot be generated. Each paragraph is
 * a button, because the listener who needs only "how do I send a reading" should
 * not sit through the four paragraphs before it.
 */
export function GuideTranscript({
  sections,
  language,
  current,
  isSpeaking,
  onSelect,
}: GuideTranscriptProps) {
  const activeRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    if (isSpeaking) activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [current, isSpeaking]);

  return (
    <ol lang={language} className="space-y-1">
      {sections.map((section) => {
        const isActive = section.index === current && isSpeaking;
        return (
          <li key={section.index} ref={section.index === current ? activeRef : undefined}>
            <button
              type="button"
              aria-current={isActive ? 'step' : undefined}
              onClick={() => {
                onSelect(section.index);
              }}
              className={`group w-full rounded-sm border-l-2 py-2 pl-3 pr-2 text-left transition-colors ${
                isActive
                  ? 'border-signal bg-signal-subtle/60'
                  : 'border-transparent hover:border-border-strong hover:bg-paper'
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="figure text-[11px] text-signal">
                  {String(section.index + 1).padStart(2, '0')}
                </span>
                <span className="text-[13px] font-semibold text-ink">{section.heading}</span>
                {isActive && (
                  <Volume2 aria-hidden className="ml-auto size-3.5 shrink-0 text-signal" />
                )}
              </span>
              <span className="mt-1 block text-[13.5px] leading-relaxed text-ink-muted group-aria-[current=step]:text-ink">
                {section.text}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
