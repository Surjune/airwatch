import { BellRing, Camera, LayoutDashboard, Map, Network, Route } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface Screen {
  readonly key: ScreenKey;
  readonly label: string;
  /** One line under the label in the sidebar, and the page's accessible name. */
  readonly hint: string;
  readonly icon: LucideIcon;
  readonly group: 'Monitor' | 'Act' | 'Network';
}

export type ScreenKey = 'overview' | 'map' | 'corridor' | 'alerts' | 'federation' | 'citizen';

/**
 * The screens, grouped by what someone arrives to do: understand the air, act
 * on it, or extend the network that measures it.
 */
export const SCREENS: readonly Screen[] = [
  {
    key: 'overview',
    label: 'Overview',
    hint: 'The network at a glance',
    icon: LayoutDashboard,
    group: 'Monitor',
  },
  {
    key: 'map',
    label: 'Live map',
    hint: 'Stations and detected hotspots',
    icon: Map,
    group: 'Monitor',
  },
  {
    key: 'corridor',
    label: 'Corridor outlook',
    hint: 'Forecast along a route',
    icon: Route,
    group: 'Monitor',
  },
  {
    key: 'alerts',
    label: 'Authority console',
    hint: 'Acknowledge and resolve alerts',
    icon: BellRing,
    group: 'Act',
  },
  {
    key: 'federation',
    label: 'Federation',
    hint: 'Coverage and model transfer',
    icon: Network,
    group: 'Network',
  },
  {
    key: 'citizen',
    label: 'Contribute',
    hint: 'Submit a photograph',
    icon: Camera,
    group: 'Network',
  },
];

export const SCREEN_KEYS: readonly ScreenKey[] = SCREENS.map((screen) => screen.key);

export const SCREEN_GROUPS = ['Monitor', 'Act', 'Network'] as const;
