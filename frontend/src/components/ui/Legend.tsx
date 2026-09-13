import { aqiBands } from '@/lib/aqi';

/**
 * The CPCB band scale, as six labelled steps.
 *
 * Steps rather than a smooth gradient, because the bands are the regulatory units
 * people act on -- "Poor" triggers different advice from "Moderate" -- and a
 * gradient would imply a continuum the policy does not have.
 */
export function Legend({ pollutantLabel }: { readonly pollutantLabel: string }) {
  return (
    <div>
      <p className="eyebrow">CPCB band · {pollutantLabel} sub-index</p>
      <ol className="mt-1.5 grid grid-cols-6 gap-px">
        {aqiBands().map((band) => (
          <li key={band.name} className="min-w-0">
            <span aria-hidden className="block h-1.5" style={{ backgroundColor: band.colour }} />
            <span className="figure mt-1 block text-[10px] text-ink-subtle">{band.floor}</span>
            <span className="hidden truncate text-[11px] text-ink-muted sm:block">{band.name}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
