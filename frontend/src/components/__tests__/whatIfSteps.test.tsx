/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import { WhatIfSteps } from '../WhatIfPanel';
import type { ImpactStep, EvaluationData } from '../../api/client';

const steps: ImpactStep[] = [
  { kind: 'param', ref: 'R-001.mass', owner: 'R-001', name: 'mass', expr: '10', unit: 'kg', inputs: [], before: 10, after: 11 },
  { kind: 'constraint', owner: 'R-002', expr: 'mass <= 11', before: { status: 'unknown' }, after: { status: 'unknown' } },
  { kind: 'param', ref: 'R-003.thrust', owner: 'R-003', name: 'thrust', expr: '20', unit: 'N', inputs: [], before: 20, after: 21 },
  { kind: 'constraint', owner: 'R-004', expr: 'thrust >= 21', before: { status: 'unknown' }, after: { status: 'unknown' } },
];

/** Minimal `EvaluationData` exercising the real `requirementVerdict` rules
 *  (see `src/lib/whatIfVerdict.ts`): every constraint passing is `pass`, any
 *  failing is `fail`, and no constraints at all is `unknown` — which is not the
 *  same as passing. `R-004` is deliberately absent so the "requirement not
 *  found" branch is reached with an evaluation present, rather than only when
 *  the prop is omitted entirely. */
const evaluation = {
  requirements: [
    { id: 'R-001', name: 'One', parameters: [], verdict: 'pass',
      constraints: [{ expr: 'a <= b', status: 'pass' }] },
    { id: 'R-002', name: 'Two', parameters: [], verdict: 'fail',
      constraints: [{ expr: 'c >= d', status: 'fail' }] },
    { id: 'R-003', name: 'Three', parameters: [], verdict: 'unknown', constraints: [] },
  ],
  summary: {},
  measured_summary: { pass: 0, fail: 0, unmeasured: 0 },
  parameter_count: 0,
  measurement_count: 0,
  data_issues: [],
} satisfies EvaluationData;

function renderSteps(
  stepIndex: number,
  opts: { steps?: ImpactStep[]; rootOwners?: Set<string>; evaluation?: EvaluationData } = {},
) {
  const onSelect = vi.fn();
  const onKeyDown = vi.fn();
  const utils = render(
    <WhatIfSteps
      steps={opts.steps ?? steps}
      stepIndex={stepIndex}
      evaluation={opts.evaluation}
      rootOwners={opts.rootOwners ?? new Set()}
      onSelect={onSelect}
      onKeyDown={onKeyDown}
    />,
  );
  return { ...utils, onSelect, onKeyDown };
}

/** The verdict word appears twice inside one step — once at the left of the
 *  header and once in the `ml-auto` slot — so a global text query is ambiguous.
 *  Scope to the step and de-duplicate. */
function verdictWords(container: HTMLElement, index: number): string[] {
  const step = container.querySelector(`[data-whatif-step="${index}"]`)!;
  const words = Array.from(step.querySelectorAll('span'))
    .map((el) => el.textContent)
    .filter((t): t is string => t === 'pass' || t === 'fail');
  return [...new Set(words)];
}

function stepIndexes(container: HTMLElement): (string | null)[] {
  return Array.from(container.querySelectorAll('[data-whatif-step]')).map((el) =>
    el.getAttribute('data-whatif-step'),
  );
}

describe('WhatIfSteps', () => {
  it('renders exactly one step at stepIndex 0', () => {
    const { container } = renderSteps(0);
    expect(stepIndexes(container)).toEqual(['0']);
  });

  it('renders steps in source order up to stepIndex', () => {
    const { container } = renderSteps(2);
    expect(stepIndexes(container)).toEqual(['0', '1', '2']);
  });

  it('keeps earlier steps mounted as stepIndex advances', () => {
    const onSelect = vi.fn();
    const onKeyDown = vi.fn();
    const { container, rerender } = render(
      <WhatIfSteps steps={steps} stepIndex={0} rootOwners={new Set()} onSelect={onSelect} onKeyDown={onKeyDown} />,
    );
    const first = container.querySelector('[data-whatif-step="0"]');

    rerender(
      <WhatIfSteps steps={steps} stepIndex={1} rootOwners={new Set()} onSelect={onSelect} onKeyDown={onKeyDown} />,
    );

    expect(stepIndexes(container)).toEqual(['0', '1']);
    expect(container.querySelector('[data-whatif-step="0"]')).toBe(first);
  });

  it('renders every step when stepIndex exceeds the last index', () => {
    const { container } = renderSteps(steps.length + 5);
    expect(stepIndexes(container)).toEqual(['0', '1', '2', '3']);
  });

  it('renders nothing for an empty step list', () => {
    const { container } = renderSteps(0, { steps: [] });
    expect(stepIndexes(container)).toEqual([]);
  });

  it('calls onSelect with the clicked step index', () => {
    const { container, onSelect } = renderSteps(2);
    fireEvent.click(container.querySelector('[data-whatif-step="1"]')!);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('renders no pass/fail word when evaluation is absent', () => {
    renderSteps(3);
    expect(screen.queryByText('pass')).toBeNull();
    expect(screen.queryByText('fail')).toBeNull();
  });

  it('renders the real verdict per step when an evaluation is supplied', () => {
    const { container } = renderSteps(3, { evaluation });
    expect(verdictWords(container, 0)).toEqual(['pass']);   // R-001, all constraints pass
    expect(verdictWords(container, 1)).toEqual(['fail']);   // R-002, one fails
  });

  it('falls back to no verdict for an owner the evaluation does not cover', () => {
    const { container } = renderSteps(3, { evaluation });
    expect(verdictWords(container, 2)).toEqual([]);         // R-003, no constraints
    expect(verdictWords(container, 3)).toEqual([]);         // R-004, absent entirely
  });

  it('colours root owners blue and leaves other owners muted', () => {
    const { container } = renderSteps(3, { rootOwners: new Set(['R-001', 'R-003']) });

    const rootOwner = container.querySelector('[data-whatif-step="0"] .text-cs-blue');
    expect(rootOwner).not.toBeNull();
    expect(rootOwner!.textContent).toBe('R-001');

    const otherOwner = container.querySelector('[data-whatif-step="1"] .text-cs-blue');
    expect(otherOwner).toBeNull();
  });
});
