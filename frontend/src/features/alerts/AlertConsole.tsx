import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/PageHeader';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Skeleton } from '@/components/ui/Skeleton';
import { Stat } from '@/components/ui/Stat';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { AlertCard } from '@/features/alerts/AlertCard';
import { OperatorSignIn } from '@/features/alerts/OperatorSignIn';
import { useAlerts, type DispatchResponse } from '@/hooks/useAlerts';
import { useOperator } from '@/lib/operator';
import { useScope } from '@/lib/scope';

/** Status filters an operator can apply. */
const FILTERS = [
  { key: 'open', label: 'Open' },
  { key: 'coordination', label: 'Across a boundary' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'all', label: 'All' },
] as const;

type FilterKey = (typeof FILTERS)[number]['key'];

/**
 * The authority console.
 *
 * This is where the system stops being an observation and becomes someone's
 * responsibility. Everything before it produces a finding; if that finding never
 * reaches a body that can act on it, none of it changes what anyone breathes.
 *
 * The list is ordered by standardised excess, as the API returns it. The figures
 * at the top are deliberately different questions -- waiting, ignored past a
 * deadline, sent across a boundary, and never delivered -- because collapsing
 * them into one "open" count would hide the last, which means the chain is broken.
 */
export function AlertConsole() {
  const { city, current } = useScope();
  const { isOperator } = useOperator();
  const { alerts, breaches, error, isLoading, isBusy, acknowledge, resolve, dispatch } =
    useAlerts(city);
  const [filter, setFilter] = useState<FilterKey>('open');
  const [lastDispatch, setLastDispatch] = useState<DispatchResponse | null>(null);

  const overdueIds = useMemo(() => new Set(breaches.map((breach) => breach.alert_id)), [breaches]);
  const open = alerts.filter((alert) => alert.status !== 'resolved');

  const visible = useMemo(() => {
    if (filter === 'all') return alerts;
    if (filter === 'resolved') return alerts.filter((alert) => alert.status === 'resolved');
    if (filter === 'coordination') return alerts.filter((alert) => alert.kind === 'coordination');
    return alerts.filter((alert) => alert.status !== 'resolved');
  }, [alerts, filter]);

  const figure = (value: number) => (isLoading ? '…' : value);
  const coordination = open.filter((alert) => alert.kind === 'coordination').length;
  const undelivered = open.filter((alert) => alert.delivered_at === null).length;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-6 px-4 pb-16 pt-6 sm:px-6 lg:pt-8">
        <PageHeader
          eyebrow={`Step 3 · Act · ${current?.label ?? '…'}`}
          title="Authority console"
          description="Each episode is routed once, to the district whose boundary holds it; when its likeliest source lies across a boundary, that jurisdiction is asked to act as well. Alerts are ordered by how far above its neighbourhood each sits, not by concentration."
          actions={
            isOperator && (
              <Button
                variant="primary"
                size="md"
                isBusy={isBusy}
                busyLabel="Working…"
                onClick={() => {
                  void dispatch().then(setLastDispatch);
                }}
              >
                Run detection
              </Button>
            )
          }
        />

        <OperatorSignIn />

        <dl className="grid grid-cols-2 gap-y-5 rounded-card border border-border bg-surface p-4 sm:p-5 lg:grid-cols-4">
          <Stat
            label="Open"
            value={figure(open.length)}
            note="Awaiting an authority"
            tone={open.length > 0 ? 'warn' : 'neutral'}
          />
          <Stat
            label="Past deadline"
            value={figure(overdueIds.size)}
            note="Sent and never answered"
            tone={overdueIds.size > 0 ? 'danger' : 'neutral'}
          />
          <Stat
            label="Across a boundary"
            value={figure(coordination)}
            note="Neighbours asked to act on a source"
            tone={coordination > 0 ? 'signal' : 'neutral'}
          />
          <Stat
            label="Not delivered"
            value={figure(undelivered)}
            note="Recorded, nobody told yet"
            tone={undelivered > 0 ? 'warn' : 'neutral'}
          />
        </dl>

        {lastDispatch && (
          <p
            role="status"
            className="figure rounded-sm border border-border bg-surface px-3 py-2 text-xs text-ink-muted"
          >
            {lastDispatch.detected} detected · {lastDispatch.raised} raised (
            {lastDispatch.coordination_requests} across a boundary) · {lastDispatch.suppressed}{' '}
            already in flight · {lastDispatch.unrouted} unrouted
          </p>
        )}

        <div className="scroll-row -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <SegmentedControl
            label="Filter alerts"
            options={FILTERS}
            value={filter}
            onChange={setFilter}
          />
        </div>

        {error ? (
          <StatusMessage
            kind="error"
            title="Could not load the alert inbox"
            detail={`${error.message} An empty console here would mean the request failed, not that nothing needs attention.`}
            {...(error.requestId ? { requestId: error.requestId } : {})}
          />
        ) : isLoading ? (
          <Skeleton label="Loading alerts" rows={5} />
        ) : visible.length === 0 ? (
          <StatusMessage
            kind="empty"
            title={filter === 'open' ? 'No open alerts' : 'Nothing matches this filter'}
            {...(filter === 'open'
              ? {
                  detail:
                    'No detected episode is waiting on an authority in this city. In a city with too few monitors to detect anything, that is a gap in coverage rather than good news.',
                }
              : {})}
          />
        ) : (
          <ul className="space-y-3">
            {visible.map((alert) => (
              <li key={alert.alert_id}>
                <AlertCard
                  alert={alert}
                  isOverdue={overdueIds.has(alert.alert_id)}
                  isBusy={isBusy}
                  canAct={isOperator}
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
