import { useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

/** Key that, when pressed alone (no modifiers), is ignored during text editing. */
const TEXT_INPUT_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

interface ShortcutHandlers {
  onEditToggle?: () => void;
  onGraphToggle?: () => void;
  onHelperToggle?: () => void;
  onHelpToggle?: () => void;
  onDocsOpen?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onListDown?: () => void;
  onListUp?: () => void;
  onListOpen?: () => void;
  onListNew?: () => void;
  onListSearch?: () => void;
  onListEscape?: () => void;
  onDetailEscape?: () => void;
  onDetailSave?: () => void;
  onDetailDelete?: () => void;
}

/**
 * Global keyboard shortcuts for reqmesh.
 *
 * Rules:
 * - When an INPUT/TEXTAREA/SELECT is focused, only modifier-based shortcuts
 *   (Ctrl+key) fire — navigation keys (j/k, Enter, etc.) pass through unchanged.
 * - Context is detected by URL path: list pages vs detail pages.
 */
export function useKeyboardShortcuts(projectId: string | undefined, handlers: ShortcutHandlers) {
  const location = useLocation();
  const navigate = useNavigate();
  const isDetail = /\/project\/[^/]+\/(requirements|components)\/[^/]+/.test(location.pathname);
  const isList = /\/project\/[^/]+\/(requirements|components|specifications|verification|traces|change-requests|risks)$/.test(location.pathname);
  const isInProject = !!projectId;

  const h = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    const tag = target.tagName;
    const inTextInput = TEXT_INPUT_TAGS.has(tag) || (target as any)?.isContentEditable;

    const ctrl = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;
    const key = e.key.toLowerCase();

    // ── Global toggles (work everywhere, even in text inputs) ──────────────
    if (isInProject) {
      if (ctrl && !shift && key === 'e') { e.preventDefault(); handlers.onEditToggle?.(); return; }
      if (ctrl && !shift && key === 'g') { e.preventDefault(); handlers.onGraphToggle?.(); return; }
      if (ctrl && !shift && key === 'h') { e.preventDefault(); handlers.onHelperToggle?.(); return; }
      if ((ctrl && !shift && key === '/') || key === 'f1') {
        e.preventDefault();
        if (key === 'f1') handlers.onDocsOpen?.();
        else handlers.onHelpToggle?.();
        return;
      }
      // '?' arrives with shiftKey set on most layouts — match on the key alone.
      if (!ctrl && key === '?' && !inTextInput) { e.preventDefault(); handlers.onHelpToggle?.(); return; }
    }

    // ── Undo / Redo (only when NOT in a text input) ─────────────────────
    if (!inTextInput) {
      if (ctrl && !shift && key === 'z') { e.preventDefault(); handlers.onUndo?.(); return; }
      if ((ctrl && !shift && key === 'y') || (ctrl && shift && key === 'z')) { e.preventDefault(); handlers.onRedo?.(); return; }
    }

    // ── Escape closes modals / goes back (works everywhere) ────────────────
    if (key === 'escape') {
      if (isDetail) { handlers.onDetailEscape?.(); return; }
      if (isList) { handlers.onListEscape?.(); return; }
      return;
    }

    // ── Detail page actions (Ctrl+S in text inputs) ────────────────────────
    if (isDetail && ctrl && !shift && key === 's') {
      e.preventDefault(); handlers.onDetailSave?.(); return;
    }
    if (isDetail && !ctrl && !shift && key === 'delete' && !inTextInput) {
      e.preventDefault(); handlers.onDetailDelete?.(); return;
    }

    // ── List navigation (only when NOT in a text input) ────────────────────
    if (isList && !inTextInput) {
      if ((key === 'j' || key === 'arrowdown') && !ctrl && !shift) { e.preventDefault(); handlers.onListDown?.(); return; }
      if ((key === 'k' || key === 'arrowup') && !ctrl && !shift) { e.preventDefault(); handlers.onListUp?.(); return; }
      if (key === 'enter' && !ctrl && !shift) { e.preventDefault(); handlers.onListOpen?.(); return; }
      if (key === 'n' && !ctrl && !shift) { e.preventDefault(); handlers.onListNew?.(); return; }
      if (key === '/' && !ctrl && !shift) { e.preventDefault(); handlers.onListSearch?.(); return; }
    }

    // ── Quick nav: Alt+key shortcuts ──────────────────────────────────────
    if (isInProject && e.altKey && !ctrl && !shift && !inTextInput) {
      const routes: Record<string, string> = {
        r: `/project/${projectId}/requirements`,
        c: `/project/${projectId}/components`,
        s: `/project/${projectId}/specifications`,
        v: `/project/${projectId}/verification`,
        t: `/project/${projectId}/traces`,
        h: `/project/${projectId}/change-requests`,
        k: `/project/${projectId}/risks`,
        m: `/project/${projectId}/metrics`,
        p: `/project/${projectId}/publish`,
      };
      const path = routes[key];
      if (path) { e.preventDefault(); navigate(path); return; }
    }
  }, [handlers, isInProject, isDetail, isList, navigate, projectId]);

  useEffect(() => {
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [h]);
}

export type { ShortcutHandlers };
