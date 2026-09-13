interface StatusMessageProps {
  readonly kind: 'loading' | 'error' | 'empty';
  readonly title: string;
  readonly detail?: string;
  readonly requestId?: string;
}

const STYLES: Record<StatusMessageProps['kind'], string> = {
  loading: 'border-border bg-surface-sunken text-ink-muted',
  error: 'border-danger/30 bg-danger-subtle text-danger',
  empty: 'border-warn/30 bg-warn-subtle text-warn',
};

/** A glyph per state, so the three are distinguishable without relying on colour. */
const GLYPHS: Record<StatusMessageProps['kind'], string> = {
  loading: '···',
  error: '!',
  empty: '∅',
};

const ROLES: Record<StatusMessageProps['kind'], 'status' | 'alert'> = {
  loading: 'status',
  error: 'alert',
  empty: 'status',
};

/**
 * A loading, failed or empty state.
 *
 * These three must never look alike. A failed request that renders as an empty
 * map reads as clean air, which is the exact misreading this project exists to
 * remove — so each state gets its own colour *and* its own glyph, because
 * colour alone fails for a colour-blind reader and fails again in print.
 *
 * A failure is announced as an alert rather than a status: it interrupts, because
 * the user is about to draw a conclusion from a screen that has no data on it.
 */
export function StatusMessage({ kind, title, detail, requestId }: StatusMessageProps) {
  return (
    <div
      role={ROLES[kind]}
      className={`flex gap-3 rounded-[--radius-card] border p-3.5 text-sm ${STYLES[kind]}`}
    >
      <span
        aria-hidden
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-current/10 text-xs font-bold"
      >
        {GLYPHS[kind]}
      </span>
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        {detail && <p className="mt-1 leading-relaxed opacity-90">{detail}</p>}
        {requestId && (
          <p className="mt-2 font-mono text-xs opacity-70">
            request <span className="select-all">{requestId}</span>
          </p>
        )}
      </div>
    </div>
  );
}
