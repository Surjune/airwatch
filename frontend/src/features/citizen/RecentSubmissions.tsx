import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { CitizenReport } from '@/hooks/useCitizen';

const SHOWN = 12;

interface RecentSubmissionsProps {
  readonly reports: readonly CitizenReport[];
  readonly isLoading: boolean;
}

/** The last day's submissions, and which of them also shape the calibration. */
export function RecentSubmissions({ reports, isLoading }: RecentSubmissionsProps) {
  return (
    <Card title="Recent submissions" description="The last 24 hours" flush>
      {isLoading ? (
        <div className="p-4">
          <Skeleton label="Loading submissions" rows={3} />
        </div>
      ) : reports.length === 0 ? (
        <div className="p-4">
          <StatusMessage
            kind="empty"
            title="No submissions in the last day"
            detail="This tier only has data when people contribute it, so an empty list means nobody has, not that the air is clean."
          />
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {reports.slice(0, SHOWN).map((report) => (
            <li
              key={report.report_id}
              className="flex items-center justify-between gap-3 px-4 py-2.5"
            >
              <span className="flex items-center gap-2 text-sm text-ink">
                Haze {report.haze_index.toFixed(2)}
                {report.had_reference && <Badge tone="ok">also calibrates</Badge>}
              </span>
              <span className="text-xs text-ink-subtle">
                {report.position.latitude.toFixed(3)}, {report.position.longitude.toFixed(3)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
