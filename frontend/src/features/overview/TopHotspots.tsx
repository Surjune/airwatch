import { Badge } from '@/components/ui/Badge';
import type { Hotspot } from '@/hooks/useAnalysis';
import { istDateTime } from '@/lib/time';

const SHOWN = 4;

/** The hotspots furthest above prediction, as a teaser for the map. */
export function TopHotspots({ hotspots }: { readonly hotspots: readonly Hotspot[] }) {
  const ranked = [...hotspots].sort((a, b) => b.peak_z - a.peak_z).slice(0, SHOWN);

  if (ranked.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        No station sat outside the expected range of its neighbours in this window.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {ranked.map((hotspot) => {
        const lead = hotspot.attributions[0];
        return (
          <li
            key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`}
            className="py-3 first:pt-0 last:pb-0"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{hotspot.station_name}</p>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  {istDateTime(hotspot.first_seen_at)} IST
                </p>
              </div>
              <Badge tone="danger">{hotspot.peak_z.toFixed(1)}× expected</Badge>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
              <span className="font-semibold text-ink">
                {hotspot.peak_observed.toFixed(0)} µg/m³
              </span>{' '}
              where {hotspot.peak_expected.toFixed(0)} was predicted
              {hotspot.trajectory_unavailable ? (
                ' · calm air, no trajectory could be traced'
              ) : lead ? (
                <>
                  {' '}
                  · candidate source <span className="text-ink">{lead.name}</span> (
                  {(lead.confidence * 100).toFixed(0)}%)
                </>
              ) : (
                ' · no registered source explains it'
              )}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
