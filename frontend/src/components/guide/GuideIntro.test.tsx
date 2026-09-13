import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { GuideIntro } from './GuideIntro';

describe('GuideIntro', () => {
  it('offers each language in its own script, and one press chooses it', () => {
    const onChoose = vi.fn();
    render(<GuideIntro onChoose={onChoose} onDismiss={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /தமிழில் கேளுங்கள்/ }));
    expect(onChoose).toHaveBeenCalledWith('ta');

    fireEvent.click(screen.getByRole('button', { name: /हिन्दी में सुनें/ }));
    expect(onChoose).toHaveBeenCalledWith('hi');
  });

  it('can be declined', () => {
    const onDismiss = vi.fn();
    render(<GuideIntro onChoose={vi.fn()} onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
