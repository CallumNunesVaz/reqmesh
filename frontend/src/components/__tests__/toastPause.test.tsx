/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act, cleanup } from '@testing-library/react';
import { ToastItem, type Toast } from '../Toast';

function successToast(): Toast {
  return { id: 1, kind: 'success', message: 'Saved' };
}

function errorToast(): Toast {
  return { id: 2, kind: 'error', message: 'Failed' };
}

describe('ToastItem auto-dismiss timer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it('removes a success toast after 4000 ms', () => {
    const onRemove = vi.fn();
    render(<ToastItem toast={successToast()} onRemove={onRemove} />);
    act(() => vi.advanceTimersByTime(3999));
    expect(onRemove).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('removes an error toast after 8000 ms', () => {
    const onRemove = vi.fn();
    render(<ToastItem toast={errorToast()} onRemove={onRemove} />);
    act(() => vi.advanceTimersByTime(7999));
    expect(onRemove).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onRemove).toHaveBeenCalledWith(2);
  });

  it('pauses on mouse enter and resumes on mouse leave', () => {
    const onRemove = vi.fn();
    const { container } = render(<ToastItem toast={successToast()} onRemove={onRemove} />);
    const root = container.firstElementChild as HTMLElement;

    fireEvent.mouseEnter(root);
    expect(root.getAttribute('data-toast-paused')).toBe('true');
    act(() => vi.advanceTimersByTime(10000));
    expect(onRemove).not.toHaveBeenCalled();

    fireEvent.mouseLeave(root);
    expect(root.getAttribute('data-toast-paused')).toBeNull();
    act(() => vi.advanceTimersByTime(4000));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('pauses on focus and resumes on blur', () => {
    const onRemove = vi.fn();
    const { container } = render(<ToastItem toast={successToast()} onRemove={onRemove} />);
    const root = container.firstElementChild as HTMLElement;

    fireEvent.focus(root);
    expect(root.getAttribute('data-toast-paused')).toBe('true');
    act(() => vi.advanceTimersByTime(10000));
    expect(onRemove).not.toHaveBeenCalled();

    fireEvent.blur(root);
    expect(root.getAttribute('data-toast-paused')).toBeNull();
    act(() => vi.advanceTimersByTime(4000));
    expect(onRemove).toHaveBeenCalledWith(1);
  });
});
