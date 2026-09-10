import type { Hotspot } from '@/hooks/useAnalysis';
import { RangeBar } from '@/components/ui/RangeBar';
import { aqiColour } from '@/lib/aqi';

interface HotspotPanelProps {
  readonly hotspots: readonly Hotspot[];
}

/** Confidence rendered as a word, since a bare number implies false precision. */
function confidenceLabel(confidence: number): string {
  if (confidence >= 0.7) return 'strong candidate';
  if (confidence >= 0.5) return 'plausible';
  return 'weak candidate';
}

/**
 * Detected hotspots and what may have caused them.
 *
 * Attribution is always shown as ranked candidates with a confidence, never as
 * a finding. Naming the wrong operator in an enforcement context is worse than
 * naming nobody, so the wording has to carry that.
 */
export function HotspotPanel({ hotspots }: HotspotPanelProps) {
  return (
    <ul className="divide-y divide-neutral-200">
      {hotspots.map((hotspot) => (
        <li key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`} className="p-4">
          <div className="flex items-baseline justify-between gap-2">
            <p className="font-medium">{hotspot.station_name}</p>
            <span className="shrink-0 rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
              {hotspot.peak_z.toFixed(1)}× expected error
            </span>
          </div>

          <p className="mt-1 text-sm text-neutral-700">
            {hotspot.peak_observed.toFixed(0)} µg/m³ where the surrounding network predicted{' '}
            {hotspot.peak_expected.toFixed(0)} — an excess of{' '}
            <strong>{hotspot.peak_excess.toFixed(0)} µg/m³</strong> sustained for{' '}
            {hotspot.intervals} hours.
          </p>

          <div className="mt-2">
            <RangeBar
              value={hotspot.peak_observed}
              spread={hotspot.peak_observed - hotspot.peak_expected}
              max={Math.max(400, hotspot.peak_observed)}
              colour={aqiColour(hotspot.peak_z * 20)}
            />
            <p className="mt-1 text-xs text-neutral-500">
              bar: neighbourhood prediction to observed value
            </p>
          </div>

          <div className="mt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Possible sources
            </p>
            {hotspot.trajectory_unavailable ? (
              <p className="mt-1 text-sm text-neutral-600">
                Air was calm, so no back-trajectory could be traced. This is not evidence that
                nothing caused it — only that the wind field could not point anywhere.
              </p>
            ) : hotspot.attributions.length === 0 ? (
              <p className="mt-1 text-sm text-neutral-600">
                No registered source explains this excess, which points to a source not in the
                registry.
              </p>
            ) : (
              <ul className="mt-1 space-y-1">
                {hotspot.attributions.map((candidate) => (
                  <li key={candidate.name} className="text-sm">
                    <span className="font-medium">{candidate.name}</span>{' '}
                    <span className="text-neutral-500">
                      — {confidenceLabel(candidate.confidence)} (
                      {(candidate.confidence * 100).toFixed(0)}%)
                    </span>
                    <p className="text-xs text-neutral-500">{candidate.explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
