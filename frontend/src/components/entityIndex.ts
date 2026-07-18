import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';
import type { EntityKind } from './entities';

/** One row of the project-wide entity index: everything linkable, flattened. */
export interface IndexedEntity {
  kind: EntityKind;
  id: string;
  name: string;
  /** Plain-text detail line — description with any markup stripped. */
  detail: string;
  status?: string;
}

const stripMarkup = (s: string) => s.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

let cache: { key: string; promise: Promise<IndexedEntity[]> } | null = null;

/**
 * Every entity in the project, fetched once and shared by the command palette,
 * hover previews and auto-linking. Cached per (project, dataVersion) so an SSE
 * change event naturally invalidates it.
 */
export function loadEntityIndex(projectId: string): Promise<IndexedEntity[]> {
  const key = `${projectId}:${useStore.getState().dataVersion}`;
  if (cache?.key === key) return cache.promise;
  const promise = Promise.all([
    api.listRequirements(projectId).catch(() => []),
    api.listVerificationCases(projectId).catch(() => []),
    api.listComponents(projectId).catch(() => []),
    api.listSpecifications(projectId).catch(() => []),
    api.listChangeRequests(projectId).catch(() => []),
    api.listRisks(projectId).catch(() => []),
  ]).then(([reqs, vcs, comps, specs, crs, risks]) => [
    ...reqs.map((r): IndexedEntity => ({ kind: 'requirement', id: r.id, name: r.name, detail: stripMarkup(r.description || ''), status: r.status })),
    ...vcs.map((v): IndexedEntity => ({ kind: 'verification', id: v.id, name: v.name, detail: stripMarkup(v.description || ''), status: v.status })),
    ...comps.map((c): IndexedEntity => ({ kind: 'component', id: c.id, name: c.name, detail: stripMarkup(c.description || ''), status: c.type })),
    ...specs.map((s): IndexedEntity => ({ kind: 'specification', id: s.id, name: s.name, detail: stripMarkup(s.description || '') })),
    ...crs.map((c): IndexedEntity => ({ kind: 'change', id: c.id, name: c.title, detail: stripMarkup(c.description || ''), status: c.status })),
    ...risks.map((r): IndexedEntity => ({ kind: 'risk', id: r.id, name: r.title, detail: stripMarkup(r.description || ''), status: r.severity })),
  ]);
  cache = { key, promise };
  return promise;
}

/**
 * Rank a query against the index. Id matches beat name matches beat
 * description matches; within a band, earlier matches rank higher.
 * An empty query returns the index head unfiltered (browse mode).
 */
export function searchEntities(entities: IndexedEntity[], query: string, limit = 40): IndexedEntity[] {
  const q = query.trim().toLowerCase();
  if (!q) return entities.slice(0, limit);
  const scored: { e: IndexedEntity; score: number }[] = [];
  for (const e of entities) {
    const id = e.id.toLowerCase();
    const name = e.name.toLowerCase();
    let score: number;
    if (id === q) score = 0;
    else if (id.startsWith(q)) score = 1;
    else if (id.includes(q)) score = 2;
    else if (name.startsWith(q)) score = 3;
    else if (name.includes(q)) score = 4;
    else if (e.detail.toLowerCase().includes(q)) score = 5;
    else continue;
    scored.push({ e, score });
  }
  scored.sort((a, b) => a.score - b.score);
  return scored.slice(0, limit).map((s) => s.e);
}

/** id → kind for every entity in the project; feeds auto-linking. */
export function useEntityKinds(projectId?: string): Map<string, EntityKind> {
  const dataVersion = useStore((s) => s.dataVersion);
  const [kinds, setKinds] = useState<Map<string, EntityKind>>(new Map());
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    loadEntityIndex(projectId).then((list) => {
      if (alive) setKinds(new Map(list.map((e) => [e.id, e.kind])));
    });
    return () => { alive = false; };
  }, [projectId, dataVersion]);
  return kinds;
}
