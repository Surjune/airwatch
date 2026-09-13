import { useCallback, useEffect, useRef, useState } from 'react';

import { apiUrl } from '@/lib/api-client';
import type { GuideSection } from '@/lib/guide';

export type PlayerStatus = 'idle' | 'loading' | 'playing' | 'paused' | 'error';

export interface GuidePlayer {
  readonly status: PlayerStatus;
  /** The paragraph being spoken, or the one that will be spoken next. */
  readonly current: number;
  /** How far through the current paragraph, from 0 to 1. */
  readonly progress: number;
  readonly play: (index?: number) => void;
  readonly pause: () => void;
}

/**
 * Speak a guide one paragraph after another, through a single audio element.
 *
 * One clip per paragraph rather than one per screen, so the transcript can show
 * which paragraph is being read, a listener can jump to the part they need, and
 * the first words play without waiting for the whole guide to be generated.
 * The next paragraph is requested as the current one starts, so the pause
 * between them is the speaker's, not the network's.
 */
export function useGuidePlayer(sections: readonly GuideSection[]): GuidePlayer {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sectionsRef = useRef(sections);
  const currentRef = useRef(0);
  const [status, setStatus] = useState<PlayerStatus>('idle');
  const [current, setCurrent] = useState(0);
  const [progress, setProgress] = useState(0);

  const load = useCallback((index: number) => {
    const audio = audioRef.current;
    const section = sectionsRef.current[index];
    if (!audio || !section) return false;
    currentRef.current = index;
    setCurrent(index);
    setProgress(0);
    audio.src = apiUrl(section.audio_path);
    const next = sectionsRef.current[index + 1];
    if (next) {
      const warm = new Audio();
      warm.preload = 'auto';
      warm.src = apiUrl(next.audio_path);
    }
    return true;
  }, []);

  const start = useCallback((audio: HTMLAudioElement) => {
    setStatus('loading');
    audio.play().catch((cause: unknown) => {
      // Moving to another paragraph abandons the previous play request, which
      // is the listener's choice rather than a failure.
      if (cause instanceof DOMException && cause.name === 'AbortError') return;
      // A browser that only lets sound start from a tap refuses a guide that
      // starts itself. That waits for the play button; it is not a broken clip.
      if (cause instanceof DOMException && cause.name === 'NotAllowedError') {
        setStatus('idle');
        return;
      }
      setStatus('error');
    });
  }, []);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = 'none';
    audioRef.current = audio;

    const onPlaying = () => {
      setStatus('playing');
    };
    const onWaiting = () => {
      setStatus('loading');
    };
    const onPause = () => {
      // Only a clip that was under way can be paused; a pause that arrives after
      // a failure or a reset must not turn either into "paused".
      if (!audio.ended) {
        setStatus((previous) =>
          previous === 'playing' || previous === 'loading' ? 'paused' : previous,
        );
      }
    };
    const onTime = () => {
      if (audio.duration > 0) setProgress(audio.currentTime / audio.duration);
    };
    const onError = () => {
      setStatus('error');
    };
    const onEnded = () => {
      if (load(currentRef.current + 1)) {
        start(audio);
        return;
      }
      // The guide has finished; the next press starts it from the top.
      load(0);
      setStatus('idle');
    };

    audio.addEventListener('playing', onPlaying);
    audio.addEventListener('waiting', onWaiting);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('error', onError);
    audio.addEventListener('ended', onEnded);
    return () => {
      audio.pause();
      audio.removeAttribute('src');
      audio.removeEventListener('playing', onPlaying);
      audio.removeEventListener('waiting', onWaiting);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('error', onError);
      audio.removeEventListener('ended', onEnded);
      audioRef.current = null;
    };
  }, [load, start]);

  // Another screen or language is another guide: stop, and start from its beginning.
  useEffect(() => {
    sectionsRef.current = sections;
    audioRef.current?.pause();
    audioRef.current?.removeAttribute('src');
    currentRef.current = 0;
    setCurrent(0);
    setProgress(0);
    setStatus('idle');
  }, [sections]);

  const play = useCallback(
    (index?: number) => {
      const audio = audioRef.current;
      if (!audio) return;
      const target = index ?? currentRef.current;
      // Resume only a clip that was genuinely under way; after a failure, or
      // before anything played, load the paragraph afresh.
      const resuming =
        index === undefined &&
        audio.getAttribute('src') !== null &&
        audio.currentTime > 0 &&
        !audio.ended &&
        audio.error === null;
      if (!resuming && !load(target)) return;
      start(audio);
    },
    [load, start],
  );

  const pause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  return { status, current, progress, play, pause };
}
