import type { ReactNode } from 'react';

interface StatProps {
  readonly label: string;
  readonly value: ReactNode;
  /** Context under the number, for a unit or a caveat. */
  readonly note?: string;
  readonly tone?: 'neutral' | 'danger' | 'warn' | 'ok';
}

const TONES = {
  neutral: 'text-ink',
  danger: 'text-danger',
  warn: 'text-warn',
  ok: 'text-ok',
} as const;

/**
 * A labelled figure.
 *
 * The label sits above the value rather than beside it, so a row of these can
 * be scanned by value. `note` exists because almost nothing here should be
 * shown as a bare number: a count needs its window, a concentration needs its
 * unit, and an estimate needs its error.
 */
export function Stat({ label, value, note, tone = 'neutral' }: StatProps) {
  return (
    <div>
      <dt className="text-xs font-medium text-ink-subtle">{label}</dt>
      <dd className={`mt-0.5 text-xl font-semibold leading-tight ${TONES[tone]}`}>{value}</dd>
      {note && <p className="mt-0.5 text-xs text-ink-muted">{note}</p>}
    </div>
  );
}

/** A row of stats, wrapping on narrow screens. */
export function StatRow({ children }: { readonly children: ReactNode }) {
  return <dl className="flex flex-wrap gap-x-8 gap-y-4">{children}</dl>;
}
