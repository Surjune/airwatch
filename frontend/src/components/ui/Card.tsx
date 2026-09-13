import type { ReactNode } from 'react';

interface CardProps {
  readonly children: ReactNode;
  /** Optional heading row. Omitted for a card that is purely a container. */
  readonly title?: string;
  readonly description?: string;
  /** A short uppercase label above the title, for where the figures come from. */
  readonly eyebrow?: string;
  /** Rendered at the right of the heading row, for counts or actions. */
  readonly aside?: ReactNode;
  readonly className?: string;
  /** Removes the body padding, for a card whose child is a table or a list. */
  readonly flush?: boolean;
}

/**
 * The single panel container.
 *
 * A hairline and no shadow: panels sit on the page like ruled boxes on a sheet,
 * so the eye goes to the figures inside them rather than to the chrome around.
 */
export function Card({
  children,
  title,
  description,
  eyebrow,
  aside,
  className,
  flush,
}: CardProps) {
  const hasHeader = Boolean(title ?? eyebrow ?? aside);
  return (
    <section
      className={`overflow-hidden rounded-card border border-border bg-surface ${className ?? ''}`}
    >
      {hasHeader && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-border px-4 py-3 sm:px-5">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && (
              <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>
            )}
            {description && (
              <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">{description}</p>
            )}
          </div>
          {aside && <div className="shrink-0 text-xs text-ink-muted">{aside}</div>}
        </header>
      )}
      <div className={flush ? '' : 'p-4 sm:p-5'}>{children}</div>
    </section>
  );
}
