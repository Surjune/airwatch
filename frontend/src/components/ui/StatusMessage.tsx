interface StatusMessageProps {
  readonly kind: 'loading' | 'error' | 'empty';
  readonly title: string;
  readonly detail?: string;
  readonly requestId?: string;
}

const STYLES: Record<StatusMessageProps['kind'], string> = {
  loading: 'border-neutral-300 bg-neutral-50 text-neutral-700',
  error: 'border-red-300 bg-red-50 text-red-800',
  empty: 'border-amber-300 bg-amber-50 text-amber-900',
};

/**
 * A loading, failed or empty state.
 *
 * Deliberately distinct from each other and from a normal render. A failed
 * request that renders as an empty map reads as clean air, which is the exact
 * failure this project exists to remove.
 */
export function StatusMessage({ kind, title, detail, requestId }: StatusMessageProps) {
  return (
    <div className={`rounded border p-3 text-sm ${STYLES[kind]}`}>
      <p className="font-medium">{title}</p>
      {detail && <p className="mt-1">{detail}</p>}
      {requestId && <p className="mt-2 font-mono text-xs opacity-70">request {requestId}</p>}
    </div>
  );
}
