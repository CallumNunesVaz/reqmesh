import { describe, it, expect } from 'vitest';
import { pushToast, type Toast } from '../src/components/Toast';

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
});
