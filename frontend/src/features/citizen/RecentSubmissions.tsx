import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { CitizenReport } from '@/hooks/useCitizen';
import { timeAgo } from '@/lib/time';

const SHOWN = 10;

interface RecentSubmissionsProps {
  readonly reports: readonly CitizenReport[];
  readonly isLoading: boolean;
}

/** The last day's photographs, and which of them also shape the calibration. */
export function RecentSubmissions({ reports, isLoading }: RecentSubmissionsProps) {
  return (
    <Card eyebrow="Last 24 hours" title="Photographs submitted" flush>
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
              className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5"
            >
              <span className="flex min-w-0 items-center gap-2 text-[13px] text-ink">
                Haze <span className="figure">{report.haze_index.toFixed(2)}</span>
                {report.had_reference && <Badge tone="ok">also calibrates</Badge>}
              </span>
              <span className="figure shrink-0 text-[11px] text-ink-subtle">
                {timeAgo(report.captured_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
