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
      className="inline-flex shrink-0 rounded-[4px] border border-border-strong bg-surface p-0.5"
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
            className={`min-h-7 whitespace-nowrap rounded-[3px] px-2.5 text-xs font-medium transition-colors ${
              isActive ? 'bg-ink text-paper' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
