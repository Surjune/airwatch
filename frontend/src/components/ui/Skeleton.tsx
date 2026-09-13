interface SkeletonProps {
  /** Number of placeholder rows to draw. */
  readonly rows?: number;
  readonly label: string;
}

/**
 * A loading placeholder.
 *
 * Deliberately grey and unlabelled-looking rather than a spinner: it shows the
 * shape of what is coming without implying any content has arrived. The
 * accessible label is what a screen reader announces, since the bars themselves
 * say nothing.
 *
 * This is never used for an empty result. A skeleton that stayed forever would
 * read as "still loading" when the honest answer is "nothing to show", and
 * those must not look alike.
 */
export function Skeleton({ rows = 3, label }: SkeletonProps) {
  return (
    <div role="status" aria-live="polite" className="space-y-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          aria-hidden
          className="h-4 animate-pulse rounded bg-surface-sunken"
          style={{ width: `${String(100 - index * 12)}%` }}
        />
      ))}
    </div>
  );
}
