import { Clock } from 'lucide-react';
import { useId, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { AlertBriefPanel } from '@/features/alerts/AlertBriefPanel';
import type { Alert } from '@/hooks/useAlerts';
import { pollutantLabel } from '@/lib/scope';
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
 * A coordination request says so first, because it asks something different of
 * its reader: the hotspot is on a neighbour's ground, and what is being asked is
 * an inspection of the source on theirs.
 *
 * Resolution requires a note, enforced here and again on the server. Overdue
 * alerts get an edge and a one-line marker rather than a red fill, so an inbox
 * that is mostly overdue can still be scanned.
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
  const isCoordination = alert.kind === 'coordination';
  const canResolve = note.trim().length > 0 && !isBusy;

  return (
    <article
      className={`rounded-card border border-l-[3px] border-border bg-surface p-4 sm:p-5 ${
        isOverdue
          ? 'border-l-danger'
          : isCoordination
            ? 'border-l-signal'
            : 'border-l-border-strong'
      }`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">
            {isCoordination ? 'Coordination request' : 'Hotspot alert'} ·{' '}
            {pollutantLabel(alert.pollutant)} · #{alert.alert_id}
          </p>
          <h3 className="mt-0.5 truncate text-[15px] font-semibold text-ink">
            {alert.station_name ?? 'Unmonitored location'}
          </h3>
          <p className="truncate text-xs text-ink-muted">To {alert.authority_name}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge tone={STATUS_TONES[alert.status]} dot>
            {alert.status}
          </Badge>
          {alert.delivered_at === null && !isResolved && (
            <span
              className="text-[11px] text-ink-subtle"
              title="Recorded, but no endpoint accepted it"
            >
              not delivered
            </span>
          )}
        </div>
      </header>

      {isCoordination && (
        <p className="mt-3 border-l-2 border-signal/40 pl-3 text-[13px] leading-relaxed text-ink">
          The hotspot is in a neighbouring jurisdiction. Its likeliest upwind source,{' '}
          <span className="font-semibold">{alert.source_name ?? 'unnamed'}</span>
          {alert.source_confidence != null && (
            <span className="figure text-ink-muted">
              {' '}
              ({(alert.source_confidence * 100).toFixed(0)}% plausible)
            </span>
          )}
          , is on your ground. A ranked candidate, not an established cause.
        </p>
      )}

      <p className="mt-3 text-sm leading-relaxed text-ink">
        <strong className="figure text-base font-medium">
          {alert.peak_observed.toFixed(0)} µg/m³
        </strong>{' '}
        where the surrounding network predicted{' '}
        <strong className="figure font-medium">{alert.peak_expected.toFixed(0)}</strong> — an excess
        of <strong className="figure font-medium">{alert.peak_excess.toFixed(0)} µg/m³</strong>
      </p>
      <p className="figure mt-1 text-[11px] text-ink-subtle">
        {alert.peak_z.toFixed(1)}× the expected error · first seen{' '}
        {istDateTime(alert.first_seen_at)} IST
      </p>

      <AlertBriefPanel alertId={alert.alert_id} />

      {isOverdue && (
        <p
          className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-danger"
          title="An alert sent and never answered is itself a finding."
        >
          <Clock aria-hidden className="size-3.5" />
          Past its response deadline
        </p>
      )}

      {alert.delivery_error != null && (
        <p className="mt-2 rounded-sm bg-warn-subtle px-2.5 py-1.5 text-xs text-warn">
          Delivery failed: {alert.delivery_error}. It stays queued.
        </p>
      )}

      {alert.resolution_note != null && (
        <p className="mt-3 rounded-sm bg-ok-subtle px-2.5 py-1.5 text-xs leading-relaxed text-ok">
          <span className="font-semibold">Resolved:</span> {alert.resolution_note}
        </p>
      )}

      {canAct && !isResolved && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
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
        <div id={noteId} className="mt-3 rounded-sm border border-border bg-paper p-3">
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
            className="mt-1.5 w-full rounded-sm border border-border-strong bg-surface p-2 text-sm text-ink placeholder:text-ink-subtle"
            placeholder="e.g. Open waste burning behind the terminal, extinguished and fined."
          />
          <div className="mt-2">
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
        </div>
      )}
    </article>
  );
}
