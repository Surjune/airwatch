import { Badge } from '@/components/ui/Badge';
import type { Hotspot } from '@/hooks/useAnalysis';
import { istDateTime } from '@/lib/time';

const SHOWN = 4;

/** The hotspots furthest above prediction, as a way into the map. */
export function TopHotspots({ hotspots }: { readonly hotspots: readonly Hotspot[] }) {
  const ranked = [...hotspots].sort((a, b) => b.peak_z - a.peak_z).slice(0, SHOWN);

  return (
    <ol className="divide-y divide-border">
      {ranked.map((hotspot) => {
        const lead = hotspot.attributions[0];
        return (
          <li
            key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`}
            className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0"
          >
            <p className="min-w-0 truncate text-sm font-medium text-ink">{hotspot.station_name}</p>
            <Badge tone="signal">{hotspot.peak_z.toFixed(1)}× expected error</Badge>
            <p className="col-span-2 text-[13px] leading-relaxed text-ink-muted">
              <span className="figure text-ink">{hotspot.peak_observed.toFixed(0)}</span> µg/m³
              where the neighbourhood predicted{' '}
              <span className="figure text-ink">{hotspot.peak_expected.toFixed(0)}</span>
              {hotspot.trajectory_unavailable ? (
                ' · no wind to trace a trajectory through'
              ) : lead ? (
                <>
                  {' '}
                  · candidate source <span className="text-ink">{lead.name}</span>{' '}
                  <span className="figure">({(lead.confidence * 100).toFixed(0)}%)</span>
                </>
              ) : (
                ' · no registered source explains it'
              )}
            </p>
            <p className="figure col-span-2 text-[11px] text-ink-subtle">
              first seen {istDateTime(hotspot.first_seen_at)} IST · {hotspot.intervals} h
            </p>
          </li>
        );
      })}
    </ol>
  );
}
