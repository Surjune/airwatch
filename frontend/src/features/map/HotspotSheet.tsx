import { ChevronUp } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

interface HotspotSheetProps {
  readonly count: number | undefined;
  readonly children: ReactNode;
}

/**
 * The hotspot list beside the map, or over it on a phone.
 *
 * On a desktop it is a fixed side panel. On a phone it is a sheet along the
 * bottom of the map that starts collapsed to one line -- the count, which is
 * the first thing anyone wants -- and opens to most of the screen, so the map
 * stays usable until the list is asked for.
 */
export function HotspotSheet({ count, children }: HotspotSheetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const bodyId = useId();

  return (
    <aside
      aria-label="Detected hotspots"
      className={`absolute inset-x-0 bottom-0 z-[1050] flex flex-col rounded-t-lg border-t border-border bg-surface shadow-overlay transition-[max-height] duration-200 lg:static lg:z-auto lg:max-h-none lg:w-[25rem] lg:shrink-0 lg:rounded-none lg:border-l lg:border-t-0 lg:shadow-none ${
        isOpen ? 'max-h-[70%]' : 'max-h-[3.75rem]'
      }`}
    >
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={bodyId}
        onClick={() => {
          setIsOpen((open) => !open);
        }}
        className="flex min-h-[3.75rem] shrink-0 items-center justify-between gap-3 border-b border-border px-4 text-left lg:pointer-events-none lg:min-h-0 lg:py-3"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-ink">
            Detected hotspots
            <span className="figure ml-2 text-signal">{count ?? '…'}</span>
          </span>
          <span className="block truncate text-xs text-ink-muted">
            Ranked by excess over the neighbourhood’s prediction
          </span>
        </span>
        <ChevronUp
          aria-hidden
          className={`size-5 shrink-0 text-ink-subtle transition-transform lg:hidden ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>
      <div id={bodyId} className="min-h-0 flex-1 overflow-y-auto">
        {children}
      </div>
    </aside>
  );
}
