import { ApiStatus } from '@/components/layout/ApiStatus';
import { CityPicker } from '@/components/layout/CityPicker';
import { Logo } from '@/components/layout/Logo';
import { SCREEN_GROUPS, SCREENS, type ScreenKey } from '@/components/layout/navigation';

interface SidebarProps {
  readonly active: ScreenKey;
  readonly onNavigate: (key: ScreenKey) => void;
}

/**
 * The primary navigation.
 *
 * Links are real anchors to `#/screen`, so a middle-click opens a screen in a
 * new tab and the address can be copied, while a plain click still navigates in
 * place. `aria-current` marks the open screen for assistive technology.
 */
export function Sidebar({ active, onNavigate }: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-chrome text-chrome-ink">
      <div className="flex items-center gap-3 px-5 pb-4 pt-5">
        <Logo className="size-9" />
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-tight">AirWatch</p>
          <p className="text-[11px] text-chrome-muted">Hyperlocal air intelligence</p>
        </div>
      </div>

      <div className="px-3 pb-5">
        <CityPicker />
      </div>

      <nav aria-label="Screens" className="flex-1 space-y-6 overflow-y-auto px-3">
        {SCREEN_GROUPS.map((group) => (
          <div key={group}>
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-chrome-muted/80">
              {group}
            </p>
            <ul className="space-y-0.5">
              {SCREENS.filter((screen) => screen.group === group).map((screen) => {
                const isActive = screen.key === active;
                const Icon = screen.icon;
                return (
                  <li key={screen.key}>
                    <a
                      href={`#/${screen.key}`}
                      aria-current={isActive ? 'page' : undefined}
                      onClick={(event) => {
                        if (event.metaKey || event.ctrlKey || event.shiftKey) return;
                        event.preventDefault();
                        onNavigate(screen.key);
                      }}
                      className={`group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-teal-400/15 font-medium text-white shadow-[inset_3px_0_0_var(--color-teal-400)]'
                          : 'text-chrome-muted hover:bg-white/5 hover:text-chrome-ink'
                      }`}
                    >
                      <Icon
                        aria-hidden
                        className={`size-[18px] shrink-0 ${isActive ? 'text-teal-300' : ''}`}
                        strokeWidth={1.75}
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{screen.label}</span>
                        <span className="block truncate text-[11px] font-normal text-chrome-muted">
                          {screen.hint}
                        </span>
                      </span>
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="space-y-3 border-t border-chrome-border p-3">
        <ApiStatus />
        <p className="px-1 text-[11px] leading-relaxed text-chrome-muted">
          A hotspot is a place dirtier than its neighbourhood predicts — not a place where the air
          is simply bad.
        </p>
      </div>
    </div>
  );
}
