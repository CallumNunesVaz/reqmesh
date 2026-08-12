import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useParams } from 'react-router-dom';
import { GuardedLink } from './navGuard';
import { copyText } from '../lib/clipboard';
import {
  ClipboardList, CheckCircle2, Boxes, FileText, GitPullRequest, AlertTriangle,
  Box, Layers, Cog, Binary, Plug, Link2, Check, Scale, Sigma, FlaskConical,
  History, MessageSquare,
} from 'lucide-react';
import { loadEntityIndex, type IndexedEntity } from './entityIndex';

/** Everything in a project that can be referenced from somewhere else. */
export type EntityKind =
  | 'requirement' | 'verification' | 'component' | 'specification' | 'change' | 'risk'
  | 'decision' | 'definition' | 'analysis' | 'baseline' | 'comment';

interface EntityMeta {
  icon: typeof Box;
  cls: string;
  label: string;
  /**
   * Where a reference to this entity navigates to, or absent when it has no
   * page of its own. A comment is that case: search returns its id, author and
   * text but nothing identifying the entity it hangs off, so there is nowhere
   * honest to send the reader. `EntityLink` renders those as a plain label
   * rather than inventing a destination.
   */
  path?: (projectId: string, id: string) => string;
}

/**
 * The single source of truth for how each entity kind looks and where it
 * lives. Only requirements have a detail page; the others deep-link into
 * their list page via `?focus=`, which selects and scrolls to the item.
 */
export const ENTITY_META: Record<EntityKind, EntityMeta> = {
  requirement: {
    icon: ClipboardList,
    cls: 'text-cs-blue',
    label: 'Requirement',
    path: (p, id) => `/project/${p}/requirements/${encodeURIComponent(id)}`,
  },
  verification: {
    icon: CheckCircle2,
    cls: 'text-cs-green',
    label: 'Verification Case',
    path: (p, id) => `/project/${p}/verification?focus=${encodeURIComponent(id)}`,
  },
  component: {
    icon: Boxes,
    cls: 'text-cs-orange',
    label: 'Component',
    path: (p, id) => `/project/${p}/components/${encodeURIComponent(id)}`,
  },
  specification: {
    icon: FileText,
    cls: 'text-cs-yellow',
    label: 'Specification',
    path: (p, id) => `/project/${p}/specifications?focus=${encodeURIComponent(id)}`,
  },
  change: {
    icon: GitPullRequest,
    cls: 'text-cs-purple',
    label: 'Change Request',
    path: (p, id) => `/project/${p}/change-requests?focus=${encodeURIComponent(id)}`,
  },
  risk: {
    icon: AlertTriangle,
    cls: 'text-cs-red',
    label: 'Risk',
    path: (p, id) => `/project/${p}/risks?focus=${encodeURIComponent(id)}`,
  },
  decision: {
    icon: Scale,
    cls: 'text-cs-teal',
    label: 'Decision',
    path: (p, id) => `/project/${p}/decisions?focus=${encodeURIComponent(id)}`,
  },
  definition: {
    icon: Sigma,
    cls: 'text-cs-pink',
    label: 'Definition',
    path: (p, id) => `/project/${p}/definitions?focus=${encodeURIComponent(id)}`,
  },
  analysis: {
    icon: FlaskConical,
    cls: 'text-cs-purple',
    label: 'Analysis Case',
    path: (p, id) => `/project/${p}/analysis?focus=${encodeURIComponent(id)}`,
  },
  baseline: {
    icon: History,
    cls: 'text-cs-yellow',
    label: 'Baseline',
    path: (p, id) => `/project/${p}/baselines?focus=${encodeURIComponent(id)}`,
  },
  comment: {
    icon: MessageSquare,
    cls: 'text-cs-grey',
    label: 'Comment',
    // No `path`: see EntityMeta.path. Search gives us no parent entity.
  },
};

/**
 * The deep link for an entity, or `null` for kinds that have no page.
 *
 * Prefer this over reaching into `ENTITY_META[kind].path` directly: it forces
 * the caller to decide what an unlinkable kind should do, which is the whole
 * reason `path` is optional.
 */
export function entityPath(kind: EntityKind, projectId: string, id: string): string | null {
  const build = ENTITY_META[kind].path;
  return build ? build(projectId, id) : null;
}

/** Component types, in the same icon+colour language as requirement types. */
export const COMPONENT_TYPE_META: Record<string, { icon: typeof Box; cls: string; label: string }> = {
  system: { icon: Box, cls: 'text-cs-blue', label: 'System' },
  subsystem: { icon: Layers, cls: 'text-cs-purple', label: 'Subsystem' },
  assembly: { icon: Boxes, cls: 'text-cs-orange', label: 'Assembly' },
  part: { icon: Cog, cls: 'text-cs-green', label: 'Part' },
  software: { icon: Binary, cls: 'text-cs-teal', label: 'Software' },
  interface: { icon: Plug, cls: 'text-cs-pink', label: 'Interface' },
};

/**
 * Resolves icon, colour class and label for an entity kind, with optional
 * per-type override for components (e.g. a Part vs an Assembly).
 *
 * - `kind === 'component'` with a known `subtype` → {@link COMPONENT_TYPE_META}
 * - otherwise → {@link ENTITY_META}[kind]
 *
 * Never throws; an unknown subtype is silently ignored.
 */
export function entityIconMeta(
  kind: EntityKind,
  subtype?: string,
): { icon: typeof Box; cls: string; label: string } {
  if (kind === 'component' && subtype) {
    const key = subtype.trim().toLowerCase();
    // hasOwnProperty, not `in`: the YAML is hand-editable, so a component typed
    // `constructor` or `toString` would otherwise resolve up the prototype
    // chain to a function with no `.icon`, and rendering it throws.
    if (Object.prototype.hasOwnProperty.call(COMPONENT_TYPE_META, key)) {
      return COMPONENT_TYPE_META[key];
    }
  }
  return ENTITY_META[kind];
}

const PREVIEW_W = 288;
const PREVIEW_DELAY_MS = 350;

/**
 * The peek card shown after hovering a reference for a beat. Portalled to the
 * body so overflow-hidden cards can't clip it, and pointer-events-none so it
 * never traps the mouse — it's a glance, not a menu.
 */
function HoverPreview({ entity, anchor }: { entity: IndexedEntity | 'missing'; anchor: DOMRect }) {
  const left = Math.max(8, Math.min(anchor.left, window.innerWidth - PREVIEW_W - 8));
  const below = anchor.bottom + 150 < window.innerHeight;
  const style: React.CSSProperties = below
    ? { left, top: anchor.bottom + 6 }
    : { left, bottom: window.innerHeight - anchor.top + 6 };

  if (entity === 'missing') {
    return createPortal(
      <div style={{ ...style, width: PREVIEW_W }} className="fixed z-[100] pointer-events-none card p-3 shadow-xl text-xs text-muted-foreground">
        Not found in this project — the reference may be dangling.
      </div>,
      document.body,
    );
  }

  const meta = entityIconMeta(entity.kind, entity.subtype);
  const Icon = meta.icon;
  return createPortal(
    <div style={{ ...style, width: PREVIEW_W }} className="fixed z-[100] pointer-events-none card p-3 shadow-xl">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Icon size={11} className={meta.cls} />
        {meta.label}
        {entity.status && <span className="ml-auto normal-case tracking-normal badge bg-muted text-muted-foreground">{entity.status}</span>}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2 min-w-0">
        <span className="font-mono text-xs text-muted-foreground shrink-0">{entity.id}</span>
        <span className="text-sm font-medium text-card-foreground truncate">{entity.name || 'Untitled'}</span>
      </div>
      {entity.detail && <p className="mt-1 text-xs text-muted-foreground line-clamp-3">{entity.detail}</p>}
    </div>,
    document.body,
  );
}

interface EntityLinkProps {
  kind: EntityKind;
  id: string;
  /** Shown after the id when present — the human-readable title. */
  name?: string;
  /** Defaults to the project in the current route. */
  projectId?: string;
  showIcon?: boolean;
  className?: string;
  /** Secondary type for kinds with per-type iconography (component `type`). */
  subtype?: string;
}

/**
 * A reference to another entity, anywhere in the app.
 *
 * Stops click propagation on purpose: these links sit inside rows and cards
 * that have their own onClick (expand, select), and without this a reference
 * would both navigate and fire the row's handler.
 */
export function EntityLink({ kind, id, name, projectId, showIcon = true, className = '', subtype }: EntityLinkProps) {
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const pid = projectId ?? routeProjectId;
  const displayMeta = entityIconMeta(kind, subtype);
  const pathMeta = ENTITY_META[kind];
  const Icon = displayMeta.icon;

  const [preview, setPreview] = useState<IndexedEntity | 'missing' | null>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(hoverTimer.current), []);

  const startPreview = (e: React.MouseEvent) => {
    if (!pid) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    hoverTimer.current = setTimeout(() => {
      loadEntityIndex(pid).then((list) => {
        setAnchor(rect);
        setPreview(list.find((en) => en.id === id) ?? 'missing');
      });
    }, PREVIEW_DELAY_MS);
  };
  const endPreview = () => {
    clearTimeout(hoverTimer.current);
    setPreview(null);
  };

  // Outside a project route there is nowhere to link to; still render the id.
  if (!pid) return <span className={`font-mono ${className}`}>{id}</span>;

  // Kinds with no page of their own render as a labelled, unlinked row.
  if (!pathMeta.path) {
    return (
      <span
        title={`${displayMeta.label} ${id}${name ? ` — ${name}` : ''}`}
        className={`inline-flex items-center gap-1 ${className}`}
      >
        {showIcon && <Icon size={12} className={`${displayMeta.cls} shrink-0`} />}
        <span className="font-mono whitespace-nowrap">{id}</span>
        {name && <span className="truncate">{name}</span>}
      </span>
    );
  }

  return (
    <GuardedLink
      to={pathMeta.path(pid, id)}
      onClick={(e) => { e.stopPropagation(); endPreview(); }}
      onMouseEnter={startPreview}
      onMouseLeave={endPreview}
      title={`${displayMeta.label} ${id}${name ? ` — ${name}` : ''}`}
      className={`inline-flex items-center gap-1 rounded hover:underline underline-offset-2 transition-colors ${className}`}
    >
      {showIcon && <Icon size={12} className={`${displayMeta.cls} shrink-0`} />}
      <span className="font-mono whitespace-nowrap">{id}</span>
      {name && <span className="truncate">{name}</span>}
      {preview && anchor && <HoverPreview entity={preview} anchor={anchor} />}
    </GuardedLink>
  );
}

interface CopyLinkButtonProps {
  kind: EntityKind;
  id: string;
  projectId?: string;
  className?: string;
}

/**
 * Copies a shareable URL for the entity — the same deep link EntityLink
 * navigates to, absolute so it can be pasted into a commit, chat or ticket.
 */
export function CopyLinkButton({ kind, id, projectId, className = '' }: CopyLinkButtonProps) {
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const pid = projectId ?? routeProjectId;
  const [copied, setCopied] = useState<false | 'ok' | 'fail'>(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(resetTimer.current), []);

  if (!pid) return null;
  // Nothing shareable exists for a kind with no page of its own.
  const target = entityPath(kind, pid, id);
  if (!target) return null;

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const url = window.location.origin + target;
    const ok = await copyText(url);
    // Only claim success when the text actually reached the clipboard. The
    // previous form was `navigator.clipboard?.writeText(...)` followed by an
    // unconditional setCopied(true): on any non-secure origin — which includes
    // every plain-HTTP deployment — `navigator.clipboard` is undefined, the
    // optional chain swallowed it, and the button still showed a tick having
    // copied nothing.
    setCopied(ok ? 'ok' : 'fail');
    clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), ok ? 1500 : 2500);
  };

  return (
    <button
      onClick={copy}
      title={copied === 'ok' ? 'Copied!'
           : copied === 'fail' ? 'Could not copy — select the link and copy manually'
           : `Copy link to ${id}`}
      className={`p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors ${className}`}
    >
      {copied === 'ok' ? <Check size={12} className="text-cs-green" />
       : copied === 'fail' ? <AlertTriangle size={12} className="text-cs-amber" />
       : <Link2 size={12} />}
    </button>
  );
}
