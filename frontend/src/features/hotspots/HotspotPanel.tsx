import { Badge } from '@/components/ui/Badge';
import { RangeBar } from '@/components/ui/RangeBar';
import type { Attribution, Hotspot } from '@/hooks/useAnalysis';
import { istDateTime } from '@/lib/time';

/** The signal colour from the design tokens, for the value tick on the range bar. */
const SIGNAL = '#c24a1c';

/** The range bar's scale never shrinks below this, so a small excess still reads as small. */
const MIN_SCALE_UGM3 = 400;

/** Confidence thresholds for the words used beside a candidate. */
const STRONG_CONFIDENCE = 0.7;
const PLAUSIBLE_CONFIDENCE = 0.5;

/** Confidence as a word, because a bare percentage implies precision it lacks. */
function confidenceLabel(confidence: number): string {
  if (confidence >= STRONG_CONFIDENCE) return 'strong candidate';
  if (confidence >= PLAUSIBLE_CONFIDENCE) return 'plausible';
  return 'weak candidate';
}

/**
 * Detected hotspots and what may have caused them.
 *
 * Each entry leads with the comparison rather than the concentration. Attribution
 * is always ranked candidates with a confidence, never a finding: naming the
 * wrong operator in an enforcement context is worse than naming nobody.
 */
export function HotspotPanel({ hotspots }: { readonly hotspots: readonly Hotspot[] }) {
  return (
    <ol className="divide-y divide-border">
      {hotspots.map((hotspot, index) => (
        <li key={`${String(hotspot.station_id)}-${hotspot.first_seen_at}`} className="p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="figure text-[11px] text-signal">#{index + 1}</p>
              <h3 className="truncate text-sm font-semibold text-ink">{hotspot.station_name}</h3>
              <p className="figure mt-0.5 text-[11px] text-ink-subtle">
                {istDateTime(hotspot.first_seen_at)} IST · {hotspot.intervals} h
              </p>
            </div>
            <Badge tone="signal">{hotspot.peak_z.toFixed(1)}× expected error</Badge>
          </div>

          <p className="mt-2.5 text-[13px] leading-relaxed text-ink">
            <strong className="figure text-base font-medium">
              {hotspot.peak_observed.toFixed(0)} µg/m³
            </strong>{' '}
            where the surrounding network predicted{' '}
            <span className="figure">{hotspot.peak_expected.toFixed(0)}</span> — an excess of{' '}
            <strong className="figure font-medium">{hotspot.peak_excess.toFixed(0)}</strong>.
          </p>

          <div className="mt-2">
            <RangeBar
              value={hotspot.peak_observed}
              spread={hotspot.peak_observed - hotspot.peak_expected}
              max={Math.max(MIN_SCALE_UGM3, hotspot.peak_observed)}
              colour={SIGNAL}
            />
            <p className="mt-1 text-[11px] text-ink-subtle">
              From the neighbourhood prediction to the observed value
            </p>
          </div>

          <div className="mt-3 border-t border-border pt-2.5">
            <p className="eyebrow">Possible sources</p>
            <SourceList hotspot={hotspot} />
          </div>
        </li>
      ))}
    </ol>
  );
}

/** The three things that can be said about a hotspot's cause, kept distinct. */
function SourceList({ hotspot }: { readonly hotspot: Hotspot }) {
  if (hotspot.trajectory_unavailable) {
    return (
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
        No back-trajectory could be traced: the air was calm, or no wind record covers that hour.{' '}
        <span className="text-ink">That is not evidence that nothing caused it</span> — only that
        the wind could not point anywhere.
      </p>
    );
  }

  if (hotspot.attributions.length === 0) {
    return (
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
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
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-medium text-ink">{candidate.name}</span>
        <Badge tone={candidate.confidence >= STRONG_CONFIDENCE ? 'warn' : 'neutral'}>
          {confidenceLabel(candidate.confidence)} · {(candidate.confidence * 100).toFixed(0)}%
        </Badge>
      </div>
      <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{candidate.explanation}</p>
    </li>
  );
}
