import { useEffect, useState } from 'react';

import { StatusMessage } from '@/components/ui/StatusMessage';
import type { components } from '@/lib/api-types';
import { ApiError, get } from '@/lib/api-client';

type FederationStatus = components['schemas']['FederationStatusResponse'];
type NodeCoverage = components['schemas']['NodeCoverageResponse'];
type TransferResult = components['schemas']['TransferResultResponse'];

/**
 * Federation dashboard.
 *
 * This screen exists to show a result that did not go the way the design hoped,
 * which is the reason it is worth showing at all. Federated averaging was
 * supposed to let a data-poor city borrow a data-rich one's model; measured, it
 * made the sparse node worse and the negative-transfer check recommended it keep
 * its own. A dashboard that buried that would be advertising an architecture
 * rather than reporting a measurement.
 *
 * Coverage and transfer are separated on purpose. Coverage is counted from the
 * database on each request; the transfer result came from a training run and is
 * shown with the sample it rests on, because a 23-row holdout is a signal and
 * not a settled fact.
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
    <div className="mx-auto flex h-full min-h-0 max-w-4xl flex-col gap-4 overflow-y-auto p-6">
      <header>
        <h2 className="text-base font-semibold">Federation</h2>
        <p className="mt-1 text-sm text-neutral-600">
          Cities exchange model weights rather than raw data, because no state hands another its
          database — that is a governance wall, not a bandwidth problem. Whether the exchange
          actually helps is a claim, and it is measured here.
        </p>
      </header>

      {error ? (
        <StatusMessage
          kind="error"
          title="Could not load federation status"
          detail={error.message}
          {...(error.requestId ? { requestId: error.requestId } : {})}
        />
      ) : isLoading || !data ? (
        <StatusMessage kind="loading" title="Reading node coverage…" />
      ) : (
        <>
          <p className="rounded border border-neutral-300 bg-white p-3 text-sm">{data.summary}</p>

          <section>
            <h3 className="text-sm font-semibold">Monitoring available to each node</h3>
            <p className="mb-2 text-xs text-neutral-600">
              Counted now. &ldquo;Reporting&rdquo; means a station produced a reading in the last{' '}
              {data.reporting_window_hours} hours — which is not the same as being listed as
              active, and the difference is the point.
            </p>
            <div className="overflow-hidden rounded border border-neutral-200 bg-white">
              <table className="w-full text-sm">
                <thead className="border-b border-neutral-200 text-left text-xs text-neutral-600">
                  <tr>
                    <th className="px-3 py-2 font-medium">Node</th>
                    <th className="px-3 py-2 font-medium">Stations</th>
                    <th className="px-3 py-2 font-medium">Reporting</th>
                    <th className="px-3 py-2 font-medium">Readings held</th>
                    <th className="px-3 py-2 font-medium">State</th>
                  </tr>
                </thead>
                <tbody>
                  {data.coverage.map((node) => (
                    <CoverageRow key={node.node} node={node} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-semibold">Did federating help?</h3>
            <p className="mb-2 text-xs text-neutral-600">
              Each node compares the federated global model against its own, on its own held-out
              data. Measured once by a training run, not recomputed here.
            </p>
            <div className="space-y-2">
              {data.transfer.map((result) => (
                <TransferCard key={result.node} result={result} />
              ))}
            </div>
          </section>

          <p className="text-xs text-neutral-600">
            The mechanism is legible rather than mysterious. Kanpur&rsquo;s own model is better than
            Delhi&rsquo;s because its air is cleaner and less variable, so its forecasting task is
            easier. Averaging weights by sample count makes the global model roughly 97% Delhi, and
            that drags Kanpur toward a harder regime it does not inhabit — textbook non-IID harm.
            Personalisation, a shared representation with a local head, is the standard answer and
            is the honest next thing to try.
          </p>
        </>
      )}
    </div>
  );
}

function CoverageRow({ node }: { readonly node: NodeCoverage }) {
  const state = node.is_unmonitored
    ? { label: 'no data ever', className: 'bg-red-100 text-red-800' }
    : node.is_stale
      ? { label: 'stale here', className: 'bg-amber-100 text-amber-900' }
      : { label: 'reporting', className: 'bg-emerald-100 text-emerald-800' };

  return (
    <tr className="border-b border-neutral-100">
      <td className="px-3 py-1.5 capitalize">{node.node}</td>
      <td className="px-3 py-1.5 tabular-nums">{node.stations}</td>
      <td className="px-3 py-1.5 tabular-nums">
        {node.reporting_stations}
        {node.silent_stations > 0 && (
          <span className="ml-2 text-xs text-neutral-500">
            {node.silent_stations} silent
          </span>
        )}
      </td>
      <td className="px-3 py-1.5 tabular-nums">{node.readings.toLocaleString()}</td>
      <td className="px-3 py-1.5">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${state.className}`}>
          {state.label}
        </span>
      </td>
    </tr>
  );
}

function TransferCard({ result }: { readonly result: TransferResult }) {
  const percent = (result.improvement * 100).toFixed(1);

  return (
    <div
      className={`rounded border p-3 ${
        result.is_harmed ? 'border-red-300 bg-red-50' : 'border-neutral-200 bg-white'
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold capitalize">{result.node}</h4>
        <span
          className={`text-sm font-medium ${result.is_harmed ? 'text-red-800' : 'text-neutral-700'}`}
        >
          {result.improvement >= 0 ? '+' : ''}
          {percent}%
        </span>
      </div>

      <p className="mt-1 text-sm">
        Its own model scores <strong>{result.local_mae.toFixed(2)}</strong> µg/m³; the federated
        model scores <strong>{result.global_mae.toFixed(2)}</strong> on the same holdout.
      </p>
      <p className="mt-1 text-sm font-medium">Recommendation: {result.recommendation}.</p>
      <p className="mt-1 text-xs text-neutral-600">
        Fitted on {result.train_rows.toLocaleString()} rows, tested on{' '}
        {result.test_rows.toLocaleString()}.
        {result.test_rows < 100 &&
          ' A holdout this small makes the figure a signal rather than a settled fact.'}
      </p>
    </div>
  );
}
