import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { useScope, VIEW_POLLUTANTS } from '@/lib/scope';

/** Switch the pollutant every scoped screen shows. */
export function PollutantToggle() {
  const { pollutant, setPollutant } = useScope();
  return (
    <SegmentedControl
      label="Pollutant"
      options={VIEW_POLLUTANTS}
      value={VIEW_POLLUTANTS.some((option) => option.key === pollutant) ? pollutant : 'pm25'}
      onChange={setPollutant}
    />
  );
}
