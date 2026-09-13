import { useEffect, useState } from 'react';

import type { ScreenKey } from '@/components/layout/navigation';
import { ApiError, get } from '@/lib/api-client';
import type { Guide, GuideLanguage } from '@/lib/guide';

export interface GuideState {
  readonly data: Guide | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
}

/**
 * The transcript of a screen's spoken guide, in one language.
 *
 * Fetched only while the guide is open, so a visitor who never asks for it costs
 * the API nothing.
 */
export function useGuide(screen: ScreenKey, language: GuideLanguage, enabled: boolean): GuideState {
  const [state, setState] = useState<GuideState>({ data: null, error: null, isLoading: false });

  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    setState({ data: null, error: null, isLoading: true });
    get<Guide>(`/guide/${screen}`, { signal: controller.signal, searchParams: { language } })
      .then((data) => {
        setState({ data, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error:
            cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0),
          isLoading: false,
        });
      });
    return () => {
      controller.abort();
    };
  }, [screen, language, enabled]);

  return state;
}
