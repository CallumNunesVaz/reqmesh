import { describe, it, expect } from 'vitest';
import { scoreRequirement, stripHtml } from '../src/lib/quality';

/**
 * The client scorer mirrors `backend/app/services/quality.py::score_requirement`.
 * These assert the behaviour the requirement-detail page relies on: the score
 * is a pure function of the draft text, so it updates as the author types,
 * with no save round-trip.
 */

describe('scoreRequirement', () => {
  it('scores clean prose 100', () => {
    const { score, findings } = scoreRequirement(
      'The system must authenticate users within 500 ms using OAuth 2.0',
    );
    expect(score).toBe(100);
    expect(findings).toHaveLength(0);
  });

  it('updates as the text changes, with no save', () => {
    // The saved description.
    const clean = 'The system must authenticate users within 500 ms';
    expect(scoreRequirement(clean).score).toBe(100);

    // One keystroke's worth of a weak word — the score drops immediately.
    const typed = `${clean} and be fast`;
    expect(scoreRequirement(typed).score).toBeLessThan(100);
    expect(scoreRequirement(typed).findings.map((f) => f.rule)).toContain('weak_words');
  });

  it('scores the HTML the editor holds, not the tags', () => {
    const { score } = scoreRequirement(
      '<p>The system <strong>must</strong> authenticate users within <em>500 ms</em>.</p>',
    );
    expect(score).toBe(100);
  });

  it('flags placeholders and word count', () => {
    const tooShort = scoreRequirement('TODO');
    expect(tooShort.findings.map((f) => f.rule)).toContain('placeholder');
    expect(tooShort.findings.map((f) => f.rule)).toContain('word_count');
  });

  it('flags the missing obligation verb', () => {
    const { findings } = scoreRequirement('This describes the authentication module');
    expect(findings.map((f) => f.rule)).toContain('no_obligation');
  });
});

describe('stripHtml', () => {
  it('separates block tags with a single space and unescapes entities', () => {
    expect(stripHtml('<p>Hello <strong>world</strong></p>')).toBe('Hello world ');
    expect(stripHtml('<div>Hello</div><div>world</div>')).toBe('Hello world ');
    expect(stripHtml('<p>Hello &amp; welcome</p>')).toBe('Hello & welcome ');
  });
});
