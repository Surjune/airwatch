import { Badge } from '@/components/ui/Badge';
import { RangeBar } from '@/components/ui/RangeBar';
import type { Attribution, Hotspot } from '@/hooks/useAnalysis';
import { aqiColour } from '@/lib/aqi';
import { istDateTime } from '@/lib/time';

interface HotspotPanelProps {
  readonly hotspots: readonly Hotspot[];
}

/** Confidence as a word, because a bare percentage implies precision it lacks. */
function confidenceLabel(confidence: number): string {
  if (confidence >= 0.7) return 'strong candidate';
  if (confidence >= 0.5) return 'plausible';
  return 'weak candidate';
}

/**
 * Detected hotspots and what may have caused them.
 *
 * Each entry leads with the comparison rather than the concentration. "381
 * where 40 was predicted" sends an inspector somewhere with something to find;
 * "381" on a bad day describes half the city.
 *
 * Attribution is always ranked candidates with a confidence, never a finding.
 * Naming the wrong operator in an enforcement context is worse than naming
 * nobody, so the wording carries that rather than leaving it implied.
 */
export function HotspotPanel({ hotspots }: HotspotPanelProps) {
  return (
    <ul className="divide-y divide-border">
      {hotspots.map((hotspot) => (
        <li key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`} className="p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-ink">{hotspot.station_name}</h3>
              <p className="mt-0.5 text-xs text-ink-subtle">
                {istDateTime(hotspot.first_seen_at)} IST · {hotspot.intervals} intervals
              </p>
            </div>
            <Badge tone="danger">{hotspot.peak_z.toFixed(1)}× expected error</Badge>
          </div>

          <p className="mt-2.5 text-sm leading-relaxed text-ink">
            <strong className="text-base font-semibold">
              {hotspot.peak_observed.toFixed(0)} µg/m³
            </strong>{' '}
            where the surrounding network predicted {hotspot.peak_expected.toFixed(0)} — an excess
            of <strong>{hotspot.peak_excess.toFixed(0)} µg/m³</strong>.
          </p>

          <div className="mt-2.5">
            <RangeBar
              value={hotspot.peak_observed}
              spread={hotspot.peak_observed - hotspot.peak_expected}
              max={Math.max(400, hotspot.peak_observed)}
              colour={aqiColour(hotspot.peak_z * 20)}
            />
            <p className="mt-1 text-xs text-ink-subtle">
              Band spans the neighbourhood prediction to the observed value
            </p>
          </div>

          <div className="mt-3.5 border-t border-border pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
              Possible sources
            </p>
            <SourceList hotspot={hotspot} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The three things that can be said about a hotspot's cause, kept distinct. */
function SourceList({ hotspot }: { readonly hotspot: Hotspot }) {
  if (hotspot.trajectory_unavailable) {
    return (
      <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
        The air was calm, so no back-trajectory could be traced.{' '}
        <span className="text-ink">This is not evidence that nothing caused it</span> — only that
        the wind field could not point anywhere.
      </p>
    );
  }

  if (hotspot.attributions.length === 0) {
    return (
      <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
        No registered source explains this excess, which points to{' '}
        <span className="text-ink">a source not in the registry</span>.
      </p>
    );
  }

  return (
    <ul className="mt-1.5 space-y-2">
      {hotspot.attributions.map((candidate) => (
        <CandidateRow key={candidate.name} candidate={candidate} />
      ))}
    </ul>
  );
}

function CandidateRow({ candidate }: { readonly candidate: Attribution }) {
  const tone = candidate.confidence >= 0.7 ? 'warn' : 'neutral';
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-ink">{candidate.name}</span>
        <Badge tone={tone}>
          {confidenceLabel(candidate.confidence)} · {(candidate.confidence * 100).toFixed(0)}%
        </Badge>
      </div>
      <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{candidate.explanation}</p>
    </li>
  );
}
