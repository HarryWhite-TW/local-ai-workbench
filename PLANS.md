# PLANS.md

## Project Goal
Build a controlled local document-to-knowledge workbench with a single Web entrypoint.
The system is read-first and approval-gated for any write-like action.

## Current Product Position
- Localhost only
- Single user only
- Prototype only
- Not a productization project
- Local document ingestion through a configured root folder
- SQLite indexing for supported local documents
- Local search by title, relative path, and extracted content
- Deterministic single-document summaries
- Obsidian-ready Markdown export after preview
- Export destination intelligence for Obsidian Vault roots, folders inside vaults, normal Markdown folders, missing folders, and non-folder paths

The public product mainline remains the Local Document-to-Knowledge Workbench. It is not a SaaS product, background automation platform, or chat-first product.

## Development Workflow Position

Development workflow tooling is separate from the product runtime.

Engineering record navigation and OPT-series artifacts are indexed in `docs/ENGINEERING_RECORDS_INDEX.md`. The index helps locate records but does not replace `PLANS.md`, active Roadmap Issues, or fresh Git/GitHub verification.

- The verified Lv4.5 recovery baseline uses ChatGPT-authored `CHATGPT-DISPATCH` requests, Dispatcher v1 `PollOnce`, Runner v1 ReviewBundle, Codex, and `LAWBRUNNER-RESULT` readback.
- B0 bridge discipline was integrated through PR #134.
- Governance Reset #135 is completed.
- Bridge Operator B1 was completed through PR #139 and reliability follow-up PR #143.
- B2 one-shot delegation was completed through PR #149, with Runner UTF-8 compatibility follow-up through PR #150.
- B3-A foreground dry-run bounded-loop foundation was completed through PR #152.
- B3-B real `maybe-status-check` bounded-loop delegation was completed through PR #154.
- B3-C opt-in real `run-reviewbundle` bounded-loop delegation was completed through PR #156.
- Runner stdin hardening was completed through PR #161 and PR #162.
- Bridge Operator safety visibility, read-only diagnostics, and course-environment bootstrap were completed through PR #163, PR #164, and PR #165.
- B4-D fresh-reboot smoke planning and manifest-validator preparation were completed through PR #166.
- Roadmap v2 execution governance was adopted through PR #167.
- Current Roadmap v2 activation commit: `9baf606197bbdf886b23782d1c67f2a872e76e09`.
- Permanent fixed Bridge Inbox: Issue `#147`.
- Roadmap v2 tracker: Issue `#168`.
- RV2-00: `DONE`.
- RV2-01: `DONE`.
- RV2-02: `DONE`.
- RV2-03: `DONE` — formal Primary Operational Host acceptance passed on 2026-07-10.
- RV2-04 remains inactive and unauthorized. REC-02 is `DONE`: final semantic acceptance passed, PR #192 merged, and the canonical merge commit is `9d458becce35d1098244b15b4fe7044d78c8f4c9`. OPT-06 is complete as a Chat-only REC-02 retrospective with `GO — conditional default` for ambiguous, safety-relevant, environment-sensitive, or evidence-heavy debugging. OPT-07 is `DONE / NO-GO`: the isolated `codebase-memory-mcp` v0.9.0 benchmark achieved only `13.04%` exploration-cost reduction, missed safety-critical Dispatcher/Runner and durable-evidence relations, completed full rollback, and was not adopted for the current workflow. Issue #188 remains deferred, and no next node is automatically activated.
- Pre-truth-sync Phase A implementation baseline commit: `9749911badec6c4011d17170f55b4305fe47a08c`.
- Latest reported B4-D focused validation: `78 passed`.
- Latest reported adjacent validation: `126 passed`.
- Course-computer environment restore/import check: `COURSE ENV OK`.
- One supervised B4-D `run-reviewbundle` smoke succeeded on clean `master` at full HEAD `f41172b1ab25b2f4db4408f2fa825deb6e754cbb`.
- Manifest SHA-256: `34d17e23f94f939765b5ed761d34aa1b3ec018e31f868857431c02314e9bf080`.
- Evidence comments: dispatch `4795080463`, Inbox `4795082149`, Runner review bundle `4795131449`, matching `LAWBRUNNER-RESULT` `4795131543`.
- Exactly one B2/Dispatcher/Runner/Codex chain ran. It succeeded with Codex exit code `0`, no retry, no changed files, and a clean final worktree.
- Manual `PollOnce` remains the verified recovery path, not the target daily experience.
- B3 implementation and the RV2-03 Primary Operational Host acceptance are complete; manual `PollOnce` remains the recovery path, not the target daily experience.
- RV2-03 Phase A implementation evidence now includes A0 Windows host compatibility hardening, A1 Host Check Harness, A2 request lifecycle and `CONSUMED` handling, A3 read-only publication preflight, B2 tool-resolution preflight, fresh-reboot branch recovery, course-computer environment recovery, post-recovery readiness gate, and Recovery Script native-command/auth hardening.
- RV2-03 accepted outcome: on the course Windows computer at `master@180d966e46194c0cd0d542d90376c52e84dda05b`, formal acceptance used manifest SHA-256 `50d7a481987c16e052e47d635d338c16afdf5a117ed48a2c513733e28382078c`, Inbox request `rv2-03-final-primary-inbox-20260710T044049Z-1b1bd31e`, and dispatch request `rv2-03-final-primary-dispatch-20260710T044049Z-1b1bd31e`.
- Durable GitHub evidence: dispatch marker `4932081797`, Inbox marker `4932081856`, Runner review bundle `4932108053`, and trusted matching result `4932108148`.
- The normal request ran exactly once: one Dispatcher, one Runner, one Codex execution, one trusted matching success result, and one local `CONSUMED` record.
- Complete local BridgeOperator state loss was accepted. Durable `COMPLETED` reconciliation reconstructed one `CONSUMED` record without Dispatcher, Runner, or Codex rerun; the subsequent duplicate gate prevented another execution.
- No automatic retry or unexpected GitHub write occurred, and the repository remained clean.
- Phase C ChatGPT App / MCP remains deferred pending separate approval.
- Startup, tray UX, service behavior, MCP, automatic commit/push/close/merge, and approval chaining remain out of scope.
- High-risk operations remain separately approval-gated.
- Raw local audit packets may remain local; durable conclusions and canonical references belong in GitHub and repository documentation.

Bridge Operator remains development workflow tooling and portfolio engineering evidence, not product runtime.

## Bridge Roadmap v2 Position

The active execution-governance specification is:

```text
docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md
```

Roadmap v2 is subordinate to:

```text
docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
docs/BRIDGE_OPERATOR_V0_SPEC.md
```

The specification was explicitly approved and squash-merged through PR #167 at commit `9baf606197bbdf886b23782d1c67f2a872e76e09`. Its activation does not authorize live smoke execution, automatic polling, startup, MCP, or any high-risk operation.

The active GitHub governance model uses:

- one long-lived Roadmap v2 tracker Issue;
- one active execution-node Issue at a time;
- entry and acceptance criteria for each node;
- explicit PR, merge, post-merge, and closeout evidence;
- no initial dependency on GitHub Projects, milestones, or labels.

## Current Integration Sequence

Completed baseline:

1. B0 documentation and governance reconciliation.
2. Governance Reset #135.
3. B1 fixed-Inbox read-only validation.
4. B2 one-shot Dispatcher delegation.
5. B3-A dry-run bounded-loop foundation.
6. B3-B `maybe-status-check` real delegation.
7. B3-C `run-reviewbundle` opt-in real delegation.
8. Windows UTF-8 and Runner stdin reliability hardening.
9. B4-A operator safety visibility.
10. B4-B read-only diagnostics.
11. B4-C safe course-environment bootstrap.
12. B4-D smoke plan and local-only manifest validator.
13. Roadmap v2 execution-governance adoption through PR #167.

Roadmap v2 default sequence:

1. `RV2-00` — specification adoption and execution baseline (`DONE`).
2. `RV2-01` — one supervised B4-D live smoke through the existing path (`DONE`).
3. `RV2-02` — B4-D closeout, documentation truth synchronization, and repository-separation design (`DONE`).
4. `RV2-03` — B3 operational acceptance on the user-designated Primary Operational Host, the course Windows computer (`DONE` — formal acceptance passed 2026-07-10).
5. `RV2-04` — Task Packet v1.1 to runtime execution-contract binding.
6. `RV2-05` — minimal thin `lawb` CLI facade.
7. `RV2-06` — execution profiles and evidence-based token control.
8. `RV2-07` — optional Phase B4 visible operator UX.
9. `RV2-08` — separately approved Phase B5 Windows login startup.
10. `RV2-09` — Phase C MCP feasibility and bounded integration.
11. `RV2-P1` — parallel product-mainline checkpoint after operational or runtime-binding milestones.

This order may change only through explicit user-approved change control. Completion or merge of one node does not automatically authorize the next node.

## Immediate Next Gate

RV2-03 is `DONE`. The accepted Primary Operational Host evidence is recorded above and on Issue #184. GitHub Issue #168 and Issue #175 retain historical bodies; this repository closeout does not mutate them.

REC-02 is `DONE`. Course Host Complete Recovery v2 passed final semantic acceptance, merged through PR #192, and was post-merge verified at canonical merge commit `9d458becce35d1098244b15b4fe7044d78c8f4c9`. Its completion does not activate RV2-04, Issue #188, or any later node. Startup, tray, service, MCP, automatic commit/push/close/merge, approval chaining, trusted-actor changes, and allowlist expansion remain out of scope.

OPT-06 is complete as a read-only REC-02 retrospective and is adopted only as a conditional debugging-profile recommendation for ambiguous, safety-relevant, environment-sensitive, or evidence-heavy work. OPT-07 is complete and accepted as `NO-GO`; `codebase-memory-mcp` is not adopted as a required or default Local AI Workbench exploration tool because it reduced comparable exploration operations by only `13.04%` and missed safety-critical relations. These outcomes do not activate RV2-04, Issue #188, another OPT node, MCP, watchers, services, or new authority.

The experimental `feat/lawb-controlled-development-skill` branch is separate, unmerged, and not a mainline capability.

The earlier RV2-03 Phase A truth-sync commit was `b90d56fb5ea08e0ac5036f50af8efc14ad5eab43`. It is historical evidence, not the current HEAD and not the commit that will result from this Phase B truth-sync task.

The approved strategic direction is to prepare the bridge for future repository separation as reusable cross-project development infrastructure. `local-ai-workbench` remains the first validated host and reference host. Physical extraction, a new repository, file movement, package publishing, import rewiring, runtime-boundary changes, startup, tray UX, service behavior, MCP, and authority expansion are not authorized here. A later separately approved migration implementation node is required.

Deferred items still include distinct `manifest_review_expires` and `execution_request_expires` fields, a versioned Host Profile, the full shared Bootstrap/runtime resolver contract where not already proven, the outer Runner result evidence contract where not already proven, startup, tray, service, and MCP.

The current in-repository implementation remains the proven baseline until migration acceptance passes. Cross-project portability cannot be claimed until the extracted design is validated with at least two different repositories.

## Product Parallel Priority

Product-facing demo, onboarding, reliability, architecture evidence, and portfolio work remain valid parallel priorities.

Bridge work must not indefinitely displace the Local Document-to-Knowledge Workbench. After `RV2-03` or `RV2-04`, the `RV2-P1` checkpoint must evaluate whether additional bridge work produces enough real reduction in risk or manual friction to justify continuing before product-facing work.

## Ecosystem Strategy Checkpoint

The ecosystem-level strategy is recorded in `docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md`. The ecosystem is the Human-Governed AI Work System: one ecosystem with multiple bounded products and tools. The Semi-Automated AI Engineering Workflow remains the first-priority ecosystem mainline and receives preferential Agentic quota. Reverb, the Human Approval Automation Gateway/n8n integration surface, Local AI Workbench, and Portfolio/Brand Website remain bounded parallel components.

The repository's Local AI Workbench product mainline and the ecosystem-global priority are distinct: `repo-local product mainline != ecosystem-global strategic priority`. Workbench Phase 5.4 is not an upper-level gate for Workflow continuation. The Workflow separation design remains valid, but physical extraction, a new repository, migration, and cutover remain unauthorized.

Phase 5.1–5.3 product-validation evidence is durably recorded in `docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md`. Its exact final verdict is `PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED`; the five-minute continuous timing claim remains unproven, summary usefulness is a small gap, and encoding/rendering anomalies are a non-blocking gap. This record does not activate Phase 5.4 or any later implementation node.

## WF-REENTRY Capability Strategy

The accepted WF-REENTRY capability adjudication is recorded in `docs/WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md`. The Workflow is repositioned as the Human-Governed AI Engineering Control Layer: its governance, evidence, authority, and current-truth core is `KEEP`, while transport-only custom infrastructure is `THIN`. Native Chat -> Codex dispatch is a replacement candidate, not an unconditional default, because reliable full-result readback is not fully proven in this user's App environment. Specialized Bridge safety and durable reconciliation remain valuable.

Direction Lock v1.2 remains authoritative for current Bridge work, while its transport strategy is `REVIEW_REQUIRED`. Repository separation remains `DEFER`; no RV2-04, Phase 5.4, benchmark, or implementation node is activated. A Native-vs-Bridge Reliability Benchmark is the next recommended review only.

## Historical M1 Baseline

The original M1 plan is retained here as historical baseline evidence.

### M1 Scope
- Minimal Web UI skeleton
- Minimal Python API skeleton
- SQLite persistence
- Fake preview / approve / audit flow
- Initial `AGENTS.md` and `PLANS.md`

### M1 Acceptance
- Web and API start locally
- User can create a preview action
- User can approve that action
- Action state persists in SQLite
- Audit events are stored and visible
- No real Gmail, Calendar, LLM, or file-writing integration

### Deferred After M1
- Real LLM integration
- Local file ingestion
- Google OAuth
- Gmail read / draft create
- Calendar query / event create
- Prompt versioning system
- Real E2E automation

## Change Log
- 2026-07-12: Recorded the accepted WF-REENTRY native-capability overlap adjudication. Repositioned the Workflow as the Human-Governed AI Engineering Control Layer, retained the governance and specialized safety core, thinned universal transport assumptions, marked native dispatch as a replacement candidate with readback still unproven, set Direction Lock transport strategy to `REVIEW_REQUIRED`, and activated no implementation node.
- 2026-07-12: Added the ECO-DOC-01 durable strategy and product-validation records. Reaffirmed Workflow Mainline as the ecosystem first priority, preserved n8n/Gateway as a bounded ecosystem component, recorded Phase 5.1–5.3 as `PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED`, and did not activate Phase 5.4, RV2-04, repository separation, or any later node.
- 2026-07-11: Closed OPT-06 and OPT-07 workflow experiments. OPT-06 produced a `GO — conditional default` recommendation for systematic debugging on ambiguous, safety-relevant, environment-sensitive, or evidence-heavy work. OPT-07 was accepted as `NO-GO` after `codebase-memory-mcp` v0.9.0 reduced comparable exploration operations by only `13.04%`, missed safety-critical Dispatcher/Runner and durable-evidence relations, and completed full rollback without repository or configuration residue. No later node was activated.
- 2026-07-11: Closed REC-02 after final semantic acceptance and PR #192 merge at canonical commit `9d458becce35d1098244b15b4fe7044d78c8f4c9`; 111 unique related tests passed on the final code state. The combined one-shot suite was environment-blocked by antivirus interference with temporary fake executables and nested-process hangs, so split-module final-state evidence was used. RV2-04, Issue #188, OPT-06, and all later nodes remain inactive unless separately approved.
- 2026-07-10: Activated REC-02 under explicit approval for Course Host Complete Recovery v2 implementation; final acceptance remains required and no later node is activated.
- 2026-07-10: Closed RV2-03 after formal Primary Operational Host acceptance passed: exactly one normal Dispatcher/Runner/Codex execution succeeded, complete local state loss reconciled durably without rerun, the duplicate gate blocked later execution, and no automatic retry or unexpected GitHub write occurred. RV2-04, REC-02, Issue #188, and OPT nodes remain inactive unless separately approved.
- 2026-06-25: Recorded RV2-01/B4-D supervised smoke success, closed stale readiness language, and added the bounded repository-separation design while keeping physical extraction unauthorized.
- 2026-06-24: Began RV2-01 readiness truth synchronization while keeping the node planned and the live smoke separately gated.
- 2026-06-24: Adopted Bridge Roadmap v2 execution governance through squash-merged PR #167, created tracker #168 and planned node #169, and kept live B4-D separately gated.
- 2026-06-24: Merged B4-D smoke planning and manifest-validator preparation through PR #166; began Roadmap v2 documentation-only adoption with live smoke still separately gated.
- 2026-06-15: Completed Bridge Operator B1 through PR #139 and UTF-8 reliability follow-up PR #143; final post-merge verification passed with 102 tests and clean stderr; began B1 closeout documentation reconciliation through Issue #145.
- 2026-06-14: Began Workflow Governance Reset through Issue #135, clarified Issue #114 as historical roadmap evidence, and kept B1, Phase C, and high-risk operations separately approval-gated.
- 2026-06-13: Merged PR #134 into `master`, verified post-merge master state, cleaned up the merged feature branch, and returned focus to visible product value.
- 2026-06-13: Recorded B0 closeout status, completed/superseded Issue cleanup, and separate PR approval requirement for bridge discipline integration.
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.
