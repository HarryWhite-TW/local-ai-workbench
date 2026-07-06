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
- RV2-03: `ACTIVE` — Phase B change-control.
- No next runtime implementation branch is approved; the docs-only truth-sync working branch is not a runtime baseline.
- Pre-truth-sync Phase A implementation baseline commit: `9749911badec6c4011d17170f55b4305fe47a08c`.
- Latest reported B4-D focused validation: `78 passed`.
- Latest reported adjacent validation: `126 passed`.
- Course-computer environment restore/import check: `COURSE ENV OK`.
- One supervised B4-D `run-reviewbundle` smoke succeeded on clean `master` at full HEAD `f41172b1ab25b2f4db4408f2fa825deb6e754cbb`.
- Manifest SHA-256: `34d17e23f94f939765b5ed761d34aa1b3ec018e31f868857431c02314e9bf080`.
- Evidence comments: dispatch `4795080463`, Inbox `4795082149`, Runner review bundle `4795131449`, matching `LAWBRUNNER-RESULT` `4795131543`.
- Exactly one B2/Dispatcher/Runner/Codex chain ran. It succeeded with Codex exit code `0`, no retry, no changed files, and a clean final worktree.
- Manual `PollOnce` remains the verified recovery path, not the target daily experience.
- B3 implementation exists, but primary-host operational daily-use acceptance remains to be proven.
- RV2-03 Phase A implementation evidence now includes A0 Windows host compatibility hardening, A1 Host Check Harness, A2 request lifecycle and `CONSUMED` handling, A3 read-only publication preflight, B2 tool-resolution preflight, fresh-reboot branch recovery, course-computer environment recovery, post-recovery readiness gate, and Recovery Script native-command/auth hardening.
- GitHub Issue #168 and Issue #175 bodies retain older pre-D2 text from the 2026-07-02 synchronization.
- Append-only comments added on 2026-07-06 record PR #183 merge, D2 current truth, and RV2-03 `ACTIVE`.
- Those comments supersede the older Issue body statements for current status.
- Canonical Issue body cleanup remains part of RV2-03 final closeout, and this focused documentation repair does not modify either Issue.
- RV2-03 Phase A final acceptance passed on 2026-06-30.
- RV2-03 Phase B B0 has been accepted under the corrected oracle and requires no rerun; this does not constitute Phase B/B3 operational acceptance.
- Phase B operational acceptance remains required on the user-designated Primary Operational Host, and RV2-03 is not `DONE`.
- D2 merge baseline used by this repair: `master@0cffe7cb4f28ea24691f69bce32d60f8d66ef681`.
- PR #181 accepted D1 as the standalone durable-evidence reconciliation prerequisite; feature head `74de2c0818ef6d957aa1498d2330dcfe68ced829` merged as `de37562670416950a999fae1b46a5efa78bca2a7`.
- D1 focused resolver verification reported `59 passed`; final related verification reported `158 passed`.
- PR #183 implemented and merged D2 as `master@0cffe7cb4f28ea24691f69bce32d60f8d66ef681`, adding the durable evidence provider, pre-Dispatcher reconciliation, local `CONSUMED` reconstruction, and delegation outcome tracking.
- PR #183 verification reported provider + B3 tests at `93 passed`, D1 resolver tests at `59 passed`, and the final `tests/local_runner_bridge` suite at `662 passed`.
- Current Primary Operational Host: the course Windows computer used for the user's normal project work.
- Secondary Compatibility Host: the home Windows computer; optional compatibility evidence there does not block RV2-03 completion.
- Issue #184 completed one trusted Dispatcher / Runner / Codex chain against `master@0cffe7cb4f28ea24691f69bce32d60f8d66ef681`; one trusted matching result was published, Runner and Codex exited `0`, no files changed, and the repository remained clean.
- The Issue #184 outer evidence wrapper timed out after nested completion. This is accepted normal-chain evidence, not final Phase B acceptance.
- PR #185 carries the safe-wait per-cycle outcome-isolation repair for B3 audit logging.
- Because the current Primary Operational Host may lose local operator state after reset, cross-reset duplicate suppression or fail-closed reconciliation against trusted durable GitHub request/result evidence remains a required and unaccepted Phase B acceptance case.
- Durable-evidence reconciliation is a critical acceptance requirement, not an optional documentation note.
- PR #177 is merged: `1acfe502271f77b4872d39adf86b687c20fb2396` was the feature head merged through PR #177 into `master@66ad9f64d59718d096dc8a2752e88f8cc44f10d6`; it is historical merge evidence, not a newly approved runtime implementation branch or a separate runtime baseline.
- D2 runtime implementation is merged, but Primary Operational Host state-loss durable reconciliation has not been accepted.
- The next operational gate after PR #185 merges is the controlled state-loss reconciliation and local duplicate-gate acceptance.
- RV2-03 remains `ACTIVE`; RV2-04 remains unauthorized.
- Phase C ChatGPT App / MCP remains deferred until Phase B is stable and accepted.
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
4. `RV2-03` — B3 operational acceptance on the user-designated Primary Operational Host, currently the course Windows computer (`ACTIVE` — Phase B change-control).
5. `RV2-04` — Task Packet v1.1 to runtime execution-contract binding.
6. `RV2-05` — minimal thin `lawb` CLI facade.
7. `RV2-06` — execution profiles and evidence-based token control.
8. `RV2-07` — optional Phase B4 visible operator UX.
9. `RV2-08` — separately approved Phase B5 Windows login startup.
10. `RV2-09` — Phase C MCP feasibility and bounded integration.
11. `RV2-P1` — parallel product-mainline checkpoint after operational or runtime-binding milestones.

This order may change only through explicit user-approved change control. Completion or merge of one node does not automatically authorize the next node.

## Immediate Next Gate

Tracker #168 is the designated canonical GitHub Roadmap surface. GitHub Issue #168 and Issue #175 bodies retain older pre-D2 text from the 2026-07-02 synchronization. Append-only comments added on 2026-07-06 record PR #183 merge, D2 current truth, and RV2-03 `ACTIVE`; those comments supersede the older body statements for current status. Canonical Issue body cleanup remains part of RV2-03 final closeout, and this focused documentation repair does not modify either Issue.

Current RV2-03 Phase A evidence is implemented and verified beyond the older repository documentation. The accepted evidence includes A0 Windows host compatibility hardening, A1 Host Check Harness, A2 request lifecycle and `CONSUMED` handling, A3 read-only publication preflight, B2 tool-resolution preflight, fresh-reboot branch recovery, course-computer environment recovery, post-recovery readiness gate, and Recovery Script native-command/auth hardening.

GitHub Issue #168 and Issue #175 bodies retain older pre-D2 text, while append-only comments added on 2026-07-06 record PR #183 merge, D2 current truth, and RV2-03 `ACTIVE`; those comments supersede the older body statements for current status until canonical body cleanup in RV2-03 final closeout. RV2-03 Phase A final acceptance passed on 2026-06-30. PR #177 is merged: `1acfe502271f77b4872d39adf86b687c20fb2396` was the feature head merged through PR #177 into `master@66ad9f64d59718d096dc8a2752e88f8cc44f10d6`. PR #179 records `853e341d6a32cdbad5fdb7f77b05353187beccf2` as pre-merge master, `649212b665264f80c95f940ec713f93dfb9ef0ca` as feature head, and `cd22eb73a1ea3f8ccd7efe146a49f567b78f7ea1` as the accepted merge commit. Those SHAs remain historical evidence, not the current canonical baseline. The canonical repository branch is `master`; current `master` HEAD is mutable current-state data that must be revalidated from Git at the beginning of each engineering task. D2 merge baseline used by this repair: `master@0cffe7cb4f28ea24691f69bce32d60f8d66ef681`. PR #181 accepted D1 as a standalone durable-evidence reconciliation prerequisite: feature head `74de2c0818ef6d957aa1498d2330dcfe68ced829` merged as `de37562670416950a999fae1b46a5efa78bca2a7`, with reported focused resolver verification of `59 passed` and final related verification of `158 passed`. PR #183 implemented and merged D2 as `master@0cffe7cb4f28ea24691f69bce32d60f8d66ef681`, adding the durable evidence provider, pre-Dispatcher reconciliation, local `CONSUMED` reconstruction, and delegation outcome tracking. Issue #184 completed one trusted Dispatcher / Runner / Codex chain with one trusted result, no changed files, and a clean repository; the outer evidence wrapper timed out after nested completion. This is accepted normal-chain evidence, not final Phase B acceptance. RV2-03 Phase B B0 has been accepted under the corrected oracle and requires no rerun, but Phase B operational acceptance on the user-designated Primary Operational Host remains separately gated and required before RV2-03 can be `DONE`. No next runtime implementation branch is approved. The current designated host is the course Windows computer, while the home Windows computer is a Secondary Compatibility Host. The course host's reset and state-loss behavior must prove duplicate suppression or fail-closed reconciliation against trusted durable GitHub request/result evidence before final acceptance. PR #185 carries the safe-wait per-cycle outcome-isolation repair, and state-loss durable reconciliation remains unaccepted.

The next operational gate after PR #185 merges is the controlled state-loss reconciliation and local duplicate-gate acceptance. D2 local implementation is merged, but D2 completion does not authorize additional live GitHub access, request or result publication, Dispatcher, Runner, Codex delegation, Primary Operational Host execution, automatic retry, startup, tray, service, MCP, trusted-actor or allowlist changes, authority expansion, commit, push, or GitHub writes beyond separately approved tasks. Current D2 decision mapping is implemented as: `COMPLETED` reconstructs or records local `CONSUMED` state and does not invoke Dispatcher; `NOT_FOUND` does not create `CONSUMED` state and may proceed only through existing ordinary delegation gates; `BLOCKED` does not invoke Dispatcher and records a reviewable fail-closed reason; `ERROR` does not invoke Dispatcher and records provider or evidence-read failure. RV2-03 remains `ACTIVE`; RV2-04 remains unauthorized.

The experimental `feat/lawb-controlled-development-skill` branch is separate, unmerged, and not a mainline capability.

The earlier RV2-03 Phase A truth-sync commit was `b90d56fb5ea08e0ac5036f50af8efc14ad5eab43`. It is historical evidence, not the current HEAD and not the commit that will result from this Phase B truth-sync task.

The approved strategic direction is to prepare the bridge for future repository separation as reusable cross-project development infrastructure. `local-ai-workbench` remains the first validated host and reference host. Physical extraction, a new repository, file movement, package publishing, import rewiring, runtime-boundary changes, startup, tray UX, service behavior, MCP, and authority expansion are not authorized here. A later separately approved migration implementation node is required.

Deferred items still include distinct `manifest_review_expires` and `execution_request_expires` fields, a versioned Host Profile, the full shared Bootstrap/runtime resolver contract where not already proven, the outer Runner result evidence contract where not already proven, Phase B daily B3 operational acceptance, startup, tray, service, and MCP.

The current in-repository implementation remains the proven baseline until migration acceptance passes. Cross-project portability cannot be claimed until the extracted design is validated with at least two different repositories.

## Product Parallel Priority

Product-facing demo, onboarding, reliability, architecture evidence, and portfolio work remain valid parallel priorities.

Bridge work must not indefinitely displace the Local Document-to-Knowledge Workbench. After `RV2-03` or `RV2-04`, the `RV2-P1` checkpoint must evaluate whether additional bridge work produces enough real reduction in risk or manual friction to justify continuing before product-facing work.

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
- 2026-06-25: Recorded RV2-01/B4-D supervised smoke success, closed stale readiness language, and added the bounded repository-separation design while keeping physical extraction unauthorized.
- 2026-06-24: Began RV2-01 readiness truth synchronization while keeping the node planned and the live smoke separately gated.
- 2026-06-24: Adopted Bridge Roadmap v2 execution governance through squash-merged PR #167, created tracker #168 and planned node #169, and kept live B4-D separately gated.
- 2026-06-24: Merged B4-D smoke planning and manifest-validator preparation through PR #166; began Roadmap v2 documentation-only adoption with live smoke still separately gated.
- 2026-06-15: Completed Bridge Operator B1 through PR #139 and UTF-8 reliability follow-up PR #143; final post-merge verification passed with 102 tests and clean stderr; began B1 closeout documentation reconciliation through Issue #145.
- 2026-06-14: Began Workflow Governance Reset through Issue #135, clarified Issue #114 as historical roadmap evidence, and kept B1, Phase C, and high-risk operations separately approval-gated.
- 2026-06-13: Merged PR #134 into `master`, verified post-merge master state, cleaned up the merged feature branch, and returned focus to visible product value.
- 2026-06-13: Recorded B0 closeout status, completed/superseded Issue cleanup, and separate PR approval requirement for bridge discipline integration.
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.
