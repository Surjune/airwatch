import type { ReactNode } from 'react';

type Tone = 'neutral' | 'danger' | 'warn' | 'ok' | 'signal';

interface StatProps {
  readonly label: string;
  readonly value: ReactNode;
  /** The window, unit or caveat the number needs. Never omitted on purpose. */
  readonly note: string;
  readonly tone?: Tone;
}

const VALUE_TONES: Record<Tone, string> = {
  neutral: 'text-ink',
  danger: 'text-danger',
  warn: 'text-warn',
  ok: 'text-ok',
  signal: 'text-signal',
};

/**
 * One headline figure with its label and caveat.
 *
 * Rendered as a `dt`/`dd` pair, so a row of these must sit inside a `dl`. The
 * number is set in the monospace, large, with nothing decorative beside it --
 * the figure is the point, and an icon in a tinted square would only compete.
 */
export function Stat({ label, value, note, tone = 'neutral' }: StatProps) {
  return (
    <div className="min-w-0 border-l border-border pl-3 sm:pl-4">
      <dt className="text-[13px] text-ink-muted">{label}</dt>
      <dd className={`figure mt-1 text-[28px] font-medium leading-none ${VALUE_TONES[tone]}`}>
        {value}
      </dd>
      <p className="mt-1.5 text-xs leading-snug text-ink-subtle">{note}</p>
    </div>
  );
}
