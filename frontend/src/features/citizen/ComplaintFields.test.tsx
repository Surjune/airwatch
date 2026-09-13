import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { DESCRIPTION_MAX_LENGTH } from '@/lib/complaints';

import { ComplaintFields, type ComplaintInput } from './ComplaintFields';

function Harness({ onValue }: { readonly onValue: (value: ComplaintInput) => void }) {
  const [value, setValue] = useState<ComplaintInput>({ category: null, description: '' });
  return (
    <ComplaintFields
      value={value}
      onChange={(next) => {
        setValue(next);
        onValue(next);
      }}
    />
  );
}

describe('ComplaintFields', () => {
  it('selects a concern, and a second tap clears it', () => {
    let latest: ComplaintInput = { category: null, description: '' };
    render(<Harness onValue={(value) => (latest = value)} />);

    const burning = screen.getByRole('button', { name: 'Burning waste' });
    fireEvent.click(burning);
    expect(latest.category).toBe('open_burning');
    expect(burning).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(burning);
    expect(latest.category).toBeNull();
  });

  it('keeps the description in any language and counts what is left', () => {
    let latest: ComplaintInput = { category: null, description: '' };
    render(<Harness onValue={(value) => (latest = value)} />);

    fireEvent.change(screen.getByLabelText(/in your own words/i), {
      target: { value: 'குப்பை எரிப்பு' },
    });

    expect(latest.description).toBe('குப்பை எரிப்பு');
    expect(
      screen.getByText(
        `${String(DESCRIPTION_MAX_LENGTH - 'குப்பை எரிப்பு'.length)} characters left`,
      ),
    ).toBeInTheDocument();
  });
});
