import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { get } from '@/lib/api-client';
import { OperatorContext, type OperatorSession } from '@/lib/operator';
import { clearOperatorToken, getOperatorToken, setOperatorToken } from '@/lib/operator-token';

/**
 * Holds the operator session for the tab.
 *
 * A stored key is trusted for display only; the server checks it on every write,
 * so a key revoked on the server simply turns the next action into a 401.
 */
export function OperatorProvider({ children }: { readonly children: ReactNode }) {
  const [isOperator, setIsOperator] = useState(() => getOperatorToken() !== null);

  const signIn = useCallback(async (key: string) => {
    setOperatorToken(key.trim());
    try {
      await get('/operator/session');
      setIsOperator(true);
    } catch (error) {
      clearOperatorToken();
      setIsOperator(false);
      throw error;
    }
  }, []);

  const signOut = useCallback(() => {
    clearOperatorToken();
    setIsOperator(false);
  }, []);

  const session = useMemo<OperatorSession>(
    () => ({ isOperator, signIn, signOut }),
    [isOperator, signIn, signOut],
  );

  return <OperatorContext.Provider value={session}>{children}</OperatorContext.Provider>;
}
