import { useMemo, useState } from 'react';

import { AlertCard } from '@/features/alerts/AlertCard';
import { useAlerts } from '@/hooks/useAlerts';
import { StatusMessage } from '@/components/ui/StatusMessage';

/** Status filters an operator can apply. */
const FILTERS = [
  { key: 'open', label: 'Open' },
  { key: 'all', label: 'All' },
  { key: 'resolved', label: 'Resolved' },
] as const;

type FilterKey = (typeof FILTERS)[number]['key'];

/**
 * The authority console.
 *
 * This is where the system stops being an observation and becomes someone's
 * responsibility. Everything above it -- fusion, detection, attribution --
 * produces a finding; if that finding never reaches a body that can act on it,
 * none of it changes what anyone breathes.
 *
 * The list is ordered by standardised excess, as the API returns it. Ordering by
 * concentration would put a citywide bad day above a single anomalous source,
 * which inverts the priority the detector exists to express.
 */
export function AlertConsole() {
  const { alerts, breaches, error, isLoading, isBusy, acknowledge, resolve, dispatch } =
    useAlerts();
  const [filter, setFilter] = useState<FilterKey>('open');
  const [lastDispatch, setLastDispatch] = useState<string | null>(null);

  const overdueIds = useMemo(
    () => new Set(breaches.map((breach) => breach.alert_id)),
    [breaches],
  );

  const visible = useMemo(() => {
    if (filter === 'all') return alerts;
    if (filter === 'resolved') return alerts.filter((alert) => alert.status === 'resolved');
    return alerts.filter((alert) => alert.status !== 'resolved');
  }, [alerts, filter]);

  const openCount = alerts.filter((alert) => alert.status !== 'resolved').length;

  return (
    <div className="flex h-full min-h-0 flex-col bg-neutral-50">
      <div className="border-b border-neutral-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Authority console</h2>
            <p className="text-xs text-neutral-600">
              {openCount} open · {overdueIds.size} past deadline · routed by jurisdiction
            </p>
          </div>
          <button
            type="button"
            disabled={isBusy}
            onClick={() => {
              void dispatch().then((outcome) => {
                if (!outcome) return;
                setLastDispatch(
                  `${String(outcome.detected)} detected · ${String(outcome.raised)} raised · ` +
                    `${String(outcome.suppressed)} already in flight · ${String(outcome.unrouted)} unrouted`,
                );
              });
            }}
            className="rounded bg-neutral-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {isBusy ? 'Working…' : 'Run detection'}
          </button>
        </div>

        <div className="mt-3 flex gap-1">
          {FILTERS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => {
                setFilter(option.key);
              }}
              className={`rounded px-2.5 py-1 text-xs font-medium ${
                filter === option.key
                  ? 'bg-neutral-800 text-white'
                  : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        {lastDispatch && (
          <p className="mt-2 rounded bg-neutral-100 px-2 py-1 text-xs text-neutral-700">
            {lastDispatch}
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <div className="p-4">
            <StatusMessage
              kind="error"
              title="Could not load the alert inbox"
              detail={`${error.message} An empty console here would mean the request failed, not that nothing needs attention.`}
              {...(error.requestId ? { requestId: error.requestId } : {})}
            />
          </div>
        ) : isLoading ? (
          <div className="p-4">
            <StatusMessage kind="loading" title="Loading alerts…" />
          </div>
        ) : visible.length === 0 ? (
          <div className="p-4">
            <StatusMessage
              kind="empty"
              title={filter === 'open' ? 'No open alerts' : 'Nothing matches this filter'}
              {...(filter === 'open'
                ? {
                    detail:
                      'No detected episode is currently waiting on an authority. Run detection to check the latest window.',
                  }
                : {})}
            />
          </div>
        ) : (
          visible.map((alert) => (
            <AlertCard
              key={alert.alert_id}
              alert={alert}
              isOverdue={overdueIds.has(alert.alert_id)}
              isBusy={isBusy}
              onAcknowledge={(id) => {
                void acknowledge(id);
              }}
              onResolve={(id, note) => {
                void resolve(id, note);
              }}
            />
          ))
        )}
      </div>
    </div>
  );
}
