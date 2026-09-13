interface SkeletonProps {
  /** Number of placeholder rows to draw. */
  readonly rows?: number;
  readonly label: string;
}

/** Each row this much narrower than the one above, in percent, so it reads as text. */
const ROW_TAPER = 12;

/**
 * A loading placeholder.
 *
 * Grey bars rather than a spinner: it shows the shape of what is coming without
 * implying any content has arrived. The accessible label is what a screen reader
 * announces, since the bars themselves say nothing.
 *
 * Never used for an empty result. A skeleton that stayed forever would read as
 * "still loading" when the honest answer is "nothing to show".
 */
export function Skeleton({ rows = 3, label }: SkeletonProps) {
  return (
    <div role="status" aria-live="polite" className="space-y-2.5">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          aria-hidden
          className="h-3.5 animate-pulse rounded-sm bg-surface-sunken"
          style={{ width: `${String(100 - index * ROW_TAPER)}%` }}
        />
      ))}
    </div>
  );
}
