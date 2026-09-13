import { PollutantToggle } from '@/components/layout/PollutantToggle';

export interface MapLayers {
  readonly sensors: boolean;
  readonly residents: boolean;
  readonly satellite: boolean;
}

interface MapToolbarProps {
  readonly cityLabel: string;
  readonly pollutantLabel: string;
  readonly windowDays: number;
  readonly layers: MapLayers;
  readonly onLayersChange: (layers: MapLayers) => void;
  readonly counts: {
    readonly monitors: number | undefined;
    readonly sensors: number | undefined;
    readonly residents: number | undefined;
  };
}

/**
 * The strip above the map: what is shown, and which of the less certain tiers
 * are drawn on top of the monitors.
 *
 * On a phone the controls scroll sideways in one row rather than wrapping into
 * three, which would take a third of the screen the map needs.
 */
export function MapToolbar({
  cityLabel,
  pollutantLabel,
  windowDays,
  layers,
  onLayersChange,
  counts,
}: MapToolbarProps) {
  return (
    <div className="shrink-0 border-b border-border bg-surface">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 px-4 pt-3 sm:px-5">
        <div className="min-w-0">
          <p className="eyebrow">Step 1 · Detect</p>
          <h1 className="text-lg font-semibold leading-tight tracking-tight text-ink">
            Live map · {cityLabel}
          </h1>
        </div>
        <p className="hidden text-xs text-ink-muted md:block">
          Latest {pollutantLabel} at each monitor · hotspots over the last {windowDays} days
        </p>
      </div>
      <div className="scroll-row flex items-center gap-2 overflow-x-auto px-4 pb-3 pt-2 sm:px-5">
        <PollutantToggle />
        <span aria-hidden className="h-5 w-px shrink-0 bg-border" />
        <Toggle
          label="Monitors"
          count={counts.monitors}
          checked
          disabled
          onChange={() => undefined}
        />
        <Toggle
          label="Community sensors"
          count={counts.sensors}
          checked={layers.sensors}
          onChange={(sensors) => {
            onLayersChange({ ...layers, sensors });
          }}
        />
        <Toggle
          label="Residents"
          count={counts.residents}
          checked={layers.residents}
          onChange={(residents) => {
            onLayersChange({ ...layers, residents });
          }}
        />
        <Toggle
          label="Satellite NO₂"
          checked={layers.satellite}
          onChange={(satellite) => {
            onLayersChange({ ...layers, satellite });
          }}
        />
      </div>
    </div>
  );
}

function Toggle({
  label,
  count,
  checked,
  disabled = false,
  onChange,
}: {
  readonly label: string;
  readonly count?: number | undefined;
  readonly checked: boolean;
  readonly disabled?: boolean;
  readonly onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={`inline-flex min-h-8 shrink-0 cursor-pointer items-center gap-2 rounded-[4px] border px-2.5 text-xs font-medium ${
        checked ? 'border-ink/40 bg-paper text-ink' : 'border-border text-ink-muted'
      } ${disabled ? 'cursor-default' : ''}`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        className="size-3.5 accent-ink"
      />
      {label}
      {count !== undefined && <span className="figure text-ink-subtle">{count}</span>}
    </label>
  );
}
