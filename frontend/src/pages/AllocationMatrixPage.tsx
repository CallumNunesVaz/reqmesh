import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Search, Grid3X3, Check, Loader, ArrowUpDown, Download } from 'lucide-react';
import { api, type AllocationMatrixData, type MatrixAxis } from '../api/client';
import { EntityLink, type EntityKind } from '../components/entities';
import { REQUIREMENT_TYPES, REQUIREMENT_TYPE_META } from '../lib/requirementTypes';
import { matrixToCsv, type MatrixCsvInput } from '../lib/matrixCsv';
import { useAuthStore } from '../store/auth';

/** The three matrices, and the entity kind each column links to.
 *
 *  All three are views of a link the backend's registry already declares with
 *  `requirements` as its target, so the page switches axis rather than there
 *  being three near-identical pages. */
const AXES: { key: MatrixAxis; label: string; colKind: 'component' | 'verification' | 'risk' | 'baseline' }[] = [
  { key: 'components', label: 'Components', colKind: 'component' },
  { key: 'verification', label: 'Verification', colKind: 'verification' },
  { key: 'risks', label: 'Risks', colKind: 'risk' },
  { key: 'baselines', label: 'Baselines', colKind: 'baseline' },
];

const STATUS_CLASSES: Record<string, string> = {
  proposed: 'border-cs-blue/30 bg-cs-blue/5',
  in_review: 'border-cs-amber/30 bg-cs-amber/5',
  approved: 'border-cs-green/30 bg-cs-green/5',
  implemented: 'border-cs-purple/30 bg-cs-purple/5',
  verified: 'border-cs-teal/30 bg-cs-teal/5',
  rejected: 'border-cs-red/30 bg-cs-red/5',
  deprecated: 'border-cs-grey/30 bg-cs-grey/5',
};

export default function AllocationMatrixPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<AllocationMatrixData | null>(null);
  const [loading, setLoading] = useState(true);
  const [axis, setAxis] = useState<MatrixAxis>('components');
  const [rows, setRows] = useState<string>('requirements');
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [toggling, setToggling] = useState<Set<string>>(new Set());
  const [transpose, setTranspose] = useState(false);
  const [error, setError] = useState('');
  const editable = useAuthStore((s) => s.canEdit());

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const d = await api.getAllocationMatrix(projectId, axis, search, filterType,
        axis === 'baselines' ? rows : undefined);
      setData(d);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [projectId, axis, search, filterType, rows]);

  useEffect(() => { load(); }, [load]);

  const toggleAllocation = async (entityId: string, colId: string, current: boolean,
                                   rowKind: string = 'requirements') => {
    if (!projectId || !editable) return;
    const key = `${entityId}:${colId}`;
    setToggling((prev) => new Set(prev).add(key));
    try {
      await api.setAllocation(projectId, entityId, colId, !current, axis, rowKind, entityId);
      setData((prev) => {
        if (!prev) return prev;
        const newRows = prev.rows.map((r) => {
          if ((r.row_id || r.req_id) !== entityId) return r;
          return { ...r, cells: { ...r.cells, [colId]: !current },
                   allocated_to: !current ? (prev.columns.find(c => c.id === colId)?.name ?? colId) : '' };
        });
        // `total_rows` for both kinds, never `total_requirements`: the latter
        // counts the whole project, while the rows here are search/filter
        // narrowed. The server divides by the narrowed count too
        // (collab_routes.py:385), so picking the project total would make the
        // optimistic percentage disagree with the server's the moment a filter
        // is active, and snap back on the next refetch.
        const totalRows = prev.total_rows;
        const allocated = newRows.filter((r) => Object.values(r.cells).some(Boolean)).length;
        return { ...prev, rows: newRows, allocated, unallocated: totalRows - allocated,
                 allocation_pct: Math.round(allocated / totalRows * 100 * 10) / 10 };
      });
    } catch (err: any) {
      setError(err.message || 'Toggle failed');
    } finally {
      setToggling((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
  };

  const handleDownload = () => {
    if (!data || !projectId) return;
    const input: MatrixCsvInput = {
      columns: data.columns.map((c) => ({ id: c.id, label: c.name })),
      rows: data.rows.map((r) => ({
        id: r.row_id || r.req_id,
        label: data.row_kind === 'components' ? r.row_name : (r.req_name || r.row_name),
        cells: data.columns.map((c) => r.cells[c.id] ?? false),
      })),
      rowHeader: data.row_kind === 'components' ? 'Component' : 'Requirement',
    };
    const csv = matrixToCsv(input);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // The axis names the file: all four axes render at the same URL, so a
    // fixed name means the components export and the risks export land in the
    // downloads folder as indistinguishable siblings.
    a.download = `${projectId}-allocation-${axis}.csv`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    a.remove();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader size={20} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) {
    return <div className="p-6 text-center text-muted-foreground">No data available.</div>;
  }

  const displayRows = transpose ? data.columns : data.rows;
  const displayCols = transpose ? data.rows : data.columns;

  const colKind = AXES.find((a) => a.key === axis)!.colKind;
  const rowKind: EntityKind = data.row_kind === 'components' ? 'component' : 'requirement';

  const isAllocated = (row: any, col: any): boolean => {
    if (!transpose) return row.cells?.[col.id] ?? false;
    const origRow = data.rows.find((r) => (r.row_id || r.req_id) === col.row_id);
    return origRow?.cells?.[row.id] ?? false;
  };

  const handleToggle = (row: any, col: any) => {
    const entityId = transpose ? (col.row_id || col.req_id) : (row.row_id || row.req_id);
    const colId = transpose ? row.id : col.id;
    toggleAllocation(entityId, colId, isAllocated(row, col), data.row_kind);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b shrink-0">
        <div className="flex items-center justify-between max-w-full">
          <div>
            <h1 className="text-xl font-bold text-card-foreground">Allocation Matrix</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Requirements × {data.column_label} — each requirement {data.verb} the
              {' '}{data.column_label.toLowerCase()} it is ticked against. Click a cell to change it.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 bg-muted rounded-lg px-2.5 py-1.5 text-xs">
              <span className="text-cs-green font-semibold">{data.allocated}</span>
              <span className="text-muted-foreground">allocated</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-cs-red font-semibold">{data.unallocated}</span>
              <span className="text-muted-foreground">unallocated</span>
              <span className="text-muted-foreground ml-1">({data.allocation_pct}%)</span>
            </div>
            <button
              onClick={() => setTranspose((v) => !v)}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Transpose (swap rows and columns)"
            >
              <ArrowUpDown size={14} />
            </button>
            <button
              onClick={handleDownload}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Download this matrix as CSV"
            >
              <Download size={14} />
            </button>
          </div>
        </div>

        {/* Which relationship to show. */}
        <div className="flex gap-1 mt-3" role="tablist" aria-label="Matrix axis">
          {AXES.map((a) => (
            <button
              key={a.key}
              role="tab"
              aria-selected={axis === a.key}
              onClick={() => {
                if (axis === 'baselines' && a.key !== 'baselines') setRows('requirements');
                setAxis(a.key);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                axis === a.key
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>

        {/* Row source selector — visible only on the baselines tab. */}
        {axis === 'baselines' && (
          <div className="flex items-center gap-0.5 mt-2 text-xs">
            <span className="text-muted-foreground mr-1.5">Rows:</span>
            <label className="cursor-pointer">
              <input
                type="radio"
                name="rows"
                checked={rows === 'requirements'}
                onChange={() => setRows('requirements')}
                className="peer sr-only"
              />
              <span className={`px-2 py-0.5 rounded transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-primary/50 ${
                rows === 'requirements'
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}>
                Requirements
              </span>
            </label>
            <label className="cursor-pointer">
              <input
                type="radio"
                name="rows"
                checked={rows === 'components'}
                onChange={() => setRows('components')}
                className="peer sr-only"
              />
              <span className={`px-2 py-0.5 rounded transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-primary/50 ${
                rows === 'components'
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}>
                Components
              </span>
            </label>
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-2 mt-3">
          <div className="flex items-center gap-1.5 bg-muted rounded-lg px-2.5 py-1.5 flex-1 max-w-sm">
            <Search size={13} className="text-muted-foreground shrink-0" />
            <input
              className="bg-transparent text-xs outline-none flex-1"
              placeholder={`Filter requirements and ${data.column_label.toLowerCase()}…`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="bg-muted rounded-lg px-2.5 py-1.5 text-xs outline-none"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">All types</option>
            {REQUIREMENT_TYPES.map((t) => (
              <option key={t} value={t}>{REQUIREMENT_TYPE_META[t].label}</option>
            ))}
          </select>
        </div>

        {error && (
          <div className="mt-2 p-2 rounded bg-destructive/10 text-destructive text-xs border border-destructive/20">{error}</div>
        )}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto">
        {data.rows.length === 0 || data.columns.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-muted-foreground">
              <Grid3X3 size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">No data to display.</p>
            </div>
          </div>
        ) : (
          <table className="border-collapse text-xs w-full">
            {/* `w-full` so a sparse axis fills the pane instead of leaving a
                blank strip down its right side — the baselines axis is five
                columns and used 437px of 620px. Because `min-width` on the cells
                still holds, a dense axis (components is 81 columns) overflows
                exactly as before and the container scrolls. Both are the browser
                reflowing on width, so it tracks the resizable pane with no JS. */}
            <thead>
              <tr>
                {/* A width, not just a min-width: with `table-layout: auto` the
                    surplus is handed out in proportion to each column's
                    max-content, and the requirement names are far longer than a
                    tick, so this column would swallow nearly all of it and leave
                    the cells as narrow as they started. */}
                <th className="sticky top-0 left-0 z-20 bg-card border-b border-r px-3 py-2 text-left font-semibold text-muted-foreground w-[200px] min-w-[140px]">
                  {transpose ? data.column_label.replace(/s$/, '') : (data.row_kind === 'components' ? 'Component' : 'Requirement')}
                </th>
                {displayCols.map((col: any) => {
                  const isBaselineColumn = !transpose && axis === 'baselines';
                  if (isBaselineColumn) {
                    const dueDate: string | undefined = col.due_date;
                    const orphan = (col.order ?? 0) === 0;
                    return (
                      <th
                        key={col.id}
                        className={`sticky top-0 z-10 bg-card border-b px-2 py-2 whitespace-nowrap ${orphan ? 'opacity-50' : ''}`}
                        style={{ minWidth: 32 }}
                      >
                        <div className="flex flex-col items-start">
                          <span className={`text-[10px] font-semibold text-muted-foreground ${orphan ? 'italic' : ''}`}>
                            {col.name}
                          </span>
                          {dueDate && (
                            <span className="text-[9px] text-muted-foreground">{dueDate}</span>
                          )}
                        </div>
                      </th>
                    );
                  }
                  return (
                    <th
                      key={transpose ? (col.row_id || col.req_id) : col.id}
                      className="sticky top-0 z-10 bg-card border-b px-2 py-2 font-semibold text-muted-foreground whitespace-nowrap"
                      style={{ writingMode: 'vertical-rl', textOrientation: 'mixed', maxHeight: 160, minWidth: 32 }}
                    >
                      <EntityLink
                        kind={transpose ? rowKind : colKind as EntityKind}
                        id={transpose ? (col.row_id || col.req_id) : col.id}
                        subtype={transpose ? undefined : col.kind}
                        className="text-[10px]"
                      />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row: any) => (
                <tr key={transpose ? row.id : (row.row_id || row.req_id)}>
                  <td className={`sticky left-0 z-10 bg-card border-r border-b px-3 py-2 ${transpose ? '' : (row.req_status ? (STATUS_CLASSES[row.req_status] || '') : '')}`}>
                    <div className="flex flex-col">
                      {transpose && axis === 'baselines' ? (
                        <>
                          <span className="font-mono text-[10px] font-semibold text-muted-foreground">{row.name}</span>
                          <span className="text-[10px] text-muted-foreground truncate max-w-[130px]">
                            {row.kind}
                          </span>
                        </>
                      ) : (
                        <>
                          <EntityLink
                            kind={transpose ? colKind as EntityKind : rowKind}
                            id={transpose ? row.id : (row.row_id || row.req_id)}
                            subtype={transpose ? row.kind : (data.row_kind === 'components' ? row.row_type : undefined)}
                            className="font-mono"
                          />
                          <span className="text-[10px] text-muted-foreground truncate max-w-[130px]">
                            {transpose ? row.name : (row.row_name || row.req_name)}
                          </span>
                        </>
                      )}
                    </div>
                  </td>
                  {displayCols.map((col: any) => {
                    const allocated = isAllocated(row, col);
                    const cellKey = `${transpose ? row.id : (row.row_id || row.req_id)}:${transpose ? (col.row_id || col.req_id) : col.id}`;
                    const isToggling = toggling.has(cellKey);
                    return (
                      <td
                        key={transpose ? (col.row_id || col.req_id) : col.id}
                        className={`border-b text-center p-0 transition-colors ${allocated ? 'bg-cs-green/15' : ''} ${
                          editable
                            ? `cursor-pointer ${allocated ? 'hover:bg-cs-green/20' : 'hover:bg-accent/30'}`
                            : ''
                        }`}
                        onClick={editable ? () => handleToggle(row, col) : undefined}
                        title={editable
                          ? `${row.row_name || row.req_name || row.name} ${data.verb} ${col.name || (col.row_name || col.req_name)}`
                          : 'Read-only in viewing mode — enable editing to change allocations'}
                      >
                        {isToggling ? (
                          <Loader size={12} className="animate-spin mx-auto text-muted-foreground" />
                        ) : allocated ? (
                          <Check size={14} className="mx-auto text-cs-green" />
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
