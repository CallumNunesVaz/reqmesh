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

// ── recent-entity tracking ──────────────────────────────────────────
interface RecentVisit {
  id: string;
  timestamp: number;
}

const RECENT_STORAGE_KEY = 'rt-recent-entities';
const RECENT_MAX = 20;
const RECENT_WINDOW_MS = 5 * 60_000;
const RECENT_BOOST = 50;

function loadRecentVisits(): RecentVisit[] {
  try {
    const raw = localStorage.getItem(RECENT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as RecentVisit[]) : [];
  } catch {
    return [];
  }
}

function saveRecentVisits(visits: RecentVisit[]): void {
  try { localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(visits)); } catch { /* quota */ }
}

/** Call every time the user navigates to an entity (palette, link, etc.). */
export function recordEntityVisit(id: string): void {
  const visits = loadRecentVisits().filter((v) => v.id !== id);
  visits.unshift({ id, timestamp: Date.now() });
  saveRecentVisits(visits.slice(0, RECENT_MAX));
}

/** Returns the recent-visit boost (0 or RECENT_BOOST) for a given entity id. */
function recentBoost(id: string, visits: RecentVisit[], now: number): number {
  for (const v of visits) {
    if (v.id === id && now - v.timestamp < RECENT_WINDOW_MS) return RECENT_BOOST;
  }
  return 0;
}

// ── fuzzy matching ──────────────────────────────────────────────────

/**
 * Returns a score >=0 if every character of `query` appears in order in
 * `target` (allowing gaps).  Higher = better.
 *   - Runs of consecutive matches are squared and summed.
 *   - Characters that land on a word-start boundary earn a +2 bonus.
 *   - Returns -1 when the query cannot be fulfilled.
 */
function fuzzyMatch(query: string, target: string): number {
  let qi = 0;
  let score = 0;
  let runLen = 0;
  let prevMatchIdx = -1;

  for (let ti = 0; ti < target.length && qi < query.length; ti++) {
    if (target[ti] === query[qi]) {
      if (prevMatchIdx === -1 || ti === prevMatchIdx + 1) {
        runLen++;
      } else {
        score += runLen * runLen;
        runLen = 1;
      }
      prevMatchIdx = ti;
      if (ti === 0 || target[ti - 1] === ' ' || target[ti - 1] === '-' || target[ti - 1] === '_') {
        score += 2;
      }
      qi++;
    }
  }

  if (qi === query.length) {
    score += runLen * runLen;
    return score;
  }
  return -1;
}

/**
 * Try the query against id/name/detail (and their space-stripped variants)
 * with optional single character-transpositions.  Returns the best fuzzy
 * score found, or -1.
 */
function bestFuzzyScore(query: string, id: string, name: string, detail: string): number {
  const queryLower = query.toLowerCase();
  const noSpaceQuery = queryLower.replace(/\s+/g, '');

  const targets: { text: string; weight: number }[] = [
    { text: id, weight: 1.0 },
    { text: name, weight: 1.05 },
  ];
  if (detail) targets.push({ text: detail, weight: 0.95 });

  for (let i = targets.length - 1; i >= 0; i--) {
    const stripped = targets[i].text.replace(/\s+/g, '');
    if (stripped !== targets[i].text) targets.push({ text: stripped, weight: targets[i].weight });
  }

  const queries = [queryLower];
  if (queryLower !== noSpaceQuery) queries.push(noSpaceQuery);

  let best = -1;

  for (const q of queries) {
    for (const t of targets) {
      const fs = fuzzyMatch(q, t.text);
      if (fs >= 0) {
        const weighted = Math.round(fs * t.weight);
        if (weighted > best) best = weighted;
      }
      // One adjacent character swap
      for (let i = 0; i < q.length - 1; i++) {
        const swapped = q.slice(0, i) + q[i + 1] + q[i] + q.slice(i + 2);
        const fs2 = fuzzyMatch(swapped, t.text);
        if (fs2 >= 0) {
          const weighted = Math.round(fs2 * t.weight * 0.7);
          if (weighted > best) best = weighted;
        }
      }
    }
  }

  return best;
}

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
 * Rank a query against the index.  Exact substring matches (score ≥
 * 1000) always rank above fuzzy matches (score < 1000).  Within each
 * band earlier / start-of-word matches rank higher.
 *
 * Recently-visited entities (last 5 minutes) get a +50 boost.
 * An empty query returns the index head unfiltered (browse mode).
 */
export function searchEntities(entities: IndexedEntity[], query: string, limit = 40): IndexedEntity[] {
  const q = query.trim().toLowerCase();
  if (!q) return entities.slice(0, limit);

  const words = q.split(/\s+/).filter(Boolean);
  const visits = loadRecentVisits();
  const now = Date.now();
  const scored: { e: IndexedEntity; score: number }[] = [];

  for (const e of entities) {
    const id = e.id.toLowerCase();
    const name = e.name.toLowerCase();
    const detail = (e.detail || '').toLowerCase();
    let score = -1;

    // ── exact / substring band (score ≥ 1000) ────────────────
    if (id === q) {
      score = 6000;
    } else if (id.startsWith(q)) {
      score = 5900;
    } else if (id.includes(q)) {
      score = 5800;
    } else if (name.startsWith(q)) {
      score = 5700;
    } else if (name.includes(q)) {
      score = 5600;
    } else if (detail.includes(q)) {
      score = 5400;
    } else if (words.length > 1) {
      const allMatch = words.every((w) => id.includes(w) || name.includes(w) || detail.includes(w));
      if (allMatch) {
        const matched = words.filter((w) => id.includes(w) || name.includes(w)).length;
        score = 5300 + matched * 100;
      }
    }

    // ── fuzzy fallback (score < 1000) ─────────────────────────
    if (score < 0) {
      const fs = bestFuzzyScore(q, id, name, detail);
      if (fs >= 0) score = Math.min(fs, 999);
    }

    if (score >= 0) {
      score += recentBoost(e.id, visits, now);
      scored.push({ e, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
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
