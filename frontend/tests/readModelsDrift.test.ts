/**
 * Compile-time drift guard for the read contract.
 *
 * The hand-written entity interfaces in `client.ts` predate the generated read
 * models and could silently drift from the API. Each assignment below fails to
 * compile if the hand-written type is missing a field the generated contract
 * requires, or has an incompatible type for one.
 */
import { describe, it, expect } from 'vitest';
import type * as G from '../src/api/generated/readModels';
import type * as H from '../src/api/client';

const _requirement: G.Requirement = {} as H.Requirement;
const _component: G.Component = {} as H.Component;
const _specification: G.Specification = {} as H.Specification;
const _verification: G.VerificationCase = {} as H.VerificationCase;
const _changeRequest: G.ChangeRequest = {} as H.ChangeRequest;
const _risk: G.Risk = {} as H.Risk;
const _comment: G.Comment = {} as H.Comment;
const _decision: G.DecisionRecord = {} as H.DecisionRecord;
const _definition: G.Definition = {} as H.Definition;
const _analysis: G.AnalysisCase = {} as H.AnalysisCase;
const _parameter: G.Parameter = {} as H.Parameter;
const _constraint: G.Constraint = {} as H.Constraint;
const _reference: G.Reference = {} as H.Reference;
const _traceLink: G.TraceLink = {} as H.TraceLink;

describe('read-model drift guard', () => {
  it('compiles the hand-written read types against the generated contract', () => {
    expect([
      _requirement, _component, _specification, _verification, _changeRequest,
      _risk, _comment, _decision, _definition, _analysis, _parameter,
      _constraint, _reference, _traceLink,
    ]).toBeTruthy();
  });
});
