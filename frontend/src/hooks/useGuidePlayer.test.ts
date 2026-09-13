import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { GuideSection } from '@/lib/guide';

import { useGuidePlayer } from './useGuidePlayer';

/** Every audio element the hook creates, newest last. */
const created: FakeAudio[] = [];

/**
 * Enough of HTMLAudioElement for the player, which jsdom cannot play.
 *
 * `play` resolves and announces playback, as a browser does once a clip starts;
 * a test ends a clip or fails it by dispatching the event a browser would.
 */
class FakeAudio extends EventTarget {
  preload = '';
  currentTime = 0;
  duration = 0;
  ended = false;
  error: MediaError | null = null;
  playResult: Promise<void> = Promise.resolve();
  private source: string | null = null;

  constructor() {
    super();
    created.push(this);
  }

  get src(): string {
    return this.source ?? '';
  }

  set src(value: string) {
    this.source = value;
    this.currentTime = 0;
    this.ended = false;
  }

  getAttribute(name: string): string | null {
    return name === 'src' ? this.source : null;
  }

  removeAttribute(name: string): void {
    if (name === 'src') this.source = null;
  }

  play(): Promise<void> {
    const result = this.playResult;
    result.then(
      () => {
        this.dispatchEvent(new Event('playing'));
      },
      () => undefined,
    );
    return result;
  }

  pause(): void {
    this.dispatchEvent(new Event('pause'));
  }

  finish(): void {
    this.ended = true;
    this.dispatchEvent(new Event('ended'));
  }
}

const SECTIONS: GuideSection[] = [0, 1, 2].map((index) => ({
  index,
  heading: `Part ${String(index)}`,
  text: 'Words.',
  audio_path: `/guide/map/sections/${String(index)}/audio?language=hi&v=abc`,
}));

/** The element doing the speaking: the first one the hook made. */
function player(): FakeAudio {
  const audio = created[0];
  if (!audio) throw new Error('no audio element was created');
  return audio;
}

beforeEach(() => {
  created.length = 0;
  vi.stubGlobal('Audio', FakeAudio);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useGuidePlayer', () => {
  it('starts with the first paragraph', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));

    await act(async () => {
      result.current.play();
      await Promise.resolve();
    });

    expect(player().src).toBe('/v1/guide/map/sections/0/audio?language=hi&v=abc');
    expect(result.current.status).toBe('playing');
    expect(result.current.current).toBe(0);
  });

  it('moves on to the next paragraph when one ends, and asks for the one after early', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));
    await act(async () => {
      result.current.play();
      await Promise.resolve();
    });

    await act(async () => {
      player().finish();
      await Promise.resolve();
    });

    expect(result.current.current).toBe(1);
    expect(player().src).toContain('/sections/1/');
    // A second element was made to fetch paragraph 2 before it is needed.
    expect(created.some((audio) => audio !== player() && audio.src.includes('/sections/2/'))).toBe(
      true,
    );
  });

  it('returns to the start once the last paragraph ends', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));
    await act(async () => {
      result.current.play(2);
      await Promise.resolve();
    });

    act(() => {
      player().finish();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.current).toBe(0);
  });

  it('plays from a paragraph chosen directly', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));

    await act(async () => {
      result.current.play(1);
      await Promise.resolve();
    });

    expect(result.current.current).toBe(1);
    expect(player().src).toContain('/sections/1/');
  });

  it('reports a clip that cannot load', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));
    await act(async () => {
      result.current.play();
      await Promise.resolve();
    });

    act(() => {
      player().dispatchEvent(new Event('error'));
    });

    expect(result.current.status).toBe('error');
  });

  it('does not call it a failure when a browser waits for a tap to make sound', async () => {
    const { result } = renderHook(() => useGuidePlayer(SECTIONS));
    player().playResult = Promise.reject(new DOMException('needs a gesture', 'NotAllowedError'));

    await act(async () => {
      result.current.play();
      await Promise.resolve();
    });

    expect(result.current.status).toBe('idle');
  });

  it('starts another guide from its beginning', async () => {
    const { result, rerender } = renderHook(({ sections }) => useGuidePlayer(sections), {
      initialProps: { sections: SECTIONS },
    });
    await act(async () => {
      result.current.play(2);
      await Promise.resolve();
    });

    rerender({ sections: SECTIONS.slice(0, 2) });

    expect(result.current.status).toBe('idle');
    expect(result.current.current).toBe(0);
    expect(player().getAttribute('src')).toBeNull();
  });
});
