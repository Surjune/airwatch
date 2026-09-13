import { Menu, X } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';

import { Logo } from '@/components/layout/Logo';
import { SCREENS, type ScreenKey } from '@/components/layout/navigation';
import { Sidebar } from '@/components/layout/Sidebar';

interface AppShellProps {
  readonly active: ScreenKey;
  readonly onNavigate: (key: ScreenKey) => void;
  readonly children: ReactNode;
}

/**
 * The frame every screen sits in: a fixed sidebar on wide screens, and a top
 * bar with a slide-over menu on narrow ones, where a sidebar would take the
 * width the map needs.
 */
export function AppShell({ active, onNavigate, children }: AppShellProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const label = SCREENS.find((candidate) => candidate.key === active)?.label ?? 'AirWatch';

  useEffect(() => {
    if (!isMenuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [isMenuOpen]);

  const navigate = (key: ScreenKey) => {
    setIsMenuOpen(false);
    onNavigate(key);
  };

  return (
    <div className="flex h-dvh bg-surface-sunken">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-accent px-3 py-2 text-sm text-white focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      <aside className="hidden w-64 shrink-0 lg:block">
        <Sidebar active={active} onNavigate={navigate} />
      </aside>

      {isMenuOpen && (
        <div
          className="fixed inset-0 z-[1100] lg:hidden"
          role="dialog"
          aria-modal
          aria-label="Menu"
        >
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/40"
            onClick={() => {
              setIsMenuOpen(false);
            }}
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] shadow-overlay">
            <Sidebar active={active} onNavigate={navigate} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-chrome-border bg-chrome px-3 text-chrome-ink lg:hidden">
          <button
            type="button"
            aria-label={isMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={isMenuOpen}
            onClick={() => {
              setIsMenuOpen((open) => !open);
            }}
            className="rounded-md p-2 hover:bg-white/10"
          >
            {isMenuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
          <Logo className="size-7" />
          <span className="text-sm font-semibold">AirWatch</span>
          <span className="truncate text-sm text-chrome-muted">/ {label}</span>
        </header>

        <main id="main" className="min-h-0 flex-1 overflow-hidden" aria-label={label}>
          {children}
        </main>
      </div>
    </div>
  );
}
