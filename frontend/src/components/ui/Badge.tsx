import type { ReactNode } from 'react';

type Tone = 'neutral' | 'danger' | 'warn' | 'ok' | 'accent' | 'signal';

interface BadgeProps {
  readonly children: ReactNode;
  readonly tone?: Tone;
  /** Rendered before the label, for a status dot. */
  readonly dot?: boolean;
}

const TONES: Record<Tone, string> = {
  neutral: 'border-border bg-surface-sunken text-ink-muted',
  danger: 'border-danger/25 bg-danger-subtle text-danger',
  warn: 'border-warn/25 bg-warn-subtle text-warn',
  ok: 'border-ok/25 bg-ok-subtle text-ok',
  accent: 'border-accent/25 bg-accent-subtle text-accent',
  signal: 'border-signal/25 bg-signal-subtle text-signal',
};

const DOTS: Record<Tone, string> = {
  neutral: 'bg-ink-subtle',
  danger: 'bg-danger',
  warn: 'bg-warn',
  ok: 'bg-ok',
  accent: 'bg-accent',
  signal: 'bg-signal',
};

/** A small status label. Tone carries meaning, so it is never chosen for looks. */
export function Badge({ children, tone = 'neutral', dot = false }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-1.5 py-px text-[11px] font-medium leading-4 ${TONES[tone]}`}
    >
      {dot && <span aria-hidden className={`size-1.5 rounded-full ${DOTS[tone]}`} />}
      {children}
    </span>
  );
}
