/** Move `name` one step in `names`. Returns null when the move is impossible
 * (name absent, already first for 'up', already last for 'down'), so the
 * caller can skip a pointless request. */
export function moveInSequence(
  names: string[],
  name: string,
  direction: 'up' | 'down',
): string[] | null {
  const idx = names.indexOf(name);
  if (idx === -1) return null;
  if (direction === 'up' && idx === 0) return null;
  if (direction === 'down' && idx === names.length - 1) return null;

  const result = [...names];
  const target = direction === 'up' ? idx - 1 : idx + 1;
  [result[idx], result[target]] = [result[target], result[idx]];
  return result;
}

/** Move the item at `from` to index `to`. Always returns a permutation of the
 * input — same length, same members. */
export function moveToIndex(names: string[], from: number, to: number): string[] {
  const result = [...names];
  const [item] = result.splice(from, 1);
  result.splice(to, 0, item);
  return result;
}
