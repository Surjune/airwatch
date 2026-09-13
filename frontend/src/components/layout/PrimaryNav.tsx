import type { MouseEvent } from 'react';

import { SCREENS, type ScreenKey } from '@/components/layout/navigation';

interface PrimaryNavProps {
  readonly active: ScreenKey;
  readonly onNavigate: (key: ScreenKey) => void;
  /** `bar` is the desktop masthead tabs; `dock` is the phone's bottom bar. */
  readonly variant: 'bar' | 'dock';
}

/**
 * The primary navigation, in two shapes from one list.
 *
 * Links are real anchors to `#/screen`, so a middle-click opens a screen in a new
 * tab and the address can be copied, while a plain click navigates in place.
 * `aria-current` marks the open screen for assistive technology.
 */
export function PrimaryNav({ active, onNavigate, variant }: PrimaryNavProps) {
  const follow = (event: MouseEvent<HTMLAnchorElement>, key: ScreenKey) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    onNavigate(key);
  };

  if (variant === 'dock') {
    return (
      <nav aria-label="Screens" className="pb-safe border-t border-border bg-surface">
        <ul className="grid grid-cols-6">
          {SCREENS.map((screen) => {
            const isActive = screen.key === active;
            const Icon = screen.icon;
            return (
              <li key={screen.key}>
                <a
                  href={`#/${screen.key}`}
                  aria-current={isActive ? 'page' : undefined}
                  aria-label={screen.label}
                  onClick={(event) => {
                    follow(event, screen.key);
                  }}
                  className={`relative flex min-h-14 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-medium leading-none ${
                    isActive ? 'text-ink' : 'text-ink-subtle'
                  }`}
                >
                  {isActive && (
                    <span aria-hidden className="absolute inset-x-3 top-0 h-0.5 bg-signal" />
                  )}
                  <Icon aria-hidden className="size-5" strokeWidth={isActive ? 2.1 : 1.7} />
                  <span className="truncate">{screen.shortLabel}</span>
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    );
  }

  return (
    <nav aria-label="Screens" className="h-full">
      <ul className="flex h-full items-stretch gap-1">
        {SCREENS.map((screen) => {
          const isActive = screen.key === active;
          return (
            <li key={screen.key} className="flex">
              <a
                href={`#/${screen.key}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={(event) => {
                  follow(event, screen.key);
                }}
                className={`relative flex items-center whitespace-nowrap px-2.5 text-[13px] font-medium transition-colors xl:px-3 ${
                  isActive ? 'text-ink' : 'text-ink-muted hover:text-ink'
                }`}
              >
                {screen.label}
                {isActive && (
                  <span
                    aria-hidden
                    className="absolute inset-x-2.5 bottom-0 h-0.5 bg-ink xl:inset-x-3"
                  />
                )}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
