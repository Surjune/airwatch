import { ArrowRight } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { ScreenKey } from '@/components/layout/navigation';
import { PollutantToggle } from '@/components/layout/PollutantToggle';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SectionHeading } from '@/components/ui/SectionHeading';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { NoHotspots } from '@/features/hotspots/NoHotspots';
import { ActSummary } from '@/features/overview/ActSummary';
import { HowItWorks } from '@/features/overview/HowItWorks';
import { MonitorReadings } from '@/features/overview/MonitorReadings';
import { NetworkTiers } from '@/features/overview/NetworkTiers';
import { OfficialReading } from '@/features/overview/OfficialReading';
import { SatelliteCard } from '@/features/overview/SatelliteCard';
import { TopHotspots } from '@/features/overview/TopHotspots';
import { useAlerts } from '@/hooks/useAlerts';
import { useHotspots, useStations } from '@/hooks/useAnalysis';
import { useCitizen } from '@/hooks/useCitizen';
import { useCitizenSensors } from '@/hooks/useCitizenSensors';
import { useHealth } from '@/hooks/useHealth';
import {
  useLowCostSensors,
  useOfficialAqi,
  useSatellite,
  type SatelliteProduct,
} from '@/hooks/useSources';
import { distanceM } from '@/lib/geo';
import { pollutantLabel, useScope } from '@/lib/scope';
import { istDateline } from '@/lib/time';

/** Detection window, in hours, matching the live map. */
const DETECTION_WINDOW_HOURS = 336;

/**
 * The landing screen, written as one argument in five parts: what the air is,
 * what the network can actually see here, what it found, who was told, and how
 * the chain works.
 *
 * Every figure keeps its window or caveat beside it, and a panel whose request
 * failed says so rather than showing zero -- "0 open alerts" from a dead API
 * would be the most reassuring and least true thing on the page.
 */
export function OverviewScreen({ onNavigate }: { readonly onNavigate: (key: ScreenKey) => void }) {
  const { city, pollutant, current } = useScope();
  const label = pollutantLabel(pollutant);
  const cityLabel = current?.label ?? '…';
  const [product, setProduct] = useState<SatelliteProduct>('no2');

  const stations = useStations(pollutant, city);
  const hotspots = useHotspots(DETECTION_WINDOW_HOURS, pollutant, city);
  const official = useOfficialAqi(city);
  const sensors = useLowCostSensors(pollutant, city);
  const satellite = useSatellite(city, product);
  const readings = useCitizenSensors(pollutant, city);
  const citizen = useCitizen();
  const alerts = useAlerts(city);
  const health = useHealth();

  // Photographs are listed for the whole network; only those inside this city's
  // view count towards its resident tier.
  const photos = useMemo(() => {
    if (!current || citizen.isLoading) return null;
    const centre = [current.centre.longitude, current.centre.latitude] as const;
    return citizen.reports.filter(
      (report) =>
        distanceM(centre, [report.position.longitude, report.position.latitude]) <=
        current.radius_m,
    );
  }, [citizen.reports, citizen.isLoading, current]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-10 px-4 pb-16 pt-6 sm:px-6 lg:px-8 lg:pt-8">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-3xl">
            <p className="eyebrow">
              {cityLabel} · {istDateline()}
            </p>
            <h1 className="mt-2 text-[28px] font-semibold leading-[1.15] tracking-tight text-ink sm:text-4xl">
              The air in {cityLabel}, and what the city average hides.
            </h1>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-muted">
              What the monitors, CPCB’s official feed, satellites, wind and residents report right
              now — and, just as plainly, where the network cannot see.
            </p>
          </div>
          <PollutantToggle />
        </header>

        <section aria-labelledby="now" className="space-y-4">
          <SectionHeading id="now" index="01" title="Right now" />
          <div className="grid gap-4 lg:grid-cols-2">
            <OfficialReading official={official} cityLabel={cityLabel} />
            <MonitorReadings stations={stations} pollutantLabel={label} />
          </div>
        </section>

        <section aria-labelledby="see" className="space-y-4">
          <SectionHeading
            id="see"
            index="02"
            title="What the network can see here"
            description="Accurate monitors are sparse, cheap sensors are dense but biased, and satellites cover everything coarsely. AirWatch keeps each in its own tier and says how much of each this city has."
          />
          <NetworkTiers
            stations={stations}
            official={official}
            sensors={sensors}
            photos={photos}
            readings={readings}
            satellite={satellite}
            health={health}
            pollutantLabel={label}
          />
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <SatelliteCard satellite={satellite} product={product} onProductChange={setProduct} />
            <Card eyebrow="Tier 2 · residents" title="Fill the gap in your street">
              <p className="text-[13px] leading-relaxed text-ink-muted">
                A photograph measures how much haze the air holds. A reading from a household sensor
                adds a number the network can compare with the nearest monitor. Both are shown as
                what they are, and both build the evidence that lets this tier be calibrated.
              </p>
              <div className="mt-4">
                <Button
                  variant="secondary"
                  size="md"
                  block
                  onClick={() => {
                    onNavigate('citizen');
                  }}
                >
                  Contribute a photo or a reading
                  <ArrowRight aria-hidden className="size-4" />
                </Button>
              </div>
            </Card>
          </div>
        </section>

        <section aria-labelledby="detect" className="space-y-4">
          <SectionHeading
            id="detect"
            index="03"
            title="What is unexpected"
            description="A hotspot is a monitor reading far above what its neighbours predict, for hours — ranked by that excess, not by concentration."
            aside={
              <Button
                onClick={() => {
                  onNavigate('map');
                }}
              >
                Open the map
                <ArrowRight aria-hidden className="size-3.5" />
              </Button>
            }
          />
          <Card>
            {hotspots.error ? (
              <StatusMessage
                kind="error"
                title="Hotspots unavailable"
                detail={hotspots.error.message}
              />
            ) : hotspots.isLoading || stations.isLoading ? (
              <Skeleton label="Detecting hotspots" rows={4} />
            ) : (hotspots.data?.hotspot_count ?? 0) === 0 ? (
              <NoHotspots
                cityLabel={cityLabel}
                stationCount={stations.data?.station_count ?? 0}
                minNeighbours={hotspots.data?.min_neighbours ?? 0}
                pollutantLabel={label}
              />
            ) : (
              <TopHotspots hotspots={hotspots.data?.hotspots ?? []} />
            )}
          </Card>
        </section>

        <section aria-labelledby="act" className="space-y-4">
          <SectionHeading id="act" index="04" title="Who has been told" />
          <ActSummary alerts={alerts} onNavigate={onNavigate} />
        </section>

        <section aria-labelledby="how" className="space-y-5">
          <SectionHeading
            id="how"
            index="05"
            title="How AirWatch works"
            description="Six links in one chain. Each has its own screen, and each states what it cannot establish."
          />
          <HowItWorks onNavigate={onNavigate} />
        </section>
      </div>
    </div>
  );
}
