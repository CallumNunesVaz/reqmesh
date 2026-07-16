import { Link, useParams } from 'react-router-dom';
import {
  ClipboardList, CheckCircle2, Boxes, FileText,
  Box, Layers, Cog, Binary, Plug,
} from 'lucide-react';

/** Everything in a project that can be referenced from somewhere else. */
export type EntityKind = 'requirement' | 'verification' | 'component' | 'specification';

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

  // Outside a project route there is nowhere to link to; still render the id.
  if (!pid) return <span className={`font-mono ${className}`}>{id}</span>;

  return (
    <Link
      to={meta.path(pid, id)}
      onClick={(e) => e.stopPropagation()}
      title={`${meta.label} ${id}${name ? ` — ${name}` : ''}`}
      className={`inline-flex items-center gap-1 rounded hover:underline underline-offset-2 transition-colors ${className}`}
    >
      {showIcon && <Icon size={12} className={`${meta.cls} shrink-0`} />}
      <span className="font-mono">{id}</span>
      {name && <span className="truncate">{name}</span>}
    </Link>
  );
}
