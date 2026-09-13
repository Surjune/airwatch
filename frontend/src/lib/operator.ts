import { createContext, useContext } from 'react';

/** Whether this browser session may act on the accountability trail. */
export interface OperatorSession {
  readonly isOperator: boolean;
  /** Verifies a key with the API and keeps it for the session if valid. */
  readonly signIn: (key: string) => Promise<void>;
  readonly signOut: () => void;
}

export const OperatorContext = createContext<OperatorSession | null>(null);

/** The operator session. Throws outside its provider rather than guessing. */
export function useOperator(): OperatorSession {
  const session = useContext(OperatorContext);
  if (!session) throw new Error('useOperator must be used inside OperatorProvider.');
  return session;
}
