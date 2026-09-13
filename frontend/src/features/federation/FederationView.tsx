import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Cell, DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';

type FederationStatus = components['schemas']['FederationStatusResponse'];
type NodeCoverage = components['schemas']['NodeCoverageResponse'];
type TransferResult = components['schemas']['TransferResultResponse'];

/** Below this many test rows, a result is labelled as a signal rather than a fact. */
const THIN_HOLDOUT_ROWS = 100;

/**
 * Federation dashboard.
 *
 * This screen reports whether federation helps, and the honest answer is that the
 * data cannot yet say. An earlier version of it declared that averaging "harmed"
 * Kanpur, on 23 held-out rows whose bootstrap interval spans zero; the claim was
 * stated with a certainty the evidence never had. Every comparison is now shown
 * with its interval, and a verdict of helped or harmed appears only when the
 * interval excludes zero and the effect is large enough to act on.
 *
 * Coverage and transfer are separated on purpose. Coverage is counted from the
 * database on each request; the transfer results came from a training run and
 * are shown with the sample they rest on.
 */
export function FederationView() {
  const [data, setData] = useState<FederationStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    get<FederationStatus>('/federation/status', { signal: controller.signal })
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

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-5 p-4 sm:p-6">
        <PageHeader
          title="Federation"
          description="Cities exchange model weights rather than raw data, because no state hands another its database — that is a governance wall, not a bandwidth problem. Whether the exchange actually helps is a claim, and it is measured here."
        />

        {error ? (
          <StatusMessage
            kind="error"
            title="Could not load federation status"
            detail={error.message}
            {...(error.requestId ? { requestId: error.requestId } : {})}
          />
        ) : isLoading || !data ? (
          <Card>
            <Skeleton label="Reading node coverage" rows={4} />
          </Card>
        ) : (
          <>
            <Card>
              <p className="text-sm leading-relaxed text-ink">{data.summary}</p>
            </Card>

            <Card
              title="Monitoring available to each node"
              description={`"Reporting" means a station produced a reading in the last ${String(data.reporting_window_hours)} hours — which is not the same as being listed as active, and the difference is the point.`}
              flush
            >
              <DataTable
                caption="Stations, reporting stations and readings held, per federated node"
                columns={['Node', 'Stations', 'Reporting', 'Readings held', 'State']}
                numericColumns={[1, 2, 3]}
              >
                {data.coverage.map((node) => (
                  <CoverageRow key={node.node} node={node} />
                ))}
              </DataTable>
            </Card>

            <Card
              title="Did federating help?"
              description="Each node compares three federated models against its own, on its own held-out data: plain averaging, and two personalised variants. Measured once by a training run, not recomputed here."
            >
              <div className="space-y-3">
                {data.transfer.map((result) => (
                  <TransferCard key={result.node} result={result} />
                ))}
              </div>
            </Card>

            <Card title="What would settle it">
              <p className="text-sm leading-relaxed text-ink-muted">
                The point estimates suggest a mechanism — Kanpur&rsquo;s cleaner, less variable air
                is an easier forecasting task, and a global model that is roughly 97% Delhi would
                pull it toward a harder regime, which a local intercept undoes. That story is
                plausible and matches the direction of every number above. It is not established:
                on 23 held-out rows the intervals are wide enough to include no effect at all. What
                would settle it is more Kanpur history, not a different model — a holdout several
                times larger would narrow those intervals enough to tell the options apart.
              </p>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function CoverageRow({ node }: { readonly node: NodeCoverage }) {
  return (
    <tr>
      <Cell>
        <span className="font-medium capitalize">{node.node}</span>
      </Cell>
      <Cell numeric>{node.stations}</Cell>
      <Cell numeric>
        {node.reporting_stations}
        {node.silent_stations > 0 && (
          <span className="ml-2 text-xs text-ink-subtle">{node.silent_stations} silent</span>
        )}
      </Cell>
      <Cell numeric muted>
        {node.readings.toLocaleString()}
      </Cell>
      <Cell>
        {node.is_unmonitored ? (
          <Badge tone="danger" dot>
            no data ever
          </Badge>
        ) : node.is_stale ? (
          <Badge tone="warn" dot>
            stale here
          </Badge>
        ) : (
          <Badge tone="ok" dot>
            reporting
          </Badge>
        )}
      </Cell>
    </tr>
  );
}

/** Human wording and tone per verdict. Tone carries meaning, never decoration. */
const VERDICTS: Record<string, { label: string; tone: 'danger' | 'ok' | 'neutral' | 'warn' }> = {
  helped: { label: 'helped', tone: 'ok' },
  harmed: { label: 'harmed', tone: 'danger' },
  no_practical_difference: { label: 'no practical difference', tone: 'neutral' },
  inconclusive: { label: 'inconclusive', tone: 'warn' },
};

const FALLBACK_VERDICT = { label: 'unknown', tone: 'neutral' } as const;

function TransferCard({ result }: { readonly result: TransferResult }) {
  return (
    <div className="rounded-[--radius-card] border border-border bg-surface p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold capitalize text-ink">{result.node}</h3>
        <span className="text-xs text-ink-muted">
          own model {result.local_mae.toFixed(2)} µg/m³ · tested on {result.test_rows} rows
        </span>
      </div>

      <DataTable
        caption={`Federated models compared with ${result.node}'s own model`}
        columns={['Model', 'Error', 'Gain vs own', '95% interval', 'Verdict']}
        numericColumns={[1, 2, 3]}
      >
        {result.candidates.map((candidate) => {
          const verdict = VERDICTS[candidate.verdict] ?? FALLBACK_VERDICT;
          return (
            <tr key={candidate.candidate}>
              <Cell>{candidate.candidate}</Cell>
              <Cell numeric>{candidate.mae.toFixed(2)}</Cell>
              <Cell numeric>
                {candidate.gain >= 0 ? '+' : ''}
                {candidate.gain.toFixed(3)}
              </Cell>
              <Cell numeric muted>
                {candidate.interval_low.toFixed(3)} to {candidate.interval_high.toFixed(3)}
              </Cell>
              <Cell>
                <Badge tone={verdict.tone}>{verdict.label}</Badge>
              </Cell>
            </tr>
          );
        })}
      </DataTable>

      <p className="mt-3 text-sm font-medium text-ink">Recommendation: {result.recommendation}.</p>
      {result.test_rows < THIN_HOLDOUT_ROWS && (
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          A holdout of {result.test_rows} rows gives intervals wide enough to include zero for every
          model here, so none of these differences can be told apart from no effect — however they
          look as point estimates.
        </p>
      )}
    </div>
  );
}
