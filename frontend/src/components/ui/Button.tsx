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
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-hover',
  secondary: 'border border-border-strong bg-surface text-ink hover:bg-surface-sunken',
  ghost: 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
  danger: 'border border-danger/30 bg-danger-subtle text-danger hover:bg-danger/10',
};

const SIZES: Record<Size, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-2 text-sm',
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
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled ?? isBusy}
      aria-busy={isBusy}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
        VARIANTS[variant]
      } ${SIZES[size]}`}
      {...rest}
    >
      {isBusy && busyLabel ? busyLabel : children}
    </button>
  );
}
