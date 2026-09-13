import { aqiBands } from '@/lib/aqi';

/**
 * A thin rule made of the six CPCB band colours, under the masthead.
 *
 * The one decorative element in the interface, and it is not decoration: it is
 * the scale every coloured mark on every screen is read against, kept in view.
 */
export function BandRule({ className = 'h-[3px]' }: { readonly className?: string }) {
  return (
    <div aria-hidden className={`flex w-full ${className}`}>
      {aqiBands().map((band) => (
        <span key={band.name} className="flex-1" style={{ backgroundColor: band.colour }} />
      ))}
    </div>
  );
}
