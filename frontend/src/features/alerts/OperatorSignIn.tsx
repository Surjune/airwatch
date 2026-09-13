import { KeyRound, LogOut } from 'lucide-react';
import { useId, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { ApiError } from '@/lib/api-client';
import { useOperator } from '@/lib/operator';

/**
 * Sign in as an operator, or see that you are one.
 *
 * Anyone may read the console; only an operator may acknowledge, resolve or run
 * detection, because each of those writes to the record an official is held to.
 */
export function OperatorSignIn() {
  const { isOperator, signIn, signOut } = useOperator();
  const [isOpen, setIsOpen] = useState(false);
  const [key, setKey] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const fieldId = useId();

  if (isOperator) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-ok/30 bg-ok-subtle px-3 py-2 text-sm text-ok">
        <KeyRound aria-hidden className="size-4" />
        <span className="font-medium">Signed in as operator</span>
        <Button variant="ghost" onClick={signOut}>
          <LogOut aria-hidden className="size-3.5" />
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-muted">
          Read-only. Operators sign in to acknowledge, resolve and run detection.
        </p>
        {!isOpen && (
          <Button
            onClick={() => {
              setIsOpen(true);
            }}
          >
            <KeyRound aria-hidden className="size-3.5" />
            Operator sign in
          </Button>
        )}
      </div>

      {isOpen && (
        <form
          className="mt-2.5 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setIsChecking(true);
            setProblem(null);
            signIn(key)
              .then(() => {
                setKey('');
                setIsOpen(false);
              })
              .catch((cause: unknown) => {
                setProblem(
                  cause instanceof ApiError && cause.status === 403
                    ? 'Operator actions are disabled on this deployment.'
                    : 'That key was not accepted.',
                );
              })
              .finally(() => {
                setIsChecking(false);
              });
          }}
        >
          <label className="min-w-64 flex-1" htmlFor={fieldId}>
            <span className="text-xs font-medium text-ink-muted">Operator key</span>
            <input
              id={fieldId}
              type="password"
              autoComplete="off"
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
              }}
              className="mt-1 w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
            />
          </label>
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={key.trim() === ''}
            isBusy={isChecking}
            busyLabel="Checking…"
          >
            Sign in
          </Button>
          {problem && (
            <p role="alert" className="w-full text-xs text-danger">
              {problem}
            </p>
          )}
        </form>
      )}
    </div>
  );
}
