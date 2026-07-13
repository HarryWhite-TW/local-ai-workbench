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

## ECO-DOC-01 Durable Records

- `docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md` — ECO-01 strategy checkpoint for the Human-Governed AI Work System, including Workflow Mainline first priority, n8n/Gateway role, bounded Workbench role, dual-track strategy, and unauthorized separation boundary.
- `docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md` — ECO-02 product-validation evidence record for Workbench Phase 5.1–5.3, including the exact `PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED` verdict and its limitations.

These records are durable navigation and evidence surfaces. They do not replace `PLANS.md`, fresh Git/GitHub verification, or task-specific authority. They do not activate Phase 5.4, RV2-04, repository separation, or any later node.

## WF-REENTRY Durable Record

- `docs/WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md` — accepted capability-overlap adjudication and native-vs-Bridge strategy checkpoint, including `KEEP`, `THIN`, `REPLACE_BY_NATIVE CANDIDATE`, and `DEFER` classifications.

This entry is navigation, not implementation authority or a replacement for current-state verification. Fresh platform, Git, GitHub, authentication, and task-specific authority verification remains required.

## OPT Records

- OPT-01: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md` defines workflow optimization contracts.
- OPT-02: `docs/POST_RV2_03_MINIMAL_EVIDENCE_COLLECTOR_V1.md` documents the minimal local facts-only evidence collector prototype.
- OPT-03: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.md` records the historical A/B workflow benchmark.
- OPT-04: `docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.md` records the mockup-first benchmark and UI contract pattern.
- OPT-05: `docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.md` records the systematic debugging profile benchmark.
- OPT-06: completed as a Chat-only REC-02 retrospective; result `GO — conditional default` for ambiguous, safety-relevant, environment-sensitive, or evidence-heavy debugging. It created no repository artifact and added no authority.
- OPT-07: `docs/POST_RV2_03_CODEBASE_MEMORY_BENCHMARK_OPT07.md` records the isolated `codebase-memory-mcp` v0.9.0 CLI benchmark; result `DONE / NO-GO`, with `13.04%` exploration-cost reduction, incomplete safety-critical relations, complete rollback, and no adoption for the current workflow.

## OPT-06 / OPT-07 Status

- OPT-06 resolved the earlier naming ambiguity by keeping the repository-native systematic-debugging follow-up as OPT-06.
- The older external codebase-memory benchmark concept was renumbered to OPT-07 before execution.
- OPT-06 is complete as a read-only retrospective and is a conditional workflow recommendation, not mandatory process.
- OPT-07 is complete and accepted as `NO-GO`; `codebase-memory-mcp` is not adopted as a required or default Local AI Workbench exploration tool.
- Neither result activates RV2-04, Issue #188, another OPT node, MCP, watchers, services, or new authority.

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

## REC-02 Operational Field Evidence

- `docs/REC_02_OPERATIONAL_FIELD_EVIDENCE_COURSE_HOST_QUICK_RESTORE.md` — accepted real-reset field evidence showing the existing REC-02 Quick Restore path converged the course computer from a restored environment to full `READY` state across three bounded wrapper runs, with final focused pytest and Host Check exit `0`, clean Git state, and safety boundaries preserved.

This record does not reopen REC-02, classify the observed stale Layer 1 `ATTENTION` as a proven defect, authorize a script repair, or activate any later node. REC-02 remains `DONE`; single-transaction convergence after conditional browser authentication is preserved only as an improvement candidate.

## Course Host Quick Restore

- `docs/COURSE_HOST_QUICK_RESTORE_RUNBOOK.md` is the daily quick-restore runbook for reset course machines.
- `docs/COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md` remains the detailed recovery reference.
- `scripts/course_environment_restore_review.ps1` is the preferred wrapper entry point.
- `scripts/bootstrap_course_environment.ps1` is the lower-level bootstrap script and should not be the first daily manual entry unless the wrapper fails.

## Deferred Candidate Nodes

These are candidates only and are not activated by this index:

- REC-01 full records closeout
- OPS-01 Course Host Quick Restore Compression
- RV2-P1 product checkpoint
- RV2-04 runtime contract binding