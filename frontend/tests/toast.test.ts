import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
// react-router v7 folded the server entrypoints into the core package;
// `react-router-dom/server` no longer exists.
import { StaticRouter } from 'react-router';
import { pushToast, ToastItem, type Toast, type ToastAction } from '../src/components/Toast';
import { countMessage } from '../src/lib/feedback';

describe('pushToast', () => {
  it('appends in order and assigns the given id', () => {
    const result = pushToast([], 'success', 'Saved', 1);
    expect(result).toEqual([{ id: 1, kind: 'success', message: 'Saved' }]);

    const result2 = pushToast(result, 'error', 'Failed', 2);
    expect(result2).toEqual([
      { id: 1, kind: 'success', message: 'Saved' },
      { id: 2, kind: 'error', message: 'Failed' },
    ]);
  });

  it('honours limit, dropping the oldest when full', () => {
    const initial: Toast[] = [
      { id: 1, kind: 'success', message: 'A' },
      { id: 2, kind: 'success', message: 'B' },
      { id: 3, kind: 'success', message: 'C' },
    ];
    const result = pushToast(initial, 'error', 'D', 4, 3);
    expect(result).toEqual([
      { id: 2, kind: 'success', message: 'B' },
      { id: 3, kind: 'success', message: 'C' },
      { id: 4, kind: 'error', message: 'D' },
    ]);
  });

  it('a limit of 1 keeps only the newest', () => {
    const initial: Toast[] = [
      { id: 5, kind: 'success', message: 'Old' },
    ];
    const result = pushToast(initial, 'error', 'New', 6, 1);
    expect(result).toEqual([
      { id: 6, kind: 'error', message: 'New' },
    ]);
  });

  it('does not mutate the array passed in', () => {
    const initial: Toast[] = [
      { id: 1, kind: 'success', message: 'A' },
    ];
    const frozen = [...initial];
    pushToast(initial, 'error', 'B', 2, 1);
    expect(initial).toEqual(frozen);
  });

  it('round-trips an action link through the queue', () => {
    const action: ToastAction = { label: 'REQM0042', to: '/project/p/requirements/REQM0042' };
    const result = pushToast([], 'success', 'Created', 1, 3, action);
    expect(result).toEqual([
      { id: 1, kind: 'success', message: 'Created', action },
    ]);
  });
});

describe('ToastItem', () => {
  const render = (toast: Toast) => renderToStaticMarkup(
    createElement(StaticRouter, { location: '/' },
      createElement(ToastItem, { toast, onRemove: () => {} })),
  );

  it('renders an anchor with the right href when the toast has a link', () => {
    const html = render({
      id: 1,
      kind: 'success',
      message: 'Created',
      action: { label: 'REQM0042', to: '/project/p/requirements/REQM0042' },
    });
    expect(html).toContain('href="/project/p/requirements/REQM0042"');
    expect(html).toContain('>REQM0042</a>');
  });

  it('renders no anchor when the toast has no link', () => {
    const html = render({ id: 1, kind: 'success', message: 'Saved' });
    expect(html).not.toContain('<a ');
  });
});

describe('countMessage', () => {
  it('pluralises the noun when the count is not one', () => {
    expect(countMessage(3, 'requirement', 'deleted')).toBe('3 requirements deleted');
    expect(countMessage(5, 'risk', 'updated')).toBe('5 risks updated');
    expect(countMessage(2, 'verification case', 'updated')).toBe('2 verification cases updated');
  });

  it('keeps the noun singular when the count is one', () => {
    expect(countMessage(1, 'requirement', 'deleted')).toBe('1 requirement deleted');
    expect(countMessage(1, 'risk', 'updated')).toBe('1 risk updated');
  });
});
