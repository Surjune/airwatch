import type { ReactNode } from 'react';

interface PageHeaderProps {
  readonly title: string;
  /** What the screen shows, and what it cannot say. */
  readonly description: ReactNode;
  readonly actions?: ReactNode;
}

/**
 * The heading block each screen opens with.
 *
 * The description is required rather than optional, and it is where each screen
 * states its own limits -- that the forecast has no day-to-day skill, that a
 * hotspot is a comparison and not a threshold, that a photograph cannot measure
 * PM2.5. Those caveats belong next to the thing they qualify, not in a footnote
 * nobody scrolls to.
 */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
