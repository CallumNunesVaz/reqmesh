import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useParams } from 'react-router-dom';
import {
  ClipboardList, CheckCircle2, Boxes, FileText, GitPullRequest, AlertTriangle,
  Box, Layers, Cog, Binary, Plug, Link2, Check,
} from 'lucide-react';
import { loadEntityIndex, type IndexedEntity } from './entityIndex';

/** Everything in a project that can be referenced from somewhere else. */
export type EntityKind = 'requirement' | 'verification' | 'component' | 'specification' | 'change' | 'risk';

interface EntityMeta {
  icon: typeof Box;
  cls: string;
  label: string;
  /** Where a reference to this entity navigates to. */
  path: (projectId: string, id: string) => string;
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
    label: 'Verification case',
    path: (p, id) => `/project/${p}/verification?focus=${encodeURIComponent(id)}`,
  },
  component: {
    icon: Boxes,
    cls: 'text-cs-orange',
    label: 'Component',
    path: (p, id) => `/project/${p}/components?focus=${encodeURIComponent(id)}`,
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
    label: 'Change request',
    path: (p, id) => `/project/${p}/change-requests?focus=${encodeURIComponent(id)}`,
  },
  risk: {
    icon: AlertTriangle,
    cls: 'text-cs-red',
    label: 'Risk',
    path: (p, id) => `/project/${p}/risks?focus=${encodeURIComponent(id)}`,
  },
};

/** Component types, in the same icon+colour language as requirement types. */
export const COMPONENT_TYPE_META: Record<string, { icon: typeof Box; cls: string; label: string }> = {
  system: { icon: Box, cls: 'text-cs-blue', label: 'System' },
  subsystem: { icon: Layers, cls: 'text-cs-purple', label: 'Subsystem' },
  assembly: { icon: Boxes, cls: 'text-cs-orange', label: 'Assembly' },
  part: { icon: Cog, cls: 'text-cs-green', label: 'Part' },
  software: { icon: Binary, cls: 'text-cs-teal', label: 'Software' },
  interface: { icon: Plug, cls: 'text-cs-pink', label: 'Interface' },
};

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

  const meta = ENTITY_META[entity.kind];
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
}

/**
 * A reference to another entity, anywhere in the app.
 *
 * Stops click propagation on purpose: these links sit inside rows and cards
 * that have their own onClick (expand, select), and without this a reference
 * would both navigate and fire the row's handler.
 */
export function EntityLink({ kind, id, name, projectId, showIcon = true, className = '' }: EntityLinkProps) {
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const pid = projectId ?? routeProjectId;
  const meta = ENTITY_META[kind];
  const Icon = meta.icon;

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

  return (
    <Link
      to={meta.path(pid, id)}
      onClick={(e) => { e.stopPropagation(); endPreview(); }}
      onMouseEnter={startPreview}
      onMouseLeave={endPreview}
      title={`${meta.label} ${id}${name ? ` — ${name}` : ''}`}
      className={`inline-flex items-center gap-1 rounded hover:underline underline-offset-2 transition-colors ${className}`}
    >
      {showIcon && <Icon size={12} className={`${meta.cls} shrink-0`} />}
      <span className="font-mono">{id}</span>
      {name && <span className="truncate">{name}</span>}
      {preview && anchor && <HoverPreview entity={preview} anchor={anchor} />}
    </Link>
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
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(resetTimer.current), []);

  if (!pid) return null;

  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    navigator.clipboard?.writeText(window.location.origin + ENTITY_META[kind].path(pid, id));
    setCopied(true);
    clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      onClick={copy}
      title={copied ? 'Copied!' : `Copy link to ${id}`}
      className={`p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors ${className}`}
    >
      {copied ? <Check size={12} className="text-cs-green" /> : <Link2 size={12} />}
    </button>
  );
}
