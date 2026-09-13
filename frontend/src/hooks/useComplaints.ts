import { useCallback, useEffect, useState } from 'react';

import type { components } from '@/lib/api-types';
import { ApiError, download, get } from '@/lib/api-client';
import { saveFile } from '@/lib/complaints';
import { deviceId } from '@/lib/device';

export type Complaints = components['schemas']['ComplaintsResponse'];
export type Complaint = components['schemas']['ComplaintSummaryResponse'];

/** Header the API reads a resident's own records by, kept out of every URL. */
const DEVICE_HEADER = 'X-Device-ID';

export interface ComplaintDownloads {
  /** The reference currently downloading, so its button can say so. */
  readonly downloading: string | null;
  readonly downloadError: ApiError | null;
  readonly downloadReport: (reference: string) => Promise<void>;
}

/** Download the PDF report for one of this browser's submissions. */
export function useReportDownload(): ComplaintDownloads {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<ApiError | null>(null);

  const downloadReport = useCallback(async (reference: string) => {
    setDownloading(reference);
    setDownloadError(null);
    try {
      const file = await download(`/citizen/complaints/${encodeURIComponent(reference)}/pdf`, {
        headers: { [DEVICE_HEADER]: deviceId() },
        fallbackName: `airwatch-${reference}.pdf`,
      });
      saveFile(file.blob, file.filename);
    } catch (cause: unknown) {
      setDownloadError(
        cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Download failed.', 0),
      );
    } finally {
      setDownloading(null);
    }
  }, []);

  return { downloading, downloadError, downloadReport };
}

export interface ComplaintList extends ComplaintDownloads {
  readonly data: Complaints | null;
  readonly error: ApiError | null;
  readonly isLoading: boolean;
}

/** This browser's own submissions, newest first, with a report download for each. */
export function useComplaints(): ComplaintList {
  const [data, setData] = useState<Complaints | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const downloads = useReportDownload();

  useEffect(() => {
    const controller = new AbortController();
    get<Complaints>('/citizen/complaints', {
      signal: controller.signal,
      headers: { [DEVICE_HEADER]: deviceId() },
    })
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          cause instanceof ApiError ? cause : new ApiError('unknown_error', 'Request failed.', 0),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, []);

  return { data, error, isLoading, ...downloads };
}
