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

  it('name is not truncated when under 60 characters', () => {
    const result = splitDescription('A brief clause with a short name. Another brief clause here too and long enough.');
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('A brief clause with a short name.');
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

  it('handles mixed delimiters', () => {
    const html = '<p>Clause one with enough text content.\nClause two also sufficient here; Clause three is good too.</p>';
    const result = splitDescription(html);
    expect(result).toHaveLength(3);
  });
});
