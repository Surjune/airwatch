import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { GuideSection } from '@/lib/guide';

import { GuideTranscript } from './GuideTranscript';

const SECTIONS: GuideSection[] = [
  { index: 0, heading: 'மேலே', text: 'முதல் பத்தி.', audio_path: '/guide/map/sections/0/audio' },
  { index: 1, heading: 'கீழே', text: 'இரண்டாம் பத்தி.', audio_path: '/guide/map/sections/1/audio' },
];

beforeAll(() => {
  // jsdom lays nothing out, so it has no scrolling to do.
  Element.prototype.scrollIntoView = vi.fn();
});

function renderTranscript(current: number, isSpeaking: boolean, onSelect = vi.fn()) {
  render(
    <GuideTranscript
      sections={SECTIONS}
      language="ta"
      current={current}
      isSpeaking={isSpeaking}
      onSelect={onSelect}
    />,
  );
  return onSelect;
}

describe('GuideTranscript', () => {
  it('shows every paragraph, marked with its language', () => {
    renderTranscript(0, false);

    expect(screen.getByText('முதல் பத்தி.')).toBeInTheDocument();
    expect(screen.getByText('இரண்டாம் பத்தி.')).toBeInTheDocument();
    expect(screen.getByRole('list')).toHaveAttribute('lang', 'ta');
  });

  it('marks the paragraph being spoken, and only while speaking', () => {
    renderTranscript(1, true);
    expect(screen.getByRole('button', { name: /கீழே/ })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('button', { name: /மேலே/ })).not.toHaveAttribute('aria-current');
  });

  it('marks nothing when the guide is not playing', () => {
    renderTranscript(1, false);
    for (const button of screen.getAllByRole('button')) {
      expect(button).not.toHaveAttribute('aria-current');
    }
  });

  it('plays from the paragraph pressed', () => {
    const onSelect = renderTranscript(0, false);
    fireEvent.click(screen.getByRole('button', { name: /கீழே/ }));
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});
