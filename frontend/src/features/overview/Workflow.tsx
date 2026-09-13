import { ArrowRight, BellRing, Compass, Radar, ShieldCheck } from 'lucide-react';

import type { ScreenKey } from '@/components/layout/navigation';

interface Step {
  readonly icon: typeof Radar;
  readonly title: string;
  readonly body: string;
  readonly screen: ScreenKey;
  readonly cta: string;
}

const STEPS: readonly Step[] = [
  {
    icon: Radar,
    title: 'Detect',
    body: 'Each station is compared with what its neighbours predict. A large, persistent excess becomes a hotspot.',
    screen: 'map',
    cta: 'Open the map',
  },
  {
    icon: Compass,
    title: 'Attribute',
    body: 'Wind is traced back from the hotspot to rank registered sources and satellite fire detections as candidates.',
    screen: 'map',
    cta: 'See candidates',
  },
  {
    icon: BellRing,
    title: 'Alert',
    body: 'The alert is routed to the authority whose jurisdiction contains it, with a response deadline.',
    screen: 'alerts',
    cta: 'Authority console',
  },
  {
    icon: ShieldCheck,
    title: 'Resolve',
    body: 'Closing an alert requires a note of what was found, so the record shows action, not a click.',
    screen: 'alerts',
    cta: 'Review the trail',
  },
];

/** How a detection becomes an answered alert, with a way into each step. */
export function Workflow({ onNavigate }: { readonly onNavigate: (key: ScreenKey) => void }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {STEPS.map((step, index) => {
        const Icon = step.icon;
        return (
          <li
            key={step.title}
            className="flex flex-col rounded-card border border-border bg-surface p-4 shadow-card"
          >
            <div className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-accent-subtle text-accent">
                <Icon aria-hidden className="size-4" />
              </span>
              <span className="text-xs font-medium text-ink-subtle">Step {index + 1}</span>
            </div>
            <h3 className="mt-3 text-sm font-semibold text-ink">{step.title}</h3>
            <p className="mt-1 flex-1 text-sm leading-relaxed text-ink-muted">{step.body}</p>
            <a
              href={`#/${step.screen}`}
              onClick={(event) => {
                event.preventDefault();
                onNavigate(step.screen);
              }}
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover"
            >
              {step.cta}
              <ArrowRight aria-hidden className="size-3.5" />
            </a>
          </li>
        );
      })}
    </ol>
  );
}
