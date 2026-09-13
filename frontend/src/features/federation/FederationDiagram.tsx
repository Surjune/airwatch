import { ArrowDownUp } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import type { components } from '@/lib/api-types';

type NodeCoverage = components['schemas']['NodeCoverageResponse'];

/**
 * What crosses a city boundary in the federation, and what never does.
 *
 * Each node is drawn with the monitoring it holds, because that asymmetry is the
 * whole premise: a city with sixty monitors and a city with none train one model
 * together, and only weights travel between them.
 */
export function FederationDiagram({ nodes }: { readonly nodes: readonly NodeCoverage[] }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4 sm:p-5">
      <p className="eyebrow">How the exchange works</p>
      <ul className="mt-3 grid gap-3 sm:grid-cols-3">
        {nodes.map((node) => (
          <li key={node.node} className="rounded-sm border border-border bg-paper p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold capitalize text-ink">{node.node} node</span>
              <span aria-hidden className="size-2 rounded-full bg-ink" />
            </div>
            <p className="figure mt-2 text-[13px] text-ink">
              {node.stations} stations · {node.readings.toLocaleString('en-IN')} readings
            </p>
            <p className="mt-1 text-xs text-ink-muted">Held in its own database</p>
            <div className="mt-2">
              {node.is_unmonitored ? (
                <Badge tone="danger">has no data of its own</Badge>
              ) : node.is_stale ? (
                <Badge tone="warn">stale</Badge>
              ) : (
                <Badge tone="ok">training locally</Badge>
              )}
            </div>
          </li>
        ))}
      </ul>

      <div className="my-3 flex items-center gap-3 text-xs text-ink-muted">
        <span aria-hidden className="h-px flex-1 border-t border-dashed border-ink/30" />
        <span className="inline-flex items-center gap-1.5 font-medium text-ink">
          <ArrowDownUp aria-hidden className="size-3.5 text-signal" />
          model weights only
        </span>
        <span aria-hidden className="h-px flex-1 border-t border-dashed border-ink/30" />
      </div>

      <div className="rounded-sm border border-ink bg-ink px-4 py-3 text-paper">
        <p className="text-sm font-semibold">Aggregator · FedAvg over Flower</p>
        <p className="mt-1 text-xs leading-relaxed text-paper/75">
          Opens no database. Round one exchanges per-feature sums to build a shared scaler; every
          round after exchanges weights, and each node scores the global model on its own held-out
          rows. Raw readings never leave a node.
        </p>
      </div>
    </div>
  );
}
