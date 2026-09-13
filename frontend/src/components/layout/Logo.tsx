/**
 * The AirWatch mark: an H3 hexagon -- the cell every estimate is keyed on -- with
 * one filled dot off-centre, which is what a hotspot is: a single place that
 * stands out from the ground around it.
 */
export function Logo({ className = 'size-7' }: { readonly className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <path
        d="M16 3.2 27.1 9.6v12.8L16 28.8 4.9 22.4V9.6Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <circle cx="19.4" cy="13.4" r="3.6" fill="var(--color-signal)" />
      <path d="M10 20.4h7.2" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}
