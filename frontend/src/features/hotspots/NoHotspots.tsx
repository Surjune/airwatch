import { StatusMessage } from '@/components/ui/StatusMessage';

interface NoHotspotsProps {
  readonly cityLabel: string;
  readonly stationCount: number;
  readonly minNeighbours: number;
  readonly pollutantLabel: string;
}

/**
 * Why a city shows no hotspots -- which is two very different statements.
 *
 * With enough monitors, an empty list is a result: every station sat within the
 * range its neighbours predicted. With too few, detection cannot run at all,
 * because a hotspot is a comparison with neighbours and there are none. Showing
 * the second as the first would tell a city with one working monitor that its
 * air holds no surprises, which is exactly the blind spot this system exists to
 * expose.
 */
export function NoHotspots({
  cityLabel,
  stationCount,
  minNeighbours,
  pollutantLabel,
}: NoHotspotsProps) {
  if (stationCount <= minNeighbours) {
    return (
      <StatusMessage
        kind="empty"
        title={`Too few monitors in ${cityLabel} to detect hotspots`}
        detail={`${cityLabel} has ${String(stationCount)} station${stationCount === 1 ? '' : 's'} reporting ${pollutantLabel}. A hotspot is a station reading above what its neighbours predict, which needs at least ${String(minNeighbours)} neighbours — so no hotspot here means no comparison was possible, not that the air holds no surprises. Citizen photographs are how this gap gets filled.`}
      />
    );
  }

  return (
    <StatusMessage
      kind="empty"
      title="No hotspots in this window"
      detail="Every station sat within the expected range of its neighbours. That is a real result, not an absence of data."
    />
  );
}
