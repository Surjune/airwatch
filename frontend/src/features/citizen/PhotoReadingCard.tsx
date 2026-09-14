import { ScanEye } from 'lucide-react';

import {
  confidencePercent,
  namesASource,
  visibleSourceLabel,
  type PhotoReading,
} from '@/lib/photo-reading';

interface PhotoReadingCardProps {
  readonly reading: PhotoReading | null | undefined;
  /** Why there is no reading, when there is none. */
  readonly note: string | null | undefined;
}

/**
 * What Google Gemini sees in the photograph.
 *
 * Set apart from the haze measurement and labelled as an AI suggestion, because
 * it answers a different question: not how polluted the air is, but what in the
 * picture might be causing it. A source that looks present in a photograph is
 * worth reporting and is not established by it.
 */
export function PhotoReadingCard({ reading, note }: PhotoReadingCardProps) {
  if (!reading) {
    return note ? <p className="mt-4 text-xs text-ink-subtle">{note}</p> : null;
  }

  const isWarning = reading.visible_source === 'not_outdoor';

  return (
    <div
      className={`mt-4 rounded-sm border p-3 ${
        isWarning ? 'border-warn/30 bg-warn-subtle' : 'border-border bg-paper'
      }`}
    >
      <p className="eyebrow flex items-center gap-1.5">
        <ScanEye aria-hidden className="size-3.5" />
        What Google Gemini sees
      </p>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm">
        <strong className={`font-semibold ${isWarning ? 'text-warn' : 'text-ink'}`}>
          {namesASource(reading.visible_source)
            ? `Likely ${visibleSourceLabel(reading.visible_source).toLowerCase()}`
            : visibleSourceLabel(reading.visible_source)}
        </strong>
        <span className="figure text-xs text-ink-muted">
          {confidencePercent(reading)} confidence
        </span>
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{reading.observation}</p>
      <p className="mt-2 text-[11px] leading-snug text-ink-subtle">
        An AI suggestion about what is visible ({reading.model}). It measures nothing and does not
        prove where pollution comes from. It is included in your PDF report.
      </p>
    </div>
  );
}
