import { LoaderCircle, Pause, Play } from 'lucide-react';

import type { PlayerStatus } from '@/hooks/useGuidePlayer';
import type { GuideMessages } from '@/lib/guide-messages';

/** Percent of the progress track. */
const PERCENT = 100;

interface GuideControlsProps {
  readonly status: PlayerStatus;
  readonly current: number;
  readonly total: number;
  readonly progress: number;
  readonly heading: string | undefined;
  readonly messages: GuideMessages;
  readonly disabled: boolean;
  readonly onPlay: () => void;
  readonly onPause: () => void;
}

/**
 * One large play control, which paragraph is playing, and how far through it.
 *
 * Deliberately a single button rather than a media player's row of controls:
 * the listener is often someone using this site for the first time, on a phone,
 * and one obvious thing to press is the whole interface they need.
 */
export function GuideControls({
  status,
  current,
  total,
  progress,
  heading,
  messages,
  disabled,
  onPlay,
  onPause,
}: GuideControlsProps) {
  const isPlaying = status === 'playing' || status === 'loading';
  const label = isPlaying ? messages.pause : status === 'paused' ? messages.resume : messages.play;
  // Across the whole guide rather than within one paragraph, so the bar answers
  // "how much is left", which is the question a listener actually has.
  const overall = total > 0 ? Math.min(1, (current + progress) / total) : 0;

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        disabled={disabled}
        aria-label={label}
        onClick={isPlaying ? onPause : onPlay}
        className="flex size-11 shrink-0 items-center justify-center rounded-full bg-ink text-paper transition-colors hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {status === 'loading' ? (
          <LoaderCircle aria-hidden className="size-5 animate-spin" />
        ) : isPlaying ? (
          <Pause aria-hidden className="size-5" fill="currentColor" />
        ) : (
          <Play aria-hidden className="ml-0.5 size-5" fill="currentColor" />
        )}
      </button>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[13px] font-medium text-ink">
            {status === 'idle' ? label : heading}
          </span>
          <span className="figure shrink-0 text-[11px] text-ink-subtle">
            {messages.part(current + 1, total)}
          </span>
        </p>
        <div
          role="progressbar"
          aria-label={messages.part(current + 1, total)}
          aria-valuemin={0}
          aria-valuemax={PERCENT}
          aria-valuenow={Math.round(overall * PERCENT)}
          className="mt-2 h-1 overflow-hidden rounded-full bg-surface-sunken"
        >
          <div
            className="h-full bg-signal transition-[width] duration-200"
            style={{ width: `${String(overall * PERCENT)}%` }}
          />
        </div>
      </div>
    </div>
  );
}
