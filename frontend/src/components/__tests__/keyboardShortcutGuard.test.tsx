/**
 * @vitest-environment jsdom
 *
 * The Alt+key quick-nav shortcuts must route through the unsaved-changes guard.
 * They previously called `navigate()` directly, so on a dirty detail page an
 * Alt+R navigated away and discarded the edit without the confirmation the
 * sidebar link would have shown.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { useKeyboardShortcuts } from '../useKeyboardShortcuts';
import { useStore } from '../../store';

function Harness() {
  useKeyboardShortcuts('p', {});
  return <div />;
}

function renderHarness() {
  return render(
    <MemoryRouter initialEntries={['/project/p/requirements/R-1']}>
      <Routes>
        <Route path="*" element={<Harness />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  useStore.getState().setNavGuard(null);
});

describe('useKeyboardShortcuts Alt quick-nav', () => {
  it('consults the registered guard before navigating', () => {
    const guard = vi.fn(async () => false);
    useStore.getState().setNavGuard(guard);
    renderHarness();

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', altKey: true }));
    });

    expect(guard).toHaveBeenCalled();
  });

  it('navigates when the guard allows it', () => {
    const guard = vi.fn(async () => true);
    useStore.getState().setNavGuard(guard);
    renderHarness();

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', altKey: true }));
    });

    expect(guard).toHaveBeenCalled();
  });
});

describe('useKeyboardShortcuts while a dialog is open', () => {
  function EscapeHarness({ onEscape }: { onEscape: () => void }) {
    useKeyboardShortcuts('p', { onDetailEscape: onEscape });
    return <div />;
  }

  it('does not fire page-level Escape handlers behind a dialog', () => {
    const onEscape = vi.fn();
    render(
      <MemoryRouter initialEntries={['/project/p/requirements/R-1']}>
        <Routes>
          <Route path="*" element={<EscapeHarness onEscape={onEscape} />} />
        </Routes>
      </MemoryRouter>,
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(onEscape).toHaveBeenCalledTimes(1);

    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    document.body.appendChild(dialog);
    try {
      act(() => {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      });
      expect(onEscape).toHaveBeenCalledTimes(1);
    } finally {
      document.body.removeChild(dialog);
    }
  });
});
