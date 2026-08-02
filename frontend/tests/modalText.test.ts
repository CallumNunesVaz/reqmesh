import { describe, it, expect } from 'vitest';
import { modalRegex, modalStrength } from '../src/lib/qualityRules';

describe('modalRegex', () => {
  it('splits text so "shall not" is one token', () => {
    const re = modalRegex();
    const matches: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec('The system shall not log')) !== null) {
      matches.push(m[0]);
    }
    expect(matches).toEqual(['shall not']);
  });

  it('finds two distinct keywords in one string', () => {
    const re = modalRegex();
    const matches: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec('The server shall respond and clients may retry')) !== null) {
      matches.push(m[0]);
    }
    expect(matches).toContain('shall');
    expect(matches).toContain('may');
  });

  it('is case-insensitive', () => {
    const re = modalRegex();
    const matches: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec('System SHALL NOT proceed')) !== null) {
      matches.push(m[0]);
    }
    expect(matches).toEqual(['SHALL NOT']);
  });

  it('tolerates runs of whitespace between the two words of a multi-word modal', () => {
    const re = modalRegex();
    const matches: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec('The system shall   not proceed')) !== null) {
      matches.push(m[0]);
    }
    expect(matches).toEqual(['shall   not']);
  });
});

describe('modalStrength', () => {
  it('SHALL NOT is binding', () => {
    expect(modalStrength('SHALL NOT')).toBe('binding');
  });

  it('shall is binding', () => {
    expect(modalStrength('shall')).toBe('binding');
  });

  it('must is binding', () => {
    expect(modalStrength('must')).toBe('binding');
  });

  it('will is binding', () => {
    expect(modalStrength('will')).toBe('binding');
  });

  it('may is advisory', () => {
    expect(modalStrength('may')).toBe('advisory');
  });

  it('should is advisory', () => {
    expect(modalStrength('should')).toBe('advisory');
  });

  it('should not is advisory', () => {
    expect(modalStrength('should not')).toBe('advisory');
  });

  it('and is null', () => {
    expect(modalStrength('and')).toBeNull();
  });

  it('handles normalised whitespace in multi-word modals', () => {
    // modalStrength normalises whitespace before comparing
    expect(modalStrength('shall  not')).toBe('binding');
  });
});
