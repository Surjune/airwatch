import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Cell, DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { Stat, StatRow } from '@/components/ui/Stat';
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
 * This screen exists to show a result that did not go the way the design hoped,
 * which is the reason it is worth showing at all. Federated averaging was meant
 * to let a data-poor city borrow a data-rich one's model; measured, it made the
 * sparse node worse and the negative-transfer check recommended it keep its own.
 * A dashboard that buried that would be advertising an architecture rather than
 * reporting a measurement.
 *
 * Coverage and transfer are separated on purpose. Coverage is counted from the
 * database on each request; the transfer result came from a training run and is
 * shown with the sample it rests on.
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
              description="Each node compares the federated global model against its own, on its own held-out data. Measured once by a training run, not recomputed here."
            >
              <div className="space-y-3">
                {data.transfer.map((result) => (
                  <TransferCard key={result.node} result={result} />
                ))}
              </div>
            </Card>

            <Card title="Why it went that way">
              <p className="text-sm leading-relaxed text-ink-muted">
                The mechanism is legible rather than mysterious. Kanpur&rsquo;s own model is better
                than Delhi&rsquo;s because its air is cleaner and less variable, so its forecasting
                task is easier. Averaging weights by sample count makes the global model roughly 97%
                Delhi, and that drags Kanpur toward a harder regime it does not inhabit — textbook
                non-IID harm. Personalisation, a shared representation with a local head, is the
                standard answer and is the honest next thing to try.
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

function TransferCard({ result }: { readonly result: TransferResult }) {
  const percent = (result.improvement * 100).toFixed(1);

  return (
    <div
      className={`rounded-[--radius-card] border p-3.5 ${
        result.is_harmed ? 'border-danger/30 bg-danger-subtle' : 'border-border bg-surface'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold capitalize text-ink">{result.node}</h3>
        <Badge tone={result.is_harmed ? 'danger' : 'neutral'}>
          {result.improvement >= 0 ? '+' : ''}
          {percent}%
        </Badge>
      </div>

      <div className="mt-3">
        <StatRow>
          <Stat label="Its own model" value={result.local_mae.toFixed(2)} note="µg/m³ MAE" />
          <Stat
            label="Federated model"
            value={result.global_mae.toFixed(2)}
            note="µg/m³ MAE, same holdout"
            tone={result.is_harmed ? 'danger' : 'neutral'}
          />
        </StatRow>
      </div>

      <p className="mt-3 text-sm font-medium text-ink">Recommendation: {result.recommendation}.</p>
      <p className="mt-1 text-xs leading-relaxed text-ink-muted">
        Fitted on {result.train_rows.toLocaleString()} rows, tested on{' '}
        {result.test_rows.toLocaleString()}.
        {result.test_rows < THIN_HOLDOUT_ROWS &&
          ' A holdout this small makes the figure a signal rather than a settled fact.'}
      </p>
    </div>
  );
}
