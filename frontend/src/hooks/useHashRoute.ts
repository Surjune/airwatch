import { useCallback, useEffect, useState } from 'react';

/**
 * Read the current screen from the URL hash, and change it.
 *
 * The screen lives in the URL so a view can be bookmarked, shared with a
 * colleague ("look at #/alerts"), reloaded without losing place, and left with
 * the browser's back button -- none of which worked while it was component
 * state. A hash rather than a path needs no server rewrite rule, so the static
 * build deploys anywhere unchanged.
 *
 * An unrecognised hash falls back to the default rather than rendering nothing.
 */
export function useHashRoute<K extends string>(
  keys: readonly K[],
  fallback: K,
): readonly [K, (next: K) => void] {
  const parse = useCallback((): K => {
    const raw = window.location.hash.replace(/^#\/?/, '');
    return (keys as readonly string[]).includes(raw) ? (raw as K) : fallback;
  }, [keys, fallback]);

  const [route, setRoute] = useState<K>(parse);

  useEffect(() => {
    const onChange = () => {
      setRoute(parse());
    };
    window.addEventListener('hashchange', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
    };
  }, [parse]);

  const navigate = useCallback((next: K) => {
    window.location.hash = `/${next}`;
  }, []);

  return [route, navigate] as const;
}
