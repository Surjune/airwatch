/**
 * The AirWatch mark: a hexagon -- the H3 cell every estimate is keyed on --
 * with a ring off-centre, which is what a hotspot is: one place that stands out
 * from the cells around it.
 */
export function Logo({ className = 'size-8' }: { readonly className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <path d="M16 2.5 27.7 9.25v13.5L16 29.5 4.3 22.75V9.25Z" fill="#14b8a6" />
      <path d="M16 2.5 27.7 9.25v13.5L16 29.5 4.3 22.75V9.25Z" fill="url(#aw-shade)" />
      <circle cx="19" cy="13.5" r="5" fill="none" stroke="#fff" strokeWidth="2.2" />
      <circle cx="19" cy="13.5" r="1.7" fill="#fff" />
      <path d="M8.5 21.5h8" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".7" />
      <defs>
        <linearGradient id="aw-shade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0f5c6e" stopOpacity="0" />
          <stop offset="1" stopColor="#0f5c6e" stopOpacity=".65" />
        </linearGradient>
      </defs>
    </svg>
  );
}
