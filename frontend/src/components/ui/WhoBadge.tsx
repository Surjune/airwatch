import { Badge } from '@/components/ui/Badge';
import { whoLabel, whoSentence, withinGuideline } from '@/lib/who';

interface WhoBadgeProps {
  /** The day's average, in `unit`. */
  readonly dailyMean: number;
  /** The average as a multiple of WHO's 24-hour guideline. */
  readonly multiple: number;
  /** WHO's 24-hour guideline, in `unit`. */
  readonly guideline: number;
  readonly unit: string;
}

/**
 * A monitor's last 24 hours against WHO's 24-hour guideline, beside its reading.
 *
 * Neutral rather than alarming in tone: in most Indian cities most days are a
 * multiple of WHO's level, and the AQI chip beside it already carries the
 * colour for how bad the air is. The short label is for the eye; a screen
 * reader gets the whole sentence instead.
 */
export function WhoBadge({ dailyMean, multiple, guideline, unit }: WhoBadgeProps) {
  const sentence = whoSentence(dailyMean, multiple, guideline, unit);
  return (
    <span title={sentence}>
      <span aria-hidden>
        <Badge tone={withinGuideline(multiple) ? 'ok' : 'neutral'}>{whoLabel(multiple)}</Badge>
      </span>
      <span className="sr-only">{sentence}</span>
    </span>
  );
}
