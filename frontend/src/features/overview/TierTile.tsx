import type { ReactNode } from 'react';

import type { TierState } from '@/lib/tiers';

interface TierTileProps {
  readonly tier: string;
  readonly name: string;
  readonly value: ReactNode;
  readonly note: string;
  readonly state: TierState;
}

const STATES: Record<TierState, { label: string; dot: string; text: string }> = {
  live: { label: 'contributing', dot: 'bg-ok', text: 'text-ok' },
  thin: { label: 'thin here', dot: 'bg-warn', text: 'text-warn' },
  none: { label: 'nothing yet', dot: 'bg-danger', text: 'text-danger' },
  loading: { label: 'checking', dot: 'bg-ink-subtle', text: 'text-ink-subtle' },
};

/**
 * One source of evidence and how much of it this city actually has.
 *
 * The state word is written out beside its dot, because "nothing yet" is the
 * finding for several tiers in a data-poor city and must read as a gap, not as
 * a quiet green panel.
 */
export function TierTile({ tier, name, value, note, state }: TierTileProps) {
  const look = STATES[state];
  return (
    <div className="flex min-w-0 flex-col bg-surface p-4">
      <p className="eyebrow">{tier}</p>
      <p className="mt-1 text-sm font-semibold text-ink">{name}</p>
      <p className="figure mt-3 text-[26px] font-medium leading-none text-ink">{value}</p>
      <p className="mt-2 flex-1 text-xs leading-snug text-ink-muted">{note}</p>
      <p className={`mt-3 inline-flex items-center gap-1.5 text-[11px] font-medium ${look.text}`}>
        <span aria-hidden className={`size-1.5 rounded-full ${look.dot}`} />
        {look.label}
      </p>
    </div>
  );
}
