import type { ReactNode } from 'react';

interface DataTableProps {
  readonly caption: string;
  readonly columns: readonly string[];
  readonly children: ReactNode;
  /** Columns whose values are numbers, right-aligned and given tabular figures. */
  readonly numericColumns?: readonly number[];
}

/**
 * The single table.
 *
 * Wide tables scroll inside their own container rather than pushing the page
 * sideways, and the caption is real rather than visually hidden decoration: a
 * screen reader reaching a grid of numbers needs to be told what the grid is.
 */
export function DataTable({ caption, columns, children, numericColumns = [] }: DataTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-left">
            {columns.map((column, index) => (
              <th
                key={column}
                scope="col"
                className={`px-4 py-2 text-xs font-medium text-ink-subtle ${
                  numericColumns.includes(index) ? 'text-right' : ''
                }`}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  );
}

interface CellProps {
  readonly children: ReactNode;
  readonly numeric?: boolean;
  readonly muted?: boolean;
}

/** One table cell, so alignment and padding are not restated per screen. */
export function Cell({ children, numeric = false, muted = false }: CellProps) {
  return (
    <td
      className={`px-4 py-2 ${numeric ? 'text-right' : ''} ${muted ? 'text-ink-muted' : 'text-ink'}`}
    >
      {children}
    </td>
  );
}
