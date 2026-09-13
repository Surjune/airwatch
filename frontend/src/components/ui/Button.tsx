import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
  readonly children: ReactNode;
  readonly variant?: Variant;
  readonly size?: Size;
  /** Shown in place of the label while a request is in flight. */
  readonly busyLabel?: string;
  readonly isBusy?: boolean;
  /** Stretch to the container's width, for a phone-width form. */
  readonly block?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'border border-ink bg-ink text-paper hover:bg-ink/85',
  secondary: 'border border-border-strong bg-surface text-ink hover:border-ink/40 hover:bg-paper',
  ghost: 'border border-transparent text-ink-muted hover:bg-surface-sunken hover:text-ink',
  danger: 'border border-danger/30 bg-danger-subtle text-danger hover:bg-danger/10',
};

const SIZES: Record<Size, string> = {
  sm: 'min-h-8 px-2.5 text-[13px]',
  md: 'min-h-10 px-4 text-sm',
};

/**
 * The single button.
 *
 * `isBusy` disables the control and swaps the label, which matters here because
 * every action on the authority console writes to a record an official is held
 * to. A double-submitted acknowledgement would put two timestamps on one event.
 */
export function Button({
  children,
  variant = 'secondary',
  size = 'sm',
  isBusy = false,
  busyLabel,
  block = false,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled ?? isBusy}
      aria-busy={isBusy}
      className={`inline-flex items-center justify-center gap-1.5 rounded-[4px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        VARIANTS[variant]
      } ${SIZES[size]} ${block ? 'w-full' : ''}`}
      {...rest}
    >
      {isBusy && busyLabel ? busyLabel : children}
    </button>
  );
}
