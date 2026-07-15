# Workflow Acceptance Integrity Protocol

## Purpose And Boundary

This protocol governs Workflow acceptance, closeout, final-status adjudication,
and correction of acceptance-integrity incidents. It supplements existing
repository, Bridge, Roadmap, task-local, and authority rules. It does not grant
execution authority, replace target-native evidence, or guarantee perfect
correctness.

## 1. Primary Goal Coverage Gate

Acceptance must explicitly map every primary goal to current evidence. Local
component checks, implementation presence, or a successful supporting path do
not substitute for the stated target experience. Any uncovered primary goal is
`PARTIAL`, `UNVERIFIED`, or `DEFERRED`, not silently accepted.

## 2. Top-Down Backward Acceptance Review

Review backward from the claimed user-visible outcome:

```text
claimed outcome
-> durable result and readback
-> target-flow behavior
-> integration and call-site behavior
-> component contracts
-> implementation and tests
```

Bottom-up implementation evidence is necessary but cannot alone establish the
top-level outcome.

## 3. Capability Matrix

Each claimed capability receives exactly one current classification:

- `VERIFIED`: directly supported by applicable current evidence.
- `PARTIAL`: meaningful behavior is proven, but the full claim is not.
- `UNVERIFIED`: evidence is absent, incomplete, stale, or not applicable to the claim.
- `DEFERRED`: intentionally outside the current accepted scope.
- `NOT_APPLICABLE`: the capability is irrelevant to the stated goal.
- `REJECTED`: evidence contradicts the claim or exposes an unacceptable defect.

The matrix must preserve qualified and negative results; it must not collapse
them into a global success label.

## 4. Contradiction Detection

Before acceptance, compare goals, governance, source, tests, call sites,
runtime evidence, review state, and durable status. Any contradiction pauses
only the affected verdict or capability. Unaffected accepted evidence remains
valid unless the contradiction directly undermines it.

## 5. Async Review Completion Gate

`no review observed != review completed`.

An asynchronous review gate is complete only when the expected review has
finished and its result is available. Merge, timeout, silence, an empty current
view, or absence of an observed comment does not prove review completion or a
no-finding result.

## 6. Cross-Call-Site Compatibility Gate

Changes to a shared parser, token, schema, protocol, state object, or delegated
command require review of every direct constructor, caller, parser, and
consumer in the affected flow. Acceptance requires at least one regression
covering the real compatibility boundary, not only isolated producer and
consumer unit tests.

## 7. Trusted Oracle Independence Rule

Code or data modified by a candidate must not become the sole trusted oracle
that accepts that same candidate. Acceptance must use a reviewer-controlled or
committed trusted baseline independent of candidate changes, or fail closed
when the trusted identity cannot be established. This rule does not claim an
OS sandbox or universal filesystem isolation.

## 8. Manual Relay Visibility

When manual relay fallback is used, evidence must expose:

```text
execution_mode=manual_relay_fallback
user_relay_required=true
fallback_reason=<exact reason>
target_experience_validated=false
```

Manual relay may preserve progress, but it cannot validate the unavailable
target experience.

## 9. Durable Truth Closure Gate

Final acceptance requires accepted conclusions to be synchronized across all
applicable durable truth surfaces after implementation, review, merge, and
post-merge verification. Stale trackers or documents must remain explicitly
marked stale until a separately authorized synchronization occurs. A local
candidate cannot claim remote or canonical closure.

## 10. Acceptance Integrity Incident Protocol

Use this bounded sequence when a potential core mismatch appears:

```text
potential core mismatch
-> pause affected downstream work only
-> preserve unaffected accepted evidence
-> suspend contested verdict/capability only
-> fresh-read governance/source/tests/call sites/remote evidence
-> classify failure
-> collect all known blockers once
-> publish revised capability matrix
-> propose one minimal complete correction
-> bounded implementation
-> target-flow validation where applicable
-> durable truth synchronization
-> final DONE re-adjudication
```

General lesson: a locally passing component can still leave the primary goal
unverified when a shared caller is stale, a reviewer has not completed, or the
candidate controls its own acceptance oracle. Corrections should repair the
complete bounded mismatch while preserving unrelated accepted evidence and
authority limits.
