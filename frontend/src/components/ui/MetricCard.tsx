import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

type Tone = 'neutral' | 'danger' | 'warn' | 'ok';

interface MetricCardProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly value: ReactNode;
  /** The window, unit or caveat the number needs. Never omitted on purpose. */
  readonly note: string;
  readonly tone?: Tone;
}

const ICON_TONES: Record<Tone, string> = {
  neutral: 'bg-accent-subtle text-accent',
  danger: 'bg-danger-subtle text-danger',
  warn: 'bg-warn-subtle text-warn',
  ok: 'bg-ok-subtle text-ok',
};

const VALUE_TONES: Record<Tone, string> = {
  neutral: 'text-ink',
  danger: 'text-danger',
  warn: 'text-warn',
  ok: 'text-ok',
};

/** A headline figure in a card, for the top of a dashboard. */
export function MetricCard({ icon: Icon, label, value, note, tone = 'neutral' }: MetricCardProps) {
  return (
    <div className="rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <dt className="text-sm font-medium text-ink-muted">{label}</dt>
        <span className={`flex size-8 items-center justify-center rounded-lg ${ICON_TONES[tone]}`}>
          <Icon aria-hidden className="size-4" strokeWidth={2} />
        </span>
      </div>
      <dd className={`mt-2 text-3xl font-semibold tracking-tight ${VALUE_TONES[tone]}`}>{value}</dd>
      <p className="mt-1 text-xs text-ink-subtle">{note}</p>
    </div>
  );
}
