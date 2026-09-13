import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Cell, DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusMessage } from '@/components/ui/StatusMessage';
import { FederationDiagram } from '@/features/federation/FederationDiagram';
import { TransferCard } from '@/features/federation/TransferCard';
import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';

type FederationStatus = components['schemas']['FederationStatusResponse'];
type NodeCoverage = components['schemas']['NodeCoverageResponse'];

/**
 * Federation dashboard.
 *
 * This screen reports whether federation helps, and the honest answer is that the
 * data cannot yet say. Every comparison is shown with its interval, and a verdict
 * of helped or harmed appears only when the interval excludes zero and the effect
 * is large enough to act on.
 *
 * Coverage and transfer are separated on purpose. Coverage is counted from the
 * database on each request; the transfer results came from a training run and are
 * shown with the sample they rest on.
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
      <div className="mx-auto max-w-5xl space-y-6 px-4 pb-16 pt-6 sm:px-6 lg:pt-8">
        <PageHeader
          eyebrow="Step 4 · Share"
          title="Federation"
          description="Cities train one forecasting model together by exchanging weights, never raw readings — because no state hands another its database, and that is a governance wall rather than a bandwidth problem. Whether the exchange actually helps each city is a claim, and it is measured here."
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
            <p className="border-l-2 border-signal pl-4 text-[15px] leading-relaxed text-ink">
              {data.summary}
            </p>

            <FederationDiagram nodes={data.coverage} />

            <Card
              eyebrow="Measured on each request"
              title="Monitoring available to each node"
              description={`"Reporting" means a station produced a reading in the last ${String(data.reporting_window_hours)} hours — not the same as being listed as active, and the difference is the point.`}
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

            <section className="space-y-3">
              <div>
                <p className="eyebrow">Measured once, by a training run</p>
                <h2 className="text-lg font-semibold tracking-tight text-ink">
                  Did federating help?
                </h2>
                <p className="mt-0.5 text-[13px] text-ink-muted">
                  Each node compares three federated models with its own, on its own held-out data:
                  plain averaging and two personalised variants.
                </p>
              </div>
              {data.transfer.map((result) => (
                <TransferCard key={result.node} result={result} />
              ))}
            </section>

            <Card eyebrow="Next evidence" title="What would settle it">
              <p className="text-[13px] leading-relaxed text-ink-muted">
                The point estimates suggest a mechanism: Kanpur’s cleaner, less variable air is an
                easier forecasting task, and a global model that is roughly 97% Delhi would pull it
                toward a harder regime. That is plausible and matches the direction of every number
                above, and it is not established — on 23 held-out rows the intervals include no
                effect at all. What would settle it is more Kanpur history, not a different model.
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
