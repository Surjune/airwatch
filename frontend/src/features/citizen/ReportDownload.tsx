import { FileDown } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { useReportDownload } from '@/hooks/useComplaints';

/**
 * The reference a resident was given, and the PDF report to attach to a grievance.
 *
 * Shown straight after a submission, because that is when someone who came to
 * complain wants the document -- not after finding a separate screen.
 */
export function ReportDownload({ reference }: { readonly reference: string }) {
  const { downloading, downloadError, downloadReport } = useReportDownload();

  return (
    <div className="mt-4 space-y-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-ink-muted">
          Your reference <span className="figure font-medium text-ink">{reference}</span>
        </p>
        <Button
          variant="primary"
          size="md"
          isBusy={downloading === reference}
          busyLabel="Preparing PDF…"
          onClick={() => {
            void downloadReport(reference);
          }}
        >
          <FileDown aria-hidden className="size-4" />
          Download PDF report
        </Button>
      </div>
      <p className="text-xs leading-relaxed text-ink-subtle">
        What you reported, what was measured, the nearest monitor, and who is responsible for this
        spot — ready to attach to a complaint with your district or state pollution board.
      </p>
      {downloadError && (
        <StatusMessage
          kind="error"
          title="The report could not be downloaded"
          detail={downloadError.message}
        />
      )}
    </div>
  );
}
