interface Option<K extends string> {
  readonly key: K;
  readonly label: string;
}

interface SegmentedControlProps<K extends string> {
  readonly label: string;
  readonly options: readonly Option<K>[];
  readonly value: K;
  readonly onChange: (key: K) => void;
}

/** A small set of mutually exclusive choices, shown all at once. */
export function SegmentedControl<K extends string>({
  label,
  options,
  value,
  onChange,
}: SegmentedControlProps<K>) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex rounded-lg border border-border bg-surface-sunken p-0.5"
    >
      {options.map((option) => {
        const isActive = option.key === value;
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={isActive}
            onClick={() => {
              onChange(option.key);
            }}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              isActive ? 'bg-surface text-ink shadow-card' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
