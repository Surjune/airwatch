import { Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { useAlertBrief } from '@/hooks/useAlertBrief';

/**
 * A two-sentence brief of the alert above it, written by Google Gemini on request.
 *
 * It sits below the figures rather than replacing them. Every number in it has
 * already been checked against those figures on the server, and a brief that
 * failed the check is never shown -- the error says so instead.
 */
export function AlertBriefPanel({ alertId }: { readonly alertId: number }) {
  const { brief, error, isLoading, load } = useAlertBrief(alertId);

  if (brief) {
    return (
      <section
        aria-label="Brief written by Google Gemini"
        className="mt-3 rounded-sm border border-accent/20 bg-accent-subtle/60 p-3"
      >
        <p className="eyebrow flex items-center gap-1.5 text-accent">
          <Sparkles aria-hidden className="size-3.5" />
          Brief · Google Gemini
        </p>
        <p className="mt-1 text-[13px] leading-relaxed text-ink">{brief.summary}</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink">
          <span className="font-semibold">Suggested first step:</span> {brief.suggested_action}
        </p>
        <p className="mt-2 text-[11px] leading-snug text-ink-subtle">{brief.notice}</p>
      </section>
    );
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <Button variant="ghost" isBusy={isLoading} busyLabel="Gemini is writing…" onClick={load}>
        <Sparkles aria-hidden className="size-3.5" />
        Summarise with Gemini
      </Button>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error.message}
        </p>
      )}
    </div>
  );
}
