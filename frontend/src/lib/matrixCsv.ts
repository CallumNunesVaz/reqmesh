export interface MatrixCsvInput {
  /** Column headings, left to right, excluding the row-label column. */
  columns: { id: string; label: string }[];
  /** One entry per row, in display order. */
  rows: { id: string; label: string; cells: boolean[] }[];
  /** Heading for the first column, e.g. "Requirement". */
  rowHeader: string;
}

function csvField(value: string): string {
  const needsQuoting = /[,"\n\r]|^ | $/.test(value);
  return needsQuoting ? `"${value.replace(/"/g, '""')}"` : value;
}

export function matrixToCsv(input: MatrixCsvInput): string {
  const header = [input.rowHeader, ...input.columns.map((c) => c.label)];
  const lines = [header.map(csvField).join(',')];

  for (const row of input.rows) {
    const fields = [row.label, ...row.cells.map((c) => (c ? 'x' : ''))];
    lines.push(fields.map(csvField).join(','));
  }

  return lines.join('\r\n') + '\r\n';
}
