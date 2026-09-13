import { Camera, FileText, Gauge } from 'lucide-react';
import { useState } from 'react';

import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { MyComplaints } from '@/features/citizen/MyComplaints';
import { PhotoForm } from '@/features/citizen/PhotoForm';
import { RecentReadings } from '@/features/citizen/RecentReadings';
import { RecentSubmissions } from '@/features/citizen/RecentSubmissions';
import { SensorReadingForm } from '@/features/citizen/SensorReadingForm';
import { SensorReadingResult } from '@/features/citizen/SensorReadingResult';
import { useCitizen } from '@/hooks/useCitizen';
import { useCitizenSensors, type SensorReadingAccepted } from '@/hooks/useCitizenSensors';
import { useScope } from '@/lib/scope';

type Mode = 'photo' | 'sensor' | 'reports';

/**
 * The citizen contribution screen: a photograph, or a household sensor reading.
 *
 * The design problem is not the upload. It is that a number from a phone or a
 * ₹5,000 sensor looks exactly like a number from a ~₹1 crore monitor once both are
 * on a map, and this screen is where that confusion would start. So each form
 * says what its input can establish, results lead with the comparison against a
 * real monitor, and the calibration state is on the screen rather than buried.
 */
export function CitizenSubmit() {
  const { city, pollutant, current } = useScope();
  const cityLabel = current?.label ?? '…';
  const [mode, setMode] = useState<Mode>('photo');
  const [accepted, setAccepted] = useState<SensorReadingAccepted | null>(null);
  const photos = useCitizen();
  const sensors = useCitizenSensors(pollutant, city);
  const failure = mode === 'photo' ? photos.error : sensors.error;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-4 pb-16 pt-6 sm:px-6 lg:pt-8">
        <PageHeader
          eyebrow={`Join in · ${cityLabel}`}
          title="Add what you can see"
          description="Monitors are expensive and few; residents are everywhere. A photograph measures how hazy the air is. A household sensor gives a number the network compares with the nearest monitor. Neither is used as ground truth — both build the evidence that lets this tier be trusted."
        />

        <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div className="space-y-4">
            <div role="tablist" aria-label="What to contribute" className="grid grid-cols-3 gap-2">
              <ModeTab
                icon={<Camera aria-hidden className="size-4" />}
                title="Photograph"
                detail="Haze, measured from the image"
                isActive={mode === 'photo'}
                onSelect={() => {
                  setMode('photo');
                }}
              />
              <ModeTab
                icon={<Gauge aria-hidden className="size-4" />}
                title="Sensor reading"
                detail="PM2.5 or PM10 from your device"
                isActive={mode === 'sensor'}
                onSelect={() => {
                  setMode('sensor');
                }}
              />
              <ModeTab
                icon={<FileText aria-hidden className="size-4" />}
                title="Your reports"
                detail="PDF for every submission"
                isActive={mode === 'reports'}
                onSelect={() => {
                  setMode('reports');
                }}
              />
            </div>

            {mode === 'reports' ? (
              <MyComplaints />
            ) : (
              <Card>
                {mode === 'photo' ? (
                  <PhotoForm tier={photos} />
                ) : (
                  <SensorReadingForm
                    isSubmitting={sensors.isSubmitting}
                    onSubmit={(input) => {
                      void sensors.submit(input).then(setAccepted);
                    }}
                  />
                )}
              </Card>
            )}

            {mode !== 'reports' && failure && (
              <StatusMessage
                kind="error"
                title={
                  mode === 'photo'
                    ? 'Could not reach the submission service'
                    : 'The reading was not accepted'
                }
                detail={failure.message}
                {...(failure.requestId ? { requestId: failure.requestId } : {})}
              />
            )}
            {mode === 'sensor' && accepted && <SensorReadingResult accepted={accepted} />}
          </div>

          <div className="space-y-4">
            {photos.calibration && (
              <StatusMessage
                kind={photos.calibration.is_calibrated ? 'success' : 'empty'}
                title={
                  photos.calibration.is_calibrated
                    ? `Photographs calibrated from ${String(photos.calibration.pairs)} pairs`
                    : `Photographs not yet calibrated — ${String(photos.calibration.pairs)} of ${String(photos.calibration.pairs_needed)} pairs`
                }
                detail={photos.calibration.explanation}
              />
            )}
            {mode === 'sensor' ? (
              <RecentReadings tier={sensors} cityLabel={cityLabel} />
            ) : (
              <RecentSubmissions reports={photos.reports} isLoading={photos.isLoading} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ModeTab({
  icon,
  title,
  detail,
  isActive,
  onSelect,
}: {
  readonly icon: React.ReactNode;
  readonly title: string;
  readonly detail: string;
  readonly isActive: boolean;
  readonly onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={onSelect}
      className={`rounded-card border p-2.5 text-left transition-colors sm:p-3 ${
        isActive ? 'border-ink bg-surface' : 'border-border bg-surface/50 hover:border-ink/40'
      }`}
    >
      <span
        className={`flex flex-col items-start gap-1 text-[13px] font-semibold leading-tight sm:flex-row sm:items-center sm:gap-2 sm:text-sm ${
          isActive ? 'text-ink' : 'text-ink-muted'
        }`}
      >
        {icon}
        {title}
      </span>
      <span className="mt-0.5 hidden text-xs text-ink-subtle sm:block">{detail}</span>
    </button>
  );
}
