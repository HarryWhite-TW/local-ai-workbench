# OPT-04 UI Mockup-First Small Benchmark

## Purpose

OPT-04 evaluates whether a mockup-first workflow should be used for later UI-related nodes in the Local Document-to-Knowledge Workbench.

The benchmark asks whether a small static mockup plus a UI contract can reduce vague UI instructions, make later Codex implementation tasks easier to bound, make reviewer acceptance clearer, and preserve the rule that mockups are not the sole source of truth.

This benchmark does not authorize product UI implementation, source code changes, GitHub write, live Bridge, Dispatcher, Runner, Codex runtime task execution, dependency installation, service, watcher, MCP, RV2-04, or OPT-05.

## Method

The method is a small qualitative benchmark:

- define one limited screen concept: Review Packet / Evidence Summary
- create a static standalone HTML mockup under `docs/`
- create a UI contract that describes intended components, states, layout rules, accessibility notes, acceptance checks, non-goals, and safety boundaries
- compare the mockup-first workflow against a purely prose UI request
- validate the JSON artifacts with `json.tool`
- collect validation evidence with the Minimal Evidence Collector using process-local `PYTHONPATH=src`

This is not a product implementation. It does not modify app source, tests, scripts, configuration, package metadata, or runtime behavior.

## Mockup-First Workflow

The proposed workflow for a future separately approved UI task is:

1. Write a small UI contract before implementation.
2. Build a static mockup that makes layout, hierarchy, labels, and states reviewable.
3. Review the mockup and contract together.
4. Convert only the accepted, bounded parts into an implementation task.
5. Treat the existing app architecture, data contracts, accessibility requirements, and repository governance as higher authority than the mockup.

Expected benefit:

- UI requests become less vague because reviewers can point to concrete regions, states, and copy.
- Implementation tasks become easier to bound because the contract identifies non-goals and source-of-truth limits.
- Reviewers can check whether the implementation matches the accepted structure without treating visual polish as hidden authority expansion.

## UI Contract Role

The UI contract is the controlling review artifact for the mockup. It records:

- target screen and user goal
- components and component responsibilities
- layout rules
- states that must be represented or considered
- accessibility notes
- acceptance checks for a later implementation task
- non-goals
- safety boundaries

The UI contract is example-only for this benchmark. It must not pretend to be current app truth. A later implementation task would need fresh reads of the app source, current product state, and any active design conventions.

## What The Mockup Can Decide

The mockup can help decide:

- approximate screen hierarchy
- relative placement of evidence summary, command results, artifact links, and safety assertions
- concise reviewer-facing labels
- empty, warning, and failed-result state vocabulary
- what information density feels reviewable without becoming noisy
- whether a future task can be expressed as a bounded UI implementation slice

## What The Mockup Cannot Decide

The mockup cannot decide:

- product direction
- actual app source structure
- API schema changes
- persistence schema changes
- evidence collector behavior
- semantic task acceptance
- Bridge, Dispatcher, Runner, or Codex runtime authority
- GitHub write authority
- dependency installation
- RV2-04 or OPT-05 activation

The mockup is not the sole source of truth. It is subordinate to repository governance, current app behavior, implementation constraints, and reviewer acceptance.

## Reviewer Acceptance Checklist

A reviewer can use this checklist to decide whether the mockup-first method is worth continuing:

- The mockup is clearly labeled as a benchmark-only artifact.
- The UI contract is valid JSON and marks itself `example_only: true`.
- The contract states that it does not represent current app truth.
- The mockup uses no external assets, no CDN, and no app integration.
- The report states the no-authority boundary clearly.
- The metrics use qualitative ratings only.
- The workflow reduces vague UI instruction without expanding scope.
- The workflow preserves reviewer judgment and current-source review.
- The handoff to OPT-05 is bounded and does not implement OPT-05.

## Risks

Known risks:

- false confidence from a polished-looking mockup
- reviewers treating the mockup as current app truth
- implementation tasks copying visual details while missing data and safety constraints
- hidden scope creep from "just make the app look like the mockup"
- accessibility requirements being under-specified in a static artifact
- stale mockup details after app source changes
- qualitative metrics overstating improvement without implementation evidence

Mitigations:

- keep the UI contract next to the mockup
- label the mockup as benchmark-only
- list non-goals explicitly
- validate JSON artifacts mechanically
- require a fresh implementation task before any product UI work
- keep the final recommendation to a bounded next step only

## Go / No-Go

Go to one bounded next UI-planning step only.

The mockup-first method appears useful when the task is UI-facing, review-heavy, and likely to suffer from vague visual instructions. It should continue only if future packets keep the mockup subordinate to current app truth and preserve explicit allowed paths, non-goals, and safety boundaries.

No-Go if a mockup is used as a shortcut around source review, accessibility review, product direction, data contract review, or authority boundaries.

## OPT-05 Handoff

Recommended next node:

```text
OPT-05 - UI Mockup-First Follow-Up Planning
```

Small OPT-05 boundary, if separately approved:

- choose one tiny product UI or reviewer-facing UI candidate
- refresh current app/source context
- compare the accepted mockup-first artifacts against actual implementation constraints
- decide whether an implementation task is safe and valuable
- preserve no GitHub write, no live Bridge, no Dispatcher, no Runner, no Codex runtime task execution, no RV2-04, no service, no watcher, no MCP, and no dependency installation

OPT-05 is not authorized by this benchmark.
