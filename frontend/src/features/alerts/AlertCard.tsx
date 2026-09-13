import { Clock } from 'lucide-react';
import { useId, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import type { Alert } from '@/hooks/useAlerts';
import { istDateTime } from '@/lib/time';

interface AlertCardProps {
  readonly alert: Alert;
  readonly isOverdue: boolean;
  readonly isBusy: boolean;
  /** False for a read-only viewer: the trail is shown, the actions are not. */
  readonly canAct?: boolean;
  readonly onAcknowledge: (alertId: number) => void;
  readonly onResolve: (alertId: number, note: string) => void;
}

/** Tone per lifecycle state. Carries meaning, so it is not chosen for looks. */
const STATUS_TONES = {
  sent: 'danger',
  acknowledged: 'warn',
  resolved: 'ok',
  escalated: 'accent',
} as const;

/**
 * One alert in the console.
 *
 * The headline is the comparison, never the bare concentration. "381 where 40
 * was expected" tells an inspector there is something at this location to find;
 * "381" on a bad day describes half the city and points at nothing.
 *
 * Resolution requires a note, enforced here and again on the server. A
 * resolution with no explanation records that someone clicked a button, which is
 * not the same as recording that something was done — and the difference is the
 * entire value of the trail.
 *
 * Overdue alerts get a red edge and a one-line marker rather than a red fill.
 * When most of the inbox is overdue — the normal state of an ignored queue —
 * filling every card makes the whole list one undifferentiated alarm and
 * nothing in it can be scanned.
 *
 * Delivery is shown separately from recording. An alert that exists in the trail
 * but reached nobody is a different finding from one that was delivered and
 * ignored, and an operator chasing the second should not be shown the first.
 */
export function AlertCard({
  alert,
  isOverdue,
  isBusy,
  canAct = true,
  onAcknowledge,
  onResolve,
}: AlertCardProps) {
  const [note, setNote] = useState('');
  const [isResolving, setIsResolving] = useState(false);
  const noteId = useId();

  const isResolved = alert.status === 'resolved';
  const canResolve = note.trim().length > 0 && !isBusy;
  const tone = STATUS_TONES[alert.status];

  return (
    <article
      className={`rounded-card border border-l-4 border-border bg-surface p-5 shadow-card ${
        isOverdue ? 'border-l-danger' : 'border-l-border'
      }`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-ink">
            {alert.station_name ?? 'Unmonitored location'}
          </h3>
          <p className="truncate text-xs text-ink-muted">{alert.authority_name}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge tone={tone} dot>
            {alert.status}
          </Badge>
          {alert.delivered_at === null && !isResolved && (
            <span className="text-xs text-ink-subtle" title="Recorded, but no endpoint accepted it">
              not delivered
            </span>
          )}
        </div>
      </header>

      <p className="mt-2.5 text-sm leading-relaxed text-ink">
        <strong className="text-base font-semibold">{alert.peak_observed.toFixed(0)} µg/m³</strong>{' '}
        where the surrounding network predicted <strong>{alert.peak_expected.toFixed(0)}</strong> —
        an excess of <strong>{alert.peak_excess.toFixed(0)} µg/m³</strong>
      </p>
      <p className="mt-1 text-xs text-ink-muted">
        {alert.peak_z.toFixed(1)}× the expected error here · first seen{' '}
        {istDateTime(alert.first_seen_at)} IST
      </p>

      {isOverdue && (
        <p
          className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-danger"
          title="An alert sent and never answered is itself a finding."
        >
          <Clock aria-hidden className="size-3.5" />
          Past its response deadline
        </p>
      )}

      {alert.delivery_error !== null && alert.delivery_error !== undefined && (
        <p className="mt-2 rounded-md bg-warn-subtle px-2.5 py-1.5 text-xs text-warn">
          Delivery failed: {alert.delivery_error}. It stays queued.
        </p>
      )}

      {alert.resolution_note !== null && alert.resolution_note !== undefined && (
        <p className="mt-2.5 rounded-md bg-ok-subtle px-2.5 py-1.5 text-xs leading-relaxed text-ok">
          <span className="font-medium">Resolved:</span> {alert.resolution_note}
        </p>
      )}

      {canAct && !isResolved && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {alert.status === 'sent' && (
            <Button
              isBusy={isBusy}
              busyLabel="Working…"
              onClick={() => {
                onAcknowledge(alert.alert_id);
              }}
            >
              Acknowledge
            </Button>
          )}
          <Button
            variant={isResolving ? 'ghost' : 'secondary'}
            disabled={isBusy}
            aria-expanded={isResolving}
            aria-controls={noteId}
            onClick={() => {
              setIsResolving((open) => !open);
            }}
          >
            {isResolving ? 'Cancel' : 'Resolve'}
          </Button>
        </div>
      )}

      {canAct && isResolving && !isResolved && (
        <div id={noteId} className="mt-3 rounded-md border border-border bg-surface-sunken p-3">
          <label className="block text-xs font-medium text-ink" htmlFor={`${noteId}-field`}>
            What was found or done?{' '}
            <span className="font-normal text-ink-muted">
              Required — a resolution with no explanation records only that a button was pressed.
            </span>
          </label>
          <textarea
            id={`${noteId}-field`}
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
            }}
            rows={3}
            className="mt-1.5 w-full rounded-md border border-border-strong bg-surface p-2 text-sm text-ink placeholder:text-ink-subtle"
            placeholder="e.g. Open waste burning behind the terminal, extinguished and fined."
          />
          <Button
            variant="primary"
            size="md"
            disabled={!canResolve}
            onClick={() => {
              onResolve(alert.alert_id, note);
              setIsResolving(false);
              setNote('');
            }}
          >
            Close alert
          </Button>
        </div>
      )}
    </article>
  );
}
