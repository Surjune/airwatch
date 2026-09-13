import type { ReactNode } from 'react';

type Tone = 'neutral' | 'danger' | 'warn' | 'ok' | 'accent';

interface BadgeProps {
  readonly children: ReactNode;
  readonly tone?: Tone;
  /** Rendered before the label, for a status dot. */
  readonly dot?: boolean;
}

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-sunken text-ink-muted',
  danger: 'bg-danger-subtle text-danger',
  warn: 'bg-warn-subtle text-warn',
  ok: 'bg-ok-subtle text-ok',
  accent: 'bg-accent-subtle text-accent',
};

const DOTS: Record<Tone, string> = {
  neutral: 'bg-ink-subtle',
  danger: 'bg-danger',
  warn: 'bg-warn',
  ok: 'bg-ok',
  accent: 'bg-accent',
};

/** A small status label. Tone carries meaning, so it is never chosen for looks. */
export function Badge({ children, tone = 'neutral', dot = false }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {dot && <span aria-hidden className={`size-1.5 rounded-full ${DOTS[tone]}`} />}
      {children}
    </span>
  );
}
