import { useState } from 'react';

import type { Alert } from '@/hooks/useAlerts';

interface AlertCardProps {
  readonly alert: Alert;
  readonly isOverdue: boolean;
  readonly isBusy: boolean;
  readonly onAcknowledge: (alertId: number) => void;
  readonly onResolve: (alertId: number, note: string) => void;
}

const STATUS_STYLES: Record<string, string> = {
  sent: 'bg-red-100 text-red-800',
  acknowledged: 'bg-amber-100 text-amber-900',
  resolved: 'bg-emerald-100 text-emerald-800',
  escalated: 'bg-purple-100 text-purple-900',
};

const FALLBACK_STATUS_STYLE = 'bg-neutral-100 text-neutral-700';

/** Render a UTC timestamp in IST, which is the only timezone an operator here reads. */
function istTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * One alert in the console.
 *
 * The headline is the comparison, never the bare concentration. "381 where 40
 * was expected" tells an inspector there is something at this location to find;
 * "381" on a bad day describes half the city and points at nothing.
 *
 * Resolution requires a note, enforced here and again on the server. A
 * resolution with no explanation records that someone clicked a button, which is
 * not the same as recording that something was done -- and the difference is the
 * entire value of the trail.
 */
export function AlertCard({
  alert,
  isOverdue,
  isBusy,
  onAcknowledge,
  onResolve,
}: AlertCardProps) {
  const [note, setNote] = useState('');
  const [isResolving, setIsResolving] = useState(false);

  const isResolved = alert.status === 'resolved';
  const canResolve = note.trim().length > 0 && !isBusy;

  return (
    <article
      className={`border-b border-neutral-200 p-4 ${isOverdue ? 'bg-red-50/60' : 'bg-white'}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">
            {alert.station_name ?? 'Unmonitored location'}
          </h3>
          <p className="truncate text-xs text-neutral-600">{alert.authority_name}</p>
        </div>
        <span
          className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
            STATUS_STYLES[alert.status] ?? FALLBACK_STATUS_STYLE
          }`}
        >
          {alert.status}
        </span>
      </header>

      <p className="mt-2 text-sm">
        <strong>{alert.peak_observed.toFixed(0)} µg/m³</strong> where the surrounding network
        predicted <strong>{alert.peak_expected.toFixed(0)}</strong> — an excess of{' '}
        <strong>{alert.peak_excess.toFixed(0)} µg/m³</strong>
      </p>
      <p className="mt-1 text-xs text-neutral-600">
        {alert.peak_z.toFixed(1)}× the expected error here · first seen {istTime(alert.first_seen_at)}{' '}
        IST
      </p>

      {isOverdue && (
        <p className="mt-2 rounded bg-red-100 px-2 py-1 text-xs font-medium text-red-800">
          Past its response deadline. An alert sent and never answered is itself a finding.
        </p>
      )}

      {alert.resolution_note && (
        <p className="mt-2 rounded bg-emerald-50 px-2 py-1 text-xs text-emerald-900">
          <span className="font-medium">Resolved:</span> {alert.resolution_note}
        </p>
      )}

      {!isResolved && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {alert.status === 'sent' && (
            <button
              type="button"
              disabled={isBusy}
              onClick={() => {
                onAcknowledge(alert.alert_id);
              }}
              className="rounded border border-neutral-300 px-3 py-1 text-xs font-medium hover:bg-neutral-50 disabled:opacity-50"
            >
              Acknowledge
            </button>
          )}
          <button
            type="button"
            disabled={isBusy}
            onClick={() => {
              setIsResolving((open) => !open);
            }}
            className="rounded border border-neutral-300 px-3 py-1 text-xs font-medium hover:bg-neutral-50 disabled:opacity-50"
          >
            {isResolving ? 'Cancel' : 'Resolve'}
          </button>
        </div>
      )}

      {isResolving && !isResolved && (
        <div className="mt-2">
          <label className="block text-xs text-neutral-600" htmlFor={`note-${String(alert.alert_id)}`}>
            What was found or done? Required.
          </label>
          <textarea
            id={`note-${String(alert.alert_id)}`}
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
            }}
            rows={2}
            className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm"
            placeholder="e.g. Open waste burning behind the terminal, extinguished and fined."
          />
          <button
            type="button"
            disabled={!canResolve}
            onClick={() => {
              onResolve(alert.alert_id, note);
              setIsResolving(false);
              setNote('');
            }}
            className="mt-2 rounded bg-neutral-800 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-40"
          >
            Close alert
          </button>
        </div>
      )}
    </article>
  );
}
