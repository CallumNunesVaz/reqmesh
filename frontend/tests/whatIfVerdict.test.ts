import { describe, expect, it } from 'vitest';
import { requirementVerdict, type Verdict } from '../src/lib/whatIfVerdict';
import type { EvaluationData, EvaluatedRequirement, EvaluatedConstraint } from '../src/api/client';

function makeConstraint(status: string, expr = 'x <= 10'): EvaluatedConstraint {
  return { expr, status: status as EvaluatedConstraint['status'] };
}

function makeReq(
  id: string,
  constraints: EvaluatedConstraint[],
  verdict: string = 'pass',
): EvaluatedRequirement {
  return {
    id,
    name: id,
    parameters: [],
    constraints,
    verdict: verdict as EvaluatedRequirement['verdict'],
  };
}

function makeEval(reqs: EvaluatedRequirement[]): EvaluationData {
  return {
    requirements: reqs,
    summary: {},
    measured_summary: { pass: 0, fail: 0, unmeasured: 0 },
    parameter_count: 0,
    measurement_count: 0,
    data_issues: [],
  };
}

describe('requirementVerdict', () => {
  it('returns pass when all constraints are satisfied', () => {
    const ev = makeEval([makeReq('R1', [
      makeConstraint('pass'),
      makeConstraint('pass'),
    ])]);
    expect(requirementVerdict(ev, 'R1')).toBe('pass');
  });

  it('returns fail when any one constraint is unsatisfied', () => {
    const ev = makeEval([makeReq('R1', [
      makeConstraint('pass'),
      makeConstraint('fail'),
    ])]);
    expect(requirementVerdict(ev, 'R1')).toBe('fail');
  });

  it('returns fail even when other constraints pass', () => {
    const ev = makeEval([makeReq('R1', [
      makeConstraint('fail'),
      makeConstraint('pass'),
      makeConstraint('pass'),
    ])]);
    expect(requirementVerdict(ev, 'R1')).toBe('fail');
  });

  it('returns unknown when the owner has no constraints', () => {
    const ev = makeEval([makeReq('R1', [])]);
    const result: Verdict = requirementVerdict(ev, 'R1');
    expect(result).toBe('unknown');
    // Explicitly assert NOT pass
    expect(result).not.toBe('pass');
  });

  it('returns unknown when the owner is absent from the evaluation', () => {
    const ev = makeEval([makeReq('R1', [makeConstraint('pass')])]);
    const result: Verdict = requirementVerdict(ev, 'R2');
    expect(result).toBe('unknown');
    expect(result).not.toBe('pass');
  });

  it('returns unknown when constraints have non-pass/non-fail statuses', () => {
    const ev = makeEval([makeReq('R1', [
      makeConstraint('unknown'),
      makeConstraint('not_applicable'),
    ])]);
    const result: Verdict = requirementVerdict(ev, 'R1');
    expect(result).toBe('unknown');
    expect(result).not.toBe('pass');
  });

  it('returns pass when a single constraint passes', () => {
    const ev = makeEval([makeReq('R1', [makeConstraint('pass')])]);
    expect(requirementVerdict(ev, 'R1')).toBe('pass');
  });
});
