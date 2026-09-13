import { useId } from 'react';

import {
  COMPLAINT_CATEGORIES,
  DESCRIPTION_MAX_LENGTH,
  type ComplaintCategory,
} from '@/lib/complaints';

export interface ComplaintInput {
  readonly category: ComplaintCategory | null;
  readonly description: string;
}

interface ComplaintFieldsProps {
  readonly value: ComplaintInput;
  readonly onChange: (value: ComplaintInput) => void;
}

/**
 * What the resident saw, in their own words, for the complaint report.
 *
 * Optional on both forms: a photograph taken only to measure haze is still worth
 * submitting. Choosing a concern again clears it, so a mis-tap is undoable
 * without a separate reset control.
 */
export function ComplaintFields({ value, onChange }: ComplaintFieldsProps) {
  const descriptionId = useId();
  const remaining = DESCRIPTION_MAX_LENGTH - value.description.length;

  return (
    <fieldset className="space-y-3">
      <legend className="text-xs font-medium text-ink-muted">
        What did you see? <span className="font-normal text-ink-subtle">Optional</span>
      </legend>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Concern">
        {COMPLAINT_CATEGORIES.map((option) => {
          const isActive = value.category === option.key;
          return (
            <button
              key={option.key}
              type="button"
              aria-pressed={isActive}
              onClick={() => {
                onChange({ ...value, category: isActive ? null : option.key });
              }}
              className={`min-h-8 rounded-[4px] border px-2.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'border-ink bg-ink text-paper'
                  : 'border-border-strong bg-surface text-ink-muted hover:border-ink/40 hover:text-ink'
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      <label htmlFor={descriptionId} className="block">
        <span className="text-xs font-medium text-ink-muted">
          In your own words{' '}
          <span className="font-normal text-ink-subtle">
            — any language; printed on your report
          </span>
        </span>
        <textarea
          id={descriptionId}
          rows={3}
          maxLength={DESCRIPTION_MAX_LENGTH}
          value={value.description}
          onChange={(event) => {
            onChange({ ...value, description: event.target.value });
          }}
          placeholder="e.g. Black smoke from the unit behind the bus stand, every night after 9 pm."
          className="mt-1 w-full rounded-sm border border-border-strong bg-paper p-2.5 text-sm text-ink placeholder:text-ink-subtle"
        />
        <span className="figure block text-right text-[11px] text-ink-subtle">
          {remaining} characters left
        </span>
      </label>
    </fieldset>
  );
}
