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
- Workflow v1 Final Closeout record: `docs/WORKFLOW_V1_FINAL_CLOSEOUT.md`; it is the primary architecture, evidence, limitation, demonstration, and conditional final-transition record
- Accepted correction/publication PR: #211 on retained branch `workflow-v1-phase-c-powershell-env-correction`; accepted reviewed head `4d3b649da9c953480c5053ae8e0b1707315de3e6`; external Codex exact-head review completed with no major issues; canonical merge `38d3e96263b671a72141d0ab92b61b91a85e6c36`; post-merge canonical verification completed
- Tracker #168 historical intermediate synchronization: comment `5005537101`; it records PR #212 post-merge evidence and the then-current `REVIEW` state
- Tracker #168 reviewer-controlled final residual-review result anchor: comment `5010099708`; it records `ACCEPTED — FINAL RESIDUAL REVIEW PASSED`
- PR #213 final durable-status transition: exact reviewed head `60be637db0c237db3d53408a272fd3aaba98ec8b`; canonical merge `317cd7e9fedb153daa034c1e698819042e2e4564`; post-merge canonical verification completed
- Tracker #168 final `DONE` publication: comment `5010353117`
- Acceptance-integrity correction baseline: `a95d05388ad77963ee8cb44c0b7710a49a9d8421`
- Phase C evidence Issues: #207 first `maybe-status-check` failure; #208 corrected success; #209 first `run-reviewbundle` failure; #210 restored-CLI success and independent PASS
- PR #203: Final Closeout candidate publication; commit `368934f5c93d210c485d49180bc1c347d7d3647c`; canonical merge `c36a1b820e6f6786267057aa05d25697b9f1deca`
- PR #204: attempted `REVIEW` -> `DONE` transition; commit `240e47a77da753c9ffb619e79be1c15e20b23e7a`; canonical merge `b20a12c07cd2de7105b94b34ed2996b06f59b84a`
- RV2-03 accepted historical node: Issue `#175`
- Deferred workflow-hardening anchor: Issue `#188`
- Records and closeout planning anchor: Issue `#190`
- RV2-03 lessons publication lane: PR `#186`
- Canonical branch: `master`; PR #211 was opened against observed base snapshot `a3be6ad46e0a2a93f7fe87dfdd3c476ed3695abb`, with any later HEAD always requiring fresh verification

`PLANS.md` remains the current project-status authority. This index is navigation only and does not itself accept, activate, or grant authority for work. Post-merge automated P2 findings on PR #203 and PR #204 invalidated the earlier acceptance, so both remain historical integrity-incident evidence. PR #211 supplied the accepted correction. PR #212 was rereviewed at exact head `dd6046409505e009e95e3a68433bca147542a088`, merged canonically at `ee4f9c06dc48719b8165b75607e51d38e7344c6b`, and passed post-merge canonical verification. Tracker #168 comment `5005537101` remains historical intermediate `REVIEW` evidence, and reviewer-controlled comment `5010099708` anchors `ACCEPTED — FINAL RESIDUAL REVIEW PASSED`. PR #213 was exact-head reviewed at `60be637db0c237db3d53408a272fd3aaba98ec8b`, merged canonically at `317cd7e9fedb153daa034c1e698819042e2e4564`, and post-merge verified; Tracker #168 comment `5010353117` published final `DONE`. The first three mandatory Workflow v1 nodes remain `DONE`. Workflow v1 Final Closeout and Workflow v1 are `DONE — FINAL DURABLE TRUTH SYNCHRONIZED`; repository and tracker truth are synchronized, and no later node is activated. Feature branches and PR candidates are proposals, not current truth; merging the exact reviewed truth-sync content into `master` publishes the final `DONE` status, and post-merge canonical verification validates that publication. Successful verification requires no second repository wording update. The truth-sync PR number and its future merge SHA are intentionally not pre-recorded.

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

- RV2-03, RV2-P1-SYNC, RV2-04N, and Cross-Repository Bounded Proof are recorded as `DONE` by current canonical `PLANS.md` and accepted evidence.
- The first three mandatory Workflow v1 nodes are `DONE`: `RV2-P1-SYNC`, `RV2-04N`, and Cross-Repository Bounded Proof. Workflow v1 Final Closeout is `DONE — FINAL DURABLE TRUTH SYNCHRONIZED`.
- Accepted PR #211 candidate verification recorded targeted pycache regressions `10 passed`, Runner v1 `89 passed`, Runner v2 compatibility `4 passed`, related Runner/Bridge `810 passed`, full repository `1112 passed`, `0 failed`, and `git diff --check` exit `0`.
- Historical RV2-04 was narrowed into completed RV2-04N; historical RV2-05/07/08/09 remain deferred and RV2-06 remains partially absorbed.
- Tracker #168 comment `5005537101` remains historical intermediate `REVIEW` evidence; comment `5010099708` remains the final residual-review anchor; comment `5010353117` is the final `DONE` publication paired with PR #213 canonical merge `317cd7e9fedb153daa034c1e698819042e2e4564`.
- This final `DONE` status does not activate another node, Issue #188, Issue #190, Workbench Phase 5.4, RV2-05/07/08/09, unabsorbed RV2-06 work, a benchmark, startup, tray, service, MCP, physical separation, deferred scope, or new runtime, trusted-actor, allowlist, GitHub, or approval authority.

## Stale Surface Warnings

- `README.md` may contain stale current-status language.
- Issue bodies may lag behind append-only comments.
- Tracker #168 comment `4998971940` is a historical pre-PR-#212 `REVIEW` checkpoint. Comment `5005537101` is the intermediate PR #212 evidence synchronization that retained `REVIEW`. Comment `5010099708` is the reviewer-controlled final residual-review result anchor. Comment `5010353117` is the paired tracker final `DONE` publication.
- Old PR bodies and old handoffs are historical evidence, not current truth.
- `docs/SEMI_AUTOMATED_WORKFLOW_V1.md` and `docs/SEMI_AUTOMATED_WORKFLOW_V1_PROOF_REPORT.md` are historical operating/proof evidence, not current Workflow v1 completion truth.
- `docs/SEMI_AUTOMATED_WORKFLOW_BASELINE.md` is a historical RV2-03-era operational snapshot; its commands and evidence require fresh applicability checks.
- Phase statements in `docs/CHATGPT_CODEX_BRIDGE_REPOSITORY_SEPARATION_PLAN.md` are historical design context and do not override current `PLANS.md`; the separation design remains unimplemented and unauthorized.
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
- Issue #188 repository-native execution-gate work
- RV2-05 thin CLI facade
- unabsorbed RV2-06 execution-profile work
- RV2-07 visible operator UX
- RV2-08 login startup
- RV2-09 connector feasibility
- Native-vs-Bridge benchmark only if later evidence requires it
- physical repository separation under a separately approved migration node
