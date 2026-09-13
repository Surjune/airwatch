import type { ReactNode } from 'react';

interface PageHeaderProps {
  readonly title: string;
  /** What the screen shows, and what it cannot say. */
  readonly description: ReactNode;
  /** The running head above the title: where in the workflow this screen sits. */
  readonly eyebrow?: string;
  readonly actions?: ReactNode;
}

/**
 * The heading block each screen opens with.
 *
 * The description is required rather than optional, and it is where each screen
 * states its own limits -- that the forecast has no day-to-day skill, that a
 * hotspot is a comparison and not a threshold, that a photograph cannot measure
 * PM2.5. Those caveats belong next to the thing they qualify.
 */
export function PageHeader({ title, description, eyebrow, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
      <div className="max-w-3xl">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="mt-1 text-[26px] font-semibold leading-tight tracking-tight text-ink sm:text-3xl">
          {title}
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
