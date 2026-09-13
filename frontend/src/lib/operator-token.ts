/**
 * Where the operator key is kept in the browser.
 *
 * sessionStorage, not localStorage: the key ends with the tab, so a shared
 * computer in a municipal office does not stay signed in for the next person.
 * Every access is guarded because storage can be unavailable (private windows,
 * blocked site data), and then the console simply stays read-only.
 */
const STORAGE_KEY = 'airwatch.operator';

export function getOperatorToken(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setOperatorToken(token: string): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Without storage the key cannot persist across reloads; the action in hand
    // still fails closed with a 401 rather than acting anonymously.
  }
}

export function clearOperatorToken(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
