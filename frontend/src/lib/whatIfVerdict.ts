import type { EvaluationData } from '../api/client';

export type Verdict = 'pass' | 'fail' | 'unknown';

/** A requirement passes when every one of its constraints is satisfied after
 *  the change, fails when any is not, and is `unknown` when it has no
 *  constraints or none were evaluated — which is not the same as passing. */
export function requirementVerdict(evaluation: EvaluationData, ownerId: string): Verdict {
  const req = evaluation.requirements.find((r) => r.id === ownerId);
  if (!req) return 'unknown';
  if (req.constraints.length === 0) return 'unknown';

  const hasFail = req.constraints.some((c) => c.status === 'fail');
  if (hasFail) return 'fail';

  const allPass = req.constraints.every((c) => c.status === 'pass');
  if (allPass) return 'pass';

  return 'unknown';
}
