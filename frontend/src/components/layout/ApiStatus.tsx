import { useHealth } from '@/hooks/useHealth';

/**
 * Whether the API behind the dashboard is reachable, shown in the masthead.
 *
 * A dashboard that silently lost its backend looks exactly like one with nothing
 * to report. Keeping the connection state where the eye rests between screens
 * means an operator never mistakes an outage for a quiet day.
 */
export function ApiStatus() {
  const { report, error, isLoading } = useHealth();

  const missing = report?.upstreams.filter((upstream) => !upstream.configured) ?? [];
  const state = isLoading
    ? { dot: 'bg-ink-subtle', label: 'Connecting…', detail: 'Checking the API' }
    : error || !report
      ? { dot: 'bg-danger', label: 'API unreachable', detail: 'Screens cannot load data' }
      : missing.length > 0
        ? {
            dot: 'bg-warn',
            label: 'Partly configured',
            detail: `${missing.map((upstream) => upstream.provider).join(', ')} not configured`,
          }
        : {
            dot: 'bg-ok',
            label: 'Live',
            detail: `All ${String(report.upstreams.length)} sources connected · API v${report.version}`,
          };

  return (
    <div role="status" className="flex items-center gap-2" title={state.detail}>
      <span aria-hidden className={`size-2 shrink-0 rounded-full ${state.dot}`} />
      {/* The word is dropped on a phone, where the masthead has room for the dot only. */}
      <span aria-hidden className="hidden text-xs font-medium text-ink-muted lg:inline">
        {state.label}
      </span>
      <span className="sr-only">
        {state.label}. {state.detail}
      </span>
    </div>
  );
}
