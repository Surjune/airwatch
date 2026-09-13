import type { ReactNode } from 'react';

interface CardProps {
  readonly children: ReactNode;
  /** Optional heading row. Omitted for a card that is purely a container. */
  readonly title?: string;
  readonly description?: string;
  /** Rendered at the right of the heading row, for counts or actions. */
  readonly aside?: ReactNode;
  readonly className?: string;
  /** Removes the body padding, for a card whose child is a table or a map. */
  readonly flush?: boolean;
}

/**
 * The single panel container.
 *
 * Every screen is a stack of these, so the border, radius and shadow are
 * defined once. Before this existed the same six Tailwind classes were repeated
 * in five components, and they had already started to drift.
 */
export function Card({ children, title, description, aside, className, flush }: CardProps) {
  return (
    <section
      className={`overflow-hidden rounded-[--radius-card] border border-border bg-surface-raised ${
        className ?? ''
      }`}
    >
      {(title ?? aside) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-ink-muted">{description}</p>}
          </div>
          {aside && <div className="shrink-0 text-xs text-ink-muted">{aside}</div>}
        </header>
      )}
      <div className={flush ? '' : 'p-4'}>{children}</div>
    </section>
  );
}
