import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, Grid3X3, Check, X, Loader, ArrowUpDown } from 'lucide-react';
import { api, type AllocationMatrixData } from '../api/client';
import { EntityLink } from '../components/entities';
import { useAuthStore } from '../store/auth';

const STATUS_CLASSES: Record<string, string> = {
  proposed: 'border-blue-500/30 bg-blue-500/5',
  in_review: 'border-amber-500/30 bg-amber-500/5',
  approved: 'border-green-500/30 bg-green-500/5',
  implemented: 'border-purple-500/30 bg-purple-500/5',
  verified: 'border-teal-500/30 bg-teal-500/5',
  rejected: 'border-red-500/30 bg-red-500/5',
  deprecated: 'border-zinc-500/30 bg-zinc-500/5',
};

export default function AllocationMatrixPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<AllocationMatrixData | null>(null);
  const [loading, setLoading] = useState(true);
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
      const d = await api.getAllocationMatrix(projectId, search, filterType);
      setData(d);
    } catch (err: any) {
      setError(err.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [projectId, search, filterType]);

  useEffect(() => { load(); }, [load]);

  const toggleAllocation = async (reqId: string, compId: string, current: boolean) => {
    if (!projectId || !editable) return;
    const key = `${reqId}:${compId}`;
    setToggling((prev) => new Set(prev).add(key));
    try {
      await api.setAllocation(projectId, reqId, compId, !current);
      setData((prev) => {
        if (!prev) return prev;
        const newRows = prev.rows.map((r) => {
          if (r.req_id !== reqId) return r;
          return { ...r, cells: { ...r.cells, [compId]: !current },
                   allocated_to: !current ? (prev.columns.find(c => c.comp_id === compId)?.comp_name ?? compId) : '' };
        });
        const allocated = newRows.filter((r) => Object.values(r.cells).some(Boolean)).length;
        return { ...prev, rows: newRows, allocated, unallocated: prev.total_requirements - allocated,
                 allocation_pct: Math.round(allocated / prev.total_requirements * 100 * 10) / 10 };
      });
    } catch (err: any) {
      setError(err.message || 'Toggle failed');
    } finally {
      setToggling((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
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

  const rows = transpose ? data.columns : data.rows;
  const cols = transpose ? data.rows : data.columns;

  const isAllocated = (row: any, col: any): boolean => {
    if (!transpose) return row.cells?.[col.comp_id] ?? false;
    const origRow = data.rows.find((r) => r.req_id === col.req_id);
    return origRow?.cells?.[row.comp_id] ?? false;
  };

  const handleToggle = (row: any, col: any) => {
    const reqId = transpose ? col.req_id : row.req_id;
    const compId = transpose ? row.comp_id : col.comp_id;
    const current = isAllocated(row, col);
    toggleAllocation(reqId, compId, current);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b shrink-0">
        <div className="flex items-center justify-between max-w-full">
          <div>
            <h1 className="text-xl font-bold text-card-foreground">Allocation Matrix</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Requirements × Components — click a cell to allocate or deallocate.
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
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2 mt-3">
          <div className="flex items-center gap-1.5 bg-muted rounded-lg px-2.5 py-1.5 flex-1 max-w-sm">
            <Search size={13} className="text-muted-foreground shrink-0" />
            <input
              className="bg-transparent text-xs outline-none flex-1"
              placeholder="Filter requirements and components…"
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
            <option value="functional">Functional</option>
            <option value="non_functional_performance">Non-Functional</option>
            <option value="interface">Interface</option>
            <option value="safety">Safety</option>
            <option value="regulatory_compliance">Regulatory</option>
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
          <table className="border-collapse text-xs">
            <thead>
              <tr>
                <th className="sticky top-0 left-0 z-20 bg-card border-b border-r px-3 py-2 text-left font-semibold text-muted-foreground min-w-[140px]">
                  {transpose ? 'Component' : 'Requirement'}
                </th>
                {cols.map((col: any) => (
                  <th
                    key={transpose ? col.req_id : col.comp_id}
                    className="sticky top-0 z-10 bg-card border-b px-2 py-2 font-semibold text-muted-foreground whitespace-nowrap"
                    style={{ writingMode: 'vertical-rl', textOrientation: 'mixed', maxHeight: 160, minWidth: 32 }}
                  >
                    <EntityLink
                      kind={transpose ? 'requirement' : 'component'}
                      id={transpose ? col.req_id : col.comp_id}
                      className="text-[10px]"
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row: any) => (
                <tr key={transpose ? row.comp_id : row.req_id}>
                  <td className={`sticky left-0 z-10 bg-card border-r border-b px-3 py-2 ${transpose ? '' : (STATUS_CLASSES[row.req_status] || '')}`}>
                    <div className="flex flex-col">
                      <EntityLink kind={transpose ? 'component' : 'requirement'} id={transpose ? row.comp_id : row.req_id} className="font-mono" />
                      <span className="text-[10px] text-muted-foreground truncate max-w-[130px]">
                        {transpose ? row.comp_name : row.req_name}
                      </span>
                    </div>
                  </td>
                  {cols.map((col: any) => {
                    const allocated = isAllocated(row, col);
                    const cellKey = `${transpose ? row.comp_id : row.req_id}:${transpose ? col.req_id : col.comp_id}`;
                    const isToggling = toggling.has(cellKey);
                    return (
                      <td
                        key={transpose ? col.req_id : col.comp_id}
                        className={`border-b text-center p-0 cursor-pointer transition-colors ${
                          allocated ? 'bg-cs-green/15 hover:bg-cs-green/20' : 'hover:bg-accent/30'
                        }`}
                        onClick={() => handleToggle(row, col)}
                        title={`${row.req_name || row.comp_name} → ${col.comp_name || col.req_name}`}
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
