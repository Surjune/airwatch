import { FileDown } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { useComplaints } from '@/hooks/useComplaints';
import { categoryLabel } from '@/lib/complaints';
import { istDateTime } from '@/lib/time';

/**
 * Every submission from this browser, each with its PDF report.
 *
 * The list is tied to an anonymous identifier held in this browser, and says so:
 * someone who clears site data and finds an empty list should know why, rather
 * than conclude their complaints were lost.
 */
export function MyComplaints() {
  const { data, error, isLoading, downloading, downloadError, downloadReport } = useComplaints();
  const complaints = data?.complaints ?? [];

  return (
    <Card
      eyebrow="Your reports"
      title="Everything you have submitted"
      description="Download the PDF report for any submission to attach to an official complaint."
      flush
    >
      {error ? (
        <div className="p-4">
          <StatusMessage
            kind="error"
            title="Your submissions could not be loaded"
            detail={error.message}
          />
        </div>
      ) : isLoading ? (
        <div className="p-4">
          <Skeleton label="Loading your submissions" rows={3} />
        </div>
      ) : complaints.length === 0 ? (
        <div className="p-4">
          <StatusMessage
            kind="empty"
            title="Nothing submitted from this browser yet"
            detail="Submit a photograph or a sensor reading and its report appears here. Reports are tied to this browser, so a different device or cleared site data starts a new list."
          />
        </div>
      ) : (
        <>
          <ul className="divide-y divide-border">
            {complaints.map((complaint) => (
              <li
                key={complaint.reference}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-5"
              >
                <div className="min-w-0 flex-1 basis-56">
                  <p className="figure text-[13px] font-medium text-ink">{complaint.reference}</p>
                  <p className="truncate text-[13px] text-ink">{complaint.headline}</p>
                  <p className="text-xs text-ink-subtle">
                    {categoryLabel(complaint.category)} · {complaint.area} ·{' '}
                    {istDateTime(complaint.submitted_at)} IST
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {complaint.compared_with_monitor && <Badge tone="ok">checked by a monitor</Badge>}
                  <Button
                    isBusy={downloading === complaint.reference}
                    busyLabel="Preparing…"
                    onClick={() => {
                      void downloadReport(complaint.reference);
                    }}
                    aria-label={`Download the PDF report for ${complaint.reference}`}
                  >
                    <FileDown aria-hidden className="size-3.5" />
                    PDF
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <p className="border-t border-border px-4 py-2.5 text-xs text-ink-subtle sm:px-5">
            {data?.note}
          </p>
        </>
      )}
      {downloadError && (
        <div className="border-t border-border p-4">
          <StatusMessage
            kind="error"
            title="The report could not be downloaded"
            detail={downloadError.message}
          />
        </div>
      )}
    </Card>
  );
}
