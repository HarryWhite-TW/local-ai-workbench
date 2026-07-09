# Engineering Records Index

## Purpose

This file is a navigation index for engineering records. It is not current truth by itself, does not replace fresh Git or GitHub verification, and does not authorize work.

## First Read Order

Recommended future session read order:

1. `AGENTS.md`
2. `src/local_runner_bridge/AGENTS.md` when bridge, workflow, Task Packet, Bridge Operator, or Codex work is involved
3. `PLANS.md`
4. `docs/ENGINEERING_RECORDS_INDEX.md`
5. Roadmap, OPT, and active task documents as needed

## Source-of-Truth Hierarchy

- `AGENTS.md` is the repo-wide rule source.
- Scoped `AGENTS.md` files govern their own folders and bridge/workflow work when applicable.
- `PLANS.md` is the durable project-status source.
- `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md` governs Roadmap v2 execution.
- Active tracker and node Issues record GitHub state, but they must be freshly verified.
- PRs and comments are historical or append-only evidence unless explicitly identified as current.
- `README.md` is a public overview, not the safest current-truth authority.

## Current Important Anchors

- Roadmap v2 tracker: Issue `#168`
- Active RV2-03 node: Issue `#175`
- Deferred workflow-hardening anchor: Issue `#188`
- Records and closeout planning anchor: Issue `#190`
- RV2-03 lessons publication lane: PR `#186`
- Canonical branch: `master`, with HEAD always requiring fresh verification

## OPT Records

- OPT-01: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md` defines workflow optimization contracts.
- OPT-02: `docs/POST_RV2_03_MINIMAL_EVIDENCE_COLLECTOR_V1.md` documents the minimal local facts-only evidence collector prototype.
- OPT-03: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.md` records the historical A/B workflow benchmark.
- OPT-04: `docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.md` records the mockup-first benchmark and UI contract pattern.
- OPT-05: `docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.md` records the systematic debugging profile benchmark.

## OPT-06 Status

- OPT-06 is not authorized.
- The current repo handoff from OPT-05 proposes systematic debugging profile follow-up planning.
- Older external research used OPT-06 for a codebase-memory CLI benchmark.
- A future planner must resolve naming and scope before using OPT-06.

## RV2 / Product Checkpoint Warning

- RV2-03 is not `DONE` unless freshly verified otherwise.
- RV2-04 is not authorized unless explicitly approved later.
- RV2-P1 product-mainline checkpoint should be considered after RV2-03 or RV2-04 according to `PLANS.md` and Roadmap rules.

## Stale Surface Warnings

- `README.md` may contain stale current-status language.
- Issue bodies may lag behind append-only comments.
- Old PR bodies and old handoffs are historical evidence, not current truth.
- Exact branch, HEAD, auth, and working tree must be freshly verified.

## Raw Evidence Boundary

- Local raw evidence, temp evidence roots, command logs, and host-specific artifacts should not be committed unless specifically approved.
- Summaries must not replace raw evidence for review.

## Course Host Quick Restore

- `docs/COURSE_HOST_QUICK_RESTORE_RUNBOOK.md` is the daily quick-restore runbook for reset course machines.
- `docs/COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md` remains the detailed recovery reference.
- `scripts/course_environment_restore_review.ps1` is the preferred wrapper entry point.
- `scripts/bootstrap_course_environment.ps1` is the lower-level bootstrap script and should not be the first daily manual entry unless the wrapper fails.
## Deferred Candidate Nodes

These are candidates only and are not activated by this index:

- REC-01 full records closeout
- OPS-01 Course Host Quick Restore Compression
- OPT-06 scope-resolution / follow-up planning
- RV2-P1 product checkpoint
- RV2-04 runtime contract binding
