import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { PhotoReading } from '@/lib/photo-reading';

import { PhotoReadingCard } from './PhotoReadingCard';

const BURNING: PhotoReading = {
  visible_source: 'open_burning',
  confidence: 0.82,
  observation: 'Grey smoke rises from a burning pile of waste.',
  model: 'gemini-3.6-flash',
};

describe('PhotoReadingCard', () => {
  it('names the likely source with Gemini’s confidence, as a suggestion', () => {
    render(<PhotoReadingCard reading={BURNING} note={null} />);

    expect(screen.getByText('Likely open burning of waste')).toBeInTheDocument();
    expect(screen.getByText('82% confidence')).toBeInTheDocument();
    expect(screen.getByText(/does not\s+prove where pollution comes from/)).toBeInTheDocument();
  });

  it('does not call something that is not a source "likely"', () => {
    render(
      <PhotoReadingCard reading={{ ...BURNING, visible_source: 'not_outdoor' }} note={null} />,
    );

    expect(screen.getByText('Not a photograph of outdoor air')).toBeInTheDocument();
  });

  it('says why there is no reading', () => {
    render(<PhotoReadingCard reading={null} note="Reading photographs is not set up." />);

    expect(screen.getByText('Reading photographs is not set up.')).toBeInTheDocument();
  });

  it('shows nothing when there is neither a reading nor a reason', () => {
    const { container } = render(<PhotoReadingCard reading={null} note={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
