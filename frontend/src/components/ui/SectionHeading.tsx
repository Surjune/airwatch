import type { ReactNode } from 'react';

interface SectionHeadingProps {
  /** Two-digit step number, so the overview reads as a sequence. */
  readonly index: string;
  readonly title: string;
  readonly description?: string;
  readonly aside?: ReactNode;
  readonly id?: string;
}

/**
 * A numbered section heading.
 *
 * The overview is one argument in order -- what the air is, what the network can
 * see, what it found, who was told -- so its sections are numbered like a report
 * rather than stacked as interchangeable widgets.
 */
export function SectionHeading({ index, title, description, aside, id }: SectionHeadingProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-t border-ink pt-3">
      <div className="flex min-w-0 gap-3 sm:gap-4">
        <span className="figure pt-0.5 text-[13px] text-signal">{index}</span>
        <div className="min-w-0">
          <h2 id={id} className="text-lg font-semibold leading-snug tracking-tight text-ink">
            {title}
          </h2>
          {description && (
            <p className="mt-0.5 max-w-2xl text-[13px] leading-relaxed text-ink-muted">
              {description}
            </p>
          )}
        </div>
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </div>
  );
}
