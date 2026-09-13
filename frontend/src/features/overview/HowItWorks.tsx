import type { ScreenKey } from '@/components/layout/navigation';

interface Step {
  readonly title: string;
  readonly body: string;
  readonly screen: ScreenKey;
  readonly link: string;
}

/** The chain from a measurement to an answered alert, one screen per link. */
const STEPS: readonly Step[] = [
  {
    title: 'Sense',
    body: 'Reference monitors, CPCB’s feed, low-cost sensors, residents’ photographs and readings, Sentinel-5P and hourly wind, each kept in its own tier.',
    screen: 'citizen',
    link: 'Add a reading',
  },
  {
    title: 'Detect',
    body: 'Every monitor is compared with what its neighbours predict. A large excess that persists for hours is a hotspot — a threshold alarm would miss it.',
    screen: 'map',
    link: 'Open the map',
  },
  {
    title: 'Attribute',
    body: 'Wind is traced back from the hotspot to rank registered sources and satellite fire detections, each with a confidence and never as a verdict.',
    screen: 'map',
    link: 'See candidates',
  },
  {
    title: 'Forecast',
    body: 'Concentration 24 to 72 hours ahead along economic corridors, and the departure hour that cuts a commuter’s exposure.',
    screen: 'corridor',
    link: 'Plan a route',
  },
  {
    title: 'Alert',
    body: 'Routed to the district that holds the hotspot, and to the neighbour that holds its source, with a deadline and a required resolution note.',
    screen: 'alerts',
    link: 'Authority console',
  },
  {
    title: 'Share',
    body: 'Cities train together by exchanging model weights, never raw data, and publish whether sharing actually helped each one.',
    screen: 'federation',
    link: 'Federation',
  },
];

/** How AirWatch turns readings into action, as a numbered sequence with a way into each step. */
export function HowItWorks({ onNavigate }: { readonly onNavigate: (key: ScreenKey) => void }) {
  return (
    <ol className="grid gap-x-6 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
      {STEPS.map((step, index) => (
        <li key={step.title} className="border-t border-border pt-3">
          <p className="figure text-xs text-signal">{String(index + 1).padStart(2, '0')}</p>
          <h3 className="mt-1 text-[15px] font-semibold text-ink">{step.title}</h3>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{step.body}</p>
          <a
            href={`#/${step.screen}`}
            onClick={(event) => {
              event.preventDefault();
              onNavigate(step.screen);
            }}
            className="mt-2 inline-block text-[13px] font-medium text-accent underline decoration-accent/30 underline-offset-4 hover:decoration-accent"
          >
            {step.link} →
          </a>
        </li>
      ))}
    </ol>
  );
}
