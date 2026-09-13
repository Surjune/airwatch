import { useHealth } from '@/hooks/useHealth';

/**
 * Whether the API behind the dashboard is reachable, shown in the chrome.
 *
 * A dashboard that silently lost its backend looks exactly like one with
 * nothing to report. Putting the connection state where the eye rests between
 * screens means an operator never mistakes an outage for a quiet day.
 */
export function ApiStatus() {
  const { report, error, isLoading } = useHealth();

  const missing = report?.upstreams.filter((upstream) => !upstream.configured) ?? [];
  const state = isLoading
    ? { dot: 'bg-chrome-muted', label: 'Connecting…', detail: 'Checking the API' }
    : error || !report
      ? { dot: 'bg-red-400', label: 'API unreachable', detail: 'Screens cannot load data' }
      : missing.length > 0
        ? {
            dot: 'bg-amber-400',
            label: 'Partly configured',
            detail: `${missing.map((upstream) => upstream.provider).join(', ')} not configured`,
          }
        : {
            dot: 'bg-emerald-400',
            label: 'All sources connected',
            detail: `API v${report.version} · ${report.environment}`,
          };

  return (
    <div role="status" className="flex items-start gap-2.5 rounded-lg bg-chrome-raised px-3 py-2.5">
      <span className="relative mt-1.5 flex size-2 shrink-0">
        {!isLoading && !error && (
          <span
            aria-hidden
            className={`absolute inline-flex size-full animate-ping rounded-full opacity-60 ${state.dot}`}
          />
        )}
        <span aria-hidden className={`relative inline-flex size-2 rounded-full ${state.dot}`} />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-chrome-ink">{state.label}</p>
        <p className="truncate text-[11px] text-chrome-muted" title={state.detail}>
          {state.detail}
        </p>
      </div>
    </div>
  );
}
