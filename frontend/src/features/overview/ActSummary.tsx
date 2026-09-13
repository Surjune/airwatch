import { ArrowRight } from 'lucide-react';

import type { ScreenKey } from '@/components/layout/navigation';
import { Button } from '@/components/ui/Button';
import { Stat } from '@/components/ui/Stat';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { AlertConsole } from '@/hooks/useAlerts';

/**
 * The accountability trail for this city in four figures.
 *
 * Four different questions, deliberately not collapsed: how many are waiting, how
 * many were ignored past their deadline, how many asked a neighbouring
 * jurisdiction to act on a source on its ground, and how many reached nobody.
 */
export function ActSummary({
  alerts,
  onNavigate,
}: {
  readonly alerts: AlertConsole;
  readonly onNavigate: (key: ScreenKey) => void;
}) {
  if (alerts.error) {
    return (
      <StatusMessage
        kind="error"
        title="Alert trail unavailable"
        detail={`${alerts.error.message} Zero open alerts here would mean the request failed, not that nothing needs attention.`}
      />
    );
  }

  const open = alerts.alerts.filter((alert) => alert.status !== 'resolved');
  const figure = (value: number) => (alerts.isLoading ? '…' : value);
  const coordination = open.filter((alert) => alert.kind === 'coordination').length;
  const undelivered = open.filter((alert) => alert.delivered_at === null).length;

  return (
    <div className="rounded-card border border-border bg-surface p-4 sm:p-5">
      <dl className="grid grid-cols-2 gap-y-5 lg:grid-cols-4">
        <Stat
          label="Open alerts"
          value={figure(open.length)}
          note="Routed to an authority, not yet resolved"
          tone={open.length > 0 ? 'warn' : 'neutral'}
        />
        <Stat
          label="Past deadline"
          value={figure(alerts.breaches.length)}
          note="Sent, and never answered in time"
          tone={alerts.breaches.length > 0 ? 'danger' : 'neutral'}
        />
        <Stat
          label="Across a boundary"
          value={figure(coordination)}
          note="Neighbours asked to act on a source on their ground"
          tone={coordination > 0 ? 'signal' : 'neutral'}
        />
        <Stat
          label="Not delivered"
          value={figure(undelivered)}
          note="Recorded, but nobody has been told yet"
          tone={undelivered > 0 ? 'warn' : 'neutral'}
        />
      </dl>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <p className="max-w-xl text-[13px] leading-relaxed text-ink-muted">
          Each alert goes to the district whose boundary holds the hotspot. When the likeliest
          upwind source sits across a boundary, that jurisdiction is asked to act too.
        </p>
        <Button
          variant="primary"
          size="md"
          onClick={() => {
            onNavigate('alerts');
          }}
        >
          Open the authority console
          <ArrowRight aria-hidden className="size-4" />
        </Button>
      </div>
    </div>
  );
}
