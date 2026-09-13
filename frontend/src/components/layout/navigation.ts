import { BellRing, Camera, LayoutDashboard, Map, Network, Route } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type ScreenKey = 'overview' | 'map' | 'corridor' | 'alerts' | 'federation' | 'citizen';

export interface Screen {
  readonly key: ScreenKey;
  readonly label: string;
  /** The label on a phone's bottom bar, where there is room for one short word. */
  readonly shortLabel: string;
  /** One line describing the screen, used as its accessible description. */
  readonly hint: string;
  /** Where the screen sits in the chain from measurement to action. */
  readonly stage: string;
  readonly icon: LucideIcon;
}

/**
 * The screens, in the order the work happens: see the city, find what is
 * unexpected, look ahead, get someone to act, share with other cities, and add
 * to what the network can see.
 */
export const SCREENS: readonly Screen[] = [
  {
    key: 'overview',
    label: 'Overview',
    shortLabel: 'Today',
    hint: 'The city right now, and what the network can see',
    stage: 'Start here',
    icon: LayoutDashboard,
  },
  {
    key: 'map',
    label: 'Live map',
    shortLabel: 'Map',
    hint: 'Stations, sensors and detected hotspots',
    stage: 'Step 1 · Detect',
    icon: Map,
  },
  {
    key: 'corridor',
    label: 'Forecast',
    shortLabel: 'Forecast',
    hint: 'The next 72 hours along economic corridors',
    stage: 'Step 2 · Forecast',
    icon: Route,
  },
  {
    key: 'alerts',
    label: 'Authority console',
    shortLabel: 'Alerts',
    hint: 'Alerts routed to the responsible authority',
    stage: 'Step 3 · Act',
    icon: BellRing,
  },
  {
    key: 'federation',
    label: 'Federation',
    shortLabel: 'Network',
    hint: 'Cities sharing models, not raw data',
    stage: 'Step 4 · Share',
    icon: Network,
  },
  {
    key: 'citizen',
    label: 'Contribute',
    shortLabel: 'Contribute',
    hint: 'Add a photograph or a sensor reading',
    stage: 'Join in',
    icon: Camera,
  },
];

export const SCREEN_KEYS: readonly ScreenKey[] = SCREENS.map((screen) => screen.key);

/** The screen record for a key. Every key is in the list, so this never misses. */
export function screenFor(key: ScreenKey): Screen {
  return SCREENS.find((screen) => screen.key === key) ?? (SCREENS[0] as Screen);
}
