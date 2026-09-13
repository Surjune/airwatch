import { useState } from 'react';

import { AlertConsole } from '@/features/alerts/AlertConsole';
import { CitizenSubmit } from '@/features/citizen/CitizenSubmit';
import { CorridorView } from '@/features/corridor/CorridorView';
import { FederationView } from '@/features/federation/FederationView';
import { MapScreen } from '@/features/map/MapScreen';

/**
 * The screens, ordered by how far along the chain they sit: see what is
 * happening, see what is coming, make someone answer for it, check whether
 * sharing helped, and extend the network into ground no monitor reaches.
 */
const VIEWS = [
  { key: 'map', label: 'Live map', hint: 'Stations and detected hotspots' },
  { key: 'corridor', label: 'Corridor', hint: 'Outlook and travel timing along a route' },
  { key: 'alerts', label: 'Authority console', hint: 'Alerts, acknowledgement and resolution' },
  { key: 'federation', label: 'Federation', hint: 'Node coverage and transfer results' },
  { key: 'citizen', label: 'Contribute', hint: 'Submit a photograph' },
] as const;

type ViewKey = (typeof VIEWS)[number]['key'];

/**
 * Application shell.
 *
 * Routes between screens and owns nothing else; each screen loads its own data.
 *
 * The strap under the title is load-bearing rather than decorative. Someone
 * arriving at a map of coloured dots will read the colours as "bad air", and
 * the entire claim of this system is that a ring means "worse than its
 * neighbourhood predicted". Saying that once at the top is cheaper than having
 * every screen re-explain it, and cheaper than being misread.
 *
 * Navigation uses real buttons with `aria-current` rather than styled divs, so
 * the console is operable from the keyboard by someone who may be in it all day.
 */
export function App(): React.JSX.Element {
  const [view, setView] = useState<ViewKey>('map');
  const active = VIEWS.find((option) => option.key === view) ?? VIEWS[0];

  return (
    <div className="flex h-screen flex-col bg-surface-sunken">
      <header className="shrink-0 border-b border-border bg-surface">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 pb-2 pt-3 sm:px-6">
          <span className="text-base font-semibold tracking-tight text-ink">AirWatch</span>
          <p className="min-w-0 flex-1 basis-64 text-xs text-ink-muted">
            Hotspots are places dirtier than their neighbourhood predicts — not places where the
            air is simply bad
          </p>
        </div>

        <nav aria-label="Screens" className="overflow-x-auto px-2 sm:px-4">
          <ul className="flex min-w-max gap-0.5">
            {VIEWS.map((option) => {
              const isActive = option.key === view;
              return (
                <li key={option.key}>
                  <button
                    type="button"
                    aria-current={isActive ? 'page' : undefined}
                    title={option.hint}
                    onClick={() => {
                      setView(option.key);
                    }}
                    className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? 'border-accent text-accent'
                        : 'border-transparent text-ink-muted hover:border-border-strong hover:text-ink'
                    }`}
                  >
                    {option.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>

      <main className="min-h-0 flex-1 overflow-hidden" aria-label={active.label}>
        {view === 'map' && <MapScreen />}
        {view === 'corridor' && <CorridorView />}
        {view === 'alerts' && <AlertConsole />}
        {view === 'federation' && <FederationView />}
        {view === 'citizen' && <CitizenSubmit />}
      </main>
    </div>
  );
}
