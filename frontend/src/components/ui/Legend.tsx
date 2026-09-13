import { aqiBands } from '@/lib/aqi';

/**
 * The CPCB band scale.
 *
 * Shown as the lower bound of each band rather than a smooth gradient, because
 * the bands are the regulatory units people act on -- "Poor" triggers different
 * advice from "Moderate" -- and a gradient would imply a continuum the policy
 * does not have.
 */
export function Legend() {
  return (
    <div>
      <p className="text-xs font-medium text-ink-subtle">CPCB band (PM2.5 sub-index)</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
        {aqiBands().map((band) => (
          <li key={band.name} className="flex items-center gap-1.5 text-xs text-ink-muted">
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: band.colour }}
            />
            {band.name}
            <span className="text-ink-subtle">{band.floor}+</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
