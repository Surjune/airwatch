import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { Stat, StatRow } from '@/components/ui/Stat';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { AlertCard } from '@/features/alerts/AlertCard';
import { useAlerts } from '@/hooks/useAlerts';

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
 * responsibility. Everything above it — fusion, detection, attribution —
 * produces a finding; if that finding never reaches a body that can act on it,
 * none of it changes what anyone breathes.
 *
 * The list is ordered by standardised excess, as the API returns it. Ordering by
 * concentration would put a citywide bad day above a single anomalous source,
 * which inverts the priority the detector exists to express.
 *
 * The three figures at the top are deliberately different questions: how many
 * are waiting, how many have been ignored past their deadline, and how many
 * nobody has actually been told about. Collapsing them into one "open" count
 * would hide the last, which is the one that means the chain is broken.
 */
export function AlertConsole() {
  const { alerts, breaches, error, isLoading, isBusy, acknowledge, resolve, dispatch } =
    useAlerts();
  const [filter, setFilter] = useState<FilterKey>('open');
  const [lastDispatch, setLastDispatch] = useState<string | null>(null);

  const overdueIds = useMemo(() => new Set(breaches.map((breach) => breach.alert_id)), [breaches]);

  const visible = useMemo(() => {
    if (filter === 'all') return alerts;
    if (filter === 'resolved') return alerts.filter((alert) => alert.status === 'resolved');
    return alerts.filter((alert) => alert.status !== 'resolved');
  }, [alerts, filter]);

  const openCount = alerts.filter((alert) => alert.status !== 'resolved').length;
  const undelivered = alerts.filter(
    (alert) => alert.delivered_at === null && alert.status !== 'resolved',
  ).length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-border bg-surface px-4 py-4 sm:px-6">
        <PageHeader
          title="Authority console"
          description="Alerts are routed by jurisdiction, one per episode, and ordered by how far above its neighbourhood each sits — not by concentration. Recording an alert and delivering it are separate facts."
          actions={
            <Button
              variant="primary"
              size="md"
              isBusy={isBusy}
              busyLabel="Working…"
              onClick={() => {
                void dispatch().then((outcome) => {
                  if (!outcome) return;
                  setLastDispatch(
                    `${String(outcome.detected)} detected · ${String(outcome.raised)} raised · ` +
                      `${String(outcome.suppressed)} already in flight · ${String(outcome.unrouted)} unrouted`,
                  );
                });
              }}
            >
              Run detection
            </Button>
          }
        />

        <div className="mt-4">
          <StatRow>
            <Stat
              label="Open"
              value={openCount}
              note="Awaiting an authority"
              tone={openCount > 0 ? 'warn' : 'neutral'}
            />
            <Stat
              label="Past deadline"
              value={overdueIds.size}
              note="Sent and never answered"
              tone={overdueIds.size > 0 ? 'danger' : 'neutral'}
            />
            <Stat
              label="Not delivered"
              value={undelivered}
              note="Recorded, nobody told yet"
              tone={undelivered > 0 ? 'warn' : 'neutral'}
            />
          </StatRow>
        </div>

        {lastDispatch && (
          <p className="mt-3 rounded-md bg-surface-sunken px-2.5 py-1.5 text-xs text-ink-muted">
            {lastDispatch}
          </p>
        )}

        <div className="mt-4 flex gap-1" role="group" aria-label="Filter alerts by state">
          {FILTERS.map((option) => (
            <Button
              key={option.key}
              variant={filter === option.key ? 'primary' : 'ghost'}
              aria-pressed={filter === option.key}
              onClick={() => {
                setFilter(option.key);
              }}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <div className="p-4 sm:p-6">
            <StatusMessage
              kind="error"
              title="Could not load the alert inbox"
              detail={`${error.message} An empty console here would mean the request failed, not that nothing needs attention.`}
              {...(error.requestId ? { requestId: error.requestId } : {})}
            />
          </div>
        ) : isLoading ? (
          <div className="p-4 sm:p-6">
            <Skeleton label="Loading alerts" rows={5} />
          </div>
        ) : visible.length === 0 ? (
          <div className="p-4 sm:p-6">
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
          <ul>
            {visible.map((alert) => (
              <li key={alert.alert_id}>
                <AlertCard
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
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
