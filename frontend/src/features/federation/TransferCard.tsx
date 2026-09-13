import { Badge } from '@/components/ui/Badge';
import { Cell, DataTable } from '@/components/ui/DataTable';
import type { components } from '@/lib/api-types';

type TransferResult = components['schemas']['TransferResultResponse'];

/** Below this many test rows, a result is labelled as a signal rather than a fact. */
const THIN_HOLDOUT_ROWS = 100;

/** Human wording and tone per verdict. Tone carries meaning, never decoration. */
const VERDICTS: Record<string, { label: string; tone: 'danger' | 'ok' | 'neutral' | 'warn' }> = {
  helped: { label: 'helped', tone: 'ok' },
  harmed: { label: 'harmed', tone: 'danger' },
  no_practical_difference: { label: 'no practical difference', tone: 'neutral' },
  inconclusive: { label: 'inconclusive', tone: 'warn' },
};

const FALLBACK_VERDICT = { label: 'unknown', tone: 'neutral' } as const;

/** One node's comparison of federated models against its own, with every interval. */
export function TransferCard({ result }: { readonly result: TransferResult }) {
  return (
    <article className="overflow-hidden rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-3 sm:px-5">
        <h3 className="text-[15px] font-semibold capitalize text-ink">{result.node}</h3>
        <span className="figure text-xs text-ink-muted">
          own model {result.local_mae.toFixed(2)} µg/m³ · tested on {result.test_rows} rows
        </span>
      </header>

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

      <div className="border-t border-border px-4 py-3 sm:px-5">
        <p className="text-sm font-medium text-ink">Recommendation: {result.recommendation}.</p>
        {result.test_rows < THIN_HOLDOUT_ROWS && (
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
            A holdout of {result.test_rows} rows gives intervals wide enough to include zero for
            every model here, so none of these differences can be told apart from no effect —
            however they look as point estimates.
          </p>
        )}
      </div>
    </article>
  );
}
