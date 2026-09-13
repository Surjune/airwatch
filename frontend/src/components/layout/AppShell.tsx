import { BookOpen } from 'lucide-react';
import type { ReactNode } from 'react';

import { ApiStatus } from '@/components/layout/ApiStatus';
import { CityPicker } from '@/components/layout/CityPicker';
import { Logo } from '@/components/layout/Logo';
import { screenFor, type ScreenKey } from '@/components/layout/navigation';
import { PrimaryNav } from '@/components/layout/PrimaryNav';
import { BandRule } from '@/components/ui/BandRule';

interface AppShellProps {
  readonly active: ScreenKey;
  readonly onNavigate: (key: ScreenKey) => void;
  readonly children: ReactNode;
}

/**
 * The frame every screen sits in.
 *
 * On a desktop, one masthead carries the wordmark, the screens as tabs, the city
 * and the connection state. On a phone the screens move to a bottom bar within
 * thumb reach, and the masthead keeps only what must stay visible: which city,
 * and whether the data is live. The city is never tucked behind a menu, because
 * every number on every screen depends on it.
 */
export function AppShell({ active, onNavigate, children }: AppShellProps) {
  const screen = screenFor(active);

  return (
    <div className="flex h-dvh flex-col bg-paper text-ink">
      <a
        href="#main"
        className="sr-only z-[1300] rounded-sm bg-ink px-3 py-2 text-sm text-paper focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      <header className="relative z-[1100] shrink-0 bg-surface">
        <div className="flex h-14 items-stretch gap-3 border-b border-border px-3 sm:px-5">
          <a
            href="#/overview"
            onClick={(event) => {
              event.preventDefault();
              onNavigate('overview');
            }}
            className="flex shrink-0 items-center gap-2 text-ink"
          >
            <Logo className="size-6" />
            <span className="text-[17px] font-semibold tracking-tight">AirWatch</span>
          </a>

          <div className="hidden min-w-0 flex-1 items-stretch pl-4 lg:flex">
            <PrimaryNav active={active} onNavigate={onNavigate} variant="bar" />
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-3">
            <CityPicker />
            <ApiStatus />
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink xl:inline-flex"
            >
              <BookOpen aria-hidden className="size-3.5" />
              API
            </a>
          </div>
        </div>
        <BandRule />
      </header>

      <main id="main" className="min-h-0 flex-1 overflow-hidden" aria-label={screen.label}>
        {children}
      </main>

      <div className="relative z-[1100] shrink-0 lg:hidden">
        <PrimaryNav active={active} onNavigate={onNavigate} variant="dock" />
      </div>
    </div>
  );
}
