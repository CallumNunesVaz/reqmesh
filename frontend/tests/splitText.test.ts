import { describe, it, expect } from 'vitest';
import { splitDescription } from '../src/lib/splitText';

describe('splitDescription', () => {
  it('returns two candidates for two sentences', () => {
    const result = splitDescription('<p>First sentence has enough text here. Second sentence also has plenty of text.</p>');
    expect(result).toHaveLength(2);
    expect(result[0].text).toContain('First sentence');
    expect(result[1].text).toContain('Second sentence');
  });

  it('returns empty array for a single sentence', () => {
    const result = splitDescription('<p>Only one sentence here that is long enough.</p>');
    expect(result).toEqual([]);
  });

  it('splits on semicolons', () => {
    const result = splitDescription('First clause has plenty of text here; Second clause also has enough text to pass the minimum length check.');
    expect(result).toHaveLength(2);
    expect(result[0].text).toContain('First clause');
    expect(result[1].text).toContain('Second clause');
  });

  it('splits on newlines', () => {
    const html = '<p>First line has plenty of characters\nSecond line also has sufficient text to survive</p>';
    const result = splitDescription(html);
    expect(result).toHaveLength(2);
  });

  it('drops fragments shorter than 15 characters and returns empty when fewer than 2 survive', () => {
    const result = splitDescription('Short. Another short. A sufficiently long sentence that passes the minimum character length threshold.');
    expect(result).toEqual([]);
  });

  it('strips HTML tags and collapses whitespace', () => {
    const result = splitDescription('<p>  Hello   <b>world</b>  </p> text here is long enough for a valid clause.  Another long enough clause goes right here and passes.</p>');
    expect(result).toHaveLength(2);
    expect(result[0].text).toBe('Hello world text here is long enough for a valid clause.');
    expect(result[1].text).toBe('Another long enough clause goes right here and passes.');
  });

  it('name truncates on a word boundary at or before 60 characters', () => {
    const longClause = 'A'.repeat(10) + ' ' + 'B'.repeat(55) + ' word. Another clause that is also long enough to be a candidate here.';
    const result = splitDescription(longClause);
    expect(result).toHaveLength(2);
    expect(result[0].name.length).toBeLessThanOrEqual(60);
    expect(result[0].name).not.toContain('Bb');
    expect(result[0].name.endsWith(' ')).toBe(false);
  });

  it('name is not truncated when under 60 characters, and drops the sentence full stop', () => {
    const result = splitDescription('A brief clause with a short name. Another brief clause here too and long enough.');
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('A brief clause with a short name');
    expect(result[0].name.length).toBeLessThanOrEqual(60);
  });

  it('does not mutate the input string', () => {
    const input = '<p>First sentence for testing no mutation. Second sentence also for no mutation test.</p>';
    const original = input.slice();
    splitDescription(input);
    expect(input).toBe(original);
  });

  it('returns empty array for empty string', () => {
    expect(splitDescription('')).toEqual([]);
  });

  it('returns empty array for whitespace-only string', () => {
    expect(splitDescription('   \n  ')).toEqual([]);
  });

  it('returns empty array when only one candidate survives length filter', () => {
    const result = splitDescription('Abc. A sufficiently long sentence that passes the minimum character length threshold and is the only survivor.');
    expect(result).toEqual([]);
  });

  it('drops the subject-and-modal opening siblings share', () => {
    const [a, b] = splitDescription(
      'The cabin heating system shall maintain a cabin temperature of 21 degrees Celsius. '
      + 'The cabin heating system shall be leak-tested at each annual inspection.',
    );
    expect(a.name).toBe('Maintain a cabin temperature of 21 degrees Celsius');
    expect(b.name).toBe('Be leak-tested at each annual inspection');
    // The point of dropping it: two siblings that used to collide no longer do.
    expect(a.name).not.toBe(b.name);
  });

  it('keeps the opening when dropping it would leave almost nothing', () => {
    const [a] = splitDescription(
      'The extremely long and detailed subsystem name here shall exist. '
      + 'Another clause that is long enough to be a candidate.',
    );
    expect(a.name).toContain('extremely long');
  });

  it('cuts a long name at a clause boundary rather than mid-phrase', () => {
    const [a] = splitDescription(
      'The system shall provide continuous heating, monitoring the cabin temperature every second of flight. '
      + 'Another clause that is long enough to be a candidate.',
    );
    expect(a.name).toBe('Provide continuous heating');
    expect(a.name.length).toBeLessThanOrEqual(60);
  });

  it('falls back to a word boundary when there is no clause boundary', () => {
    const [a] = splitDescription(
      'The system shall provide continuous cabin heating throughout every phase of normal flight operations. '
      + 'Another clause that is long enough to be a candidate.',
    );
    expect(a.name.length).toBeLessThanOrEqual(60);
    expect(a.name.endsWith(' ')).toBe(false);
    // A word boundary, not a chopped word.
    expect(a.text).toContain(a.name.charAt(0).toLowerCase() + a.name.slice(1));
  });

  it('names never end in dangling punctuation', () => {
    const result = splitDescription(
      'The system shall do the first thing, which is quite important; '
      + 'The system shall do the second thing, which also matters a lot.',
    );
    for (const c of result) expect(c.name).not.toMatch(/[.,;:\s]$/);
  });

  it('handles mixed delimiters', () => {
    const html = '<p>Clause one with enough text content.\nClause two also sufficient here; Clause three is good too.</p>';
    const result = splitDescription(html);
    expect(result).toHaveLength(3);
  });
});
