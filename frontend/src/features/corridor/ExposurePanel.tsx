import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ExposureAdvisory } from '@/hooks/useAnalysis';

/** Percent of the bar track, for the widest bar. */
const PERCENT = 100;

/**
 * When to travel, if the day's shape supports an answer.
 *
 * The one decision the forecast is genuinely equipped to inform. Climatology has
 * no day-to-day skill, so it cannot say whether tomorrow will be bad -- but it
 * does resolve the shape of an average day, and "is the evening usually better
 * than the afternoon on this route" is exactly a question about that shape.
 *
 * When the day is flat, no hour is named: naming one on a difference smaller than
 * the forecast's own error would dress noise as advice.
 */
export function ExposurePanel({
  advisory,
  isLoading,
}: {
  readonly advisory: ExposureAdvisory | null;
  readonly isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card eyebrow="Exposure advisory" title="When to travel">
        <Skeleton label="Comparing departure times" rows={4} />
      </Card>
    );
  }
  if (!advisory) return null;

  const peak = Math.max(...advisory.options.map((option) => option.exposure), 1);
  const minutes = advisory.options[0]?.travel_minutes;

  return (
    <Card eyebrow="Exposure advisory" title="When to travel this route">
      <p
        className={`rounded-sm px-3 py-2 text-sm leading-relaxed ${
          advisory.is_actionable ? 'bg-ok-subtle text-ok' : 'bg-surface-sunken text-ink'
        }`}
      >
        {advisory.explanation}
      </p>

      <ol className="mt-4 space-y-1.5">
        {advisory.options.map((option) => {
          const isBest = advisory.is_actionable && option.hour === advisory.best_hour;
          const isWorst = advisory.is_actionable && option.hour === advisory.worst_hour;
          return (
            <li key={option.hour} className="grid grid-cols-[3rem_1fr_auto] items-center gap-2">
              <span className="figure text-xs text-ink-muted">
                {String(option.hour).padStart(2, '0')}:00
              </span>
              <span className="h-3 overflow-hidden rounded-[2px] bg-surface-sunken">
                <span
                  className={`block h-full ${isBest ? 'bg-ok' : isWorst ? 'bg-signal' : 'bg-ink/30'}`}
                  style={{ width: `${String((option.exposure / peak) * PERCENT)}%` }}
                  title={`${option.mean_concentration.toFixed(0)} µg/m³ average over ${option.travel_minutes.toFixed(0)} minutes`}
                />
              </span>
              <span className="figure w-20 text-right text-xs text-ink-muted">
                {option.mean_concentration.toFixed(0)} µg/m³
              </span>
            </li>
          );
        })}
      </ol>

      <p className="mt-4 text-xs leading-relaxed text-ink-subtle">
        Bars are exposure — concentration multiplied by the time spent in it — for a{' '}
        {minutes !== undefined ? `${minutes.toFixed(0)}-minute` : 'typical'} journey. Not micrograms
        inhaled: that needs a breathing rate which depends on the person, and inventing one would
        add a made-up factor to a number that is useful without it.
      </p>
    </Card>
  );
}
