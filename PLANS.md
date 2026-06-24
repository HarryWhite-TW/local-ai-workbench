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
- Current post-PR-#166 `master` merge commit: `380f1c2fc1d7ea6201da7e7a56da387aea766d48`.
- Permanent fixed Bridge Inbox: Issue `#147`.
- Latest reported B4-D focused validation: `78 passed`.
- Latest reported adjacent validation: `126 passed`.
- Course-computer environment restore/import check: `COURSE ENV OK`.
- The live B4-D smoke has not been authorized or executed.
- Manual `PollOnce` remains the verified recovery path, not the target daily experience.
- B3 implementation exists, but primary-host operational daily-use acceptance remains to be proven.
- Phase C ChatGPT App / MCP remains deferred until Phase B is stable and accepted.
- High-risk operations remain separately approval-gated.
- Raw local audit packets may remain local; durable conclusions and canonical references belong in GitHub and repository documentation.

Bridge Operator remains development workflow tooling and portfolio engineering evidence, not product runtime.

## Bridge Roadmap v2 Position

The proposed execution-governance specification is:

```text
docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md
```

Roadmap v2 is subordinate to:

```text
docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
docs/BRIDGE_OPERATOR_V0_SPEC.md
```

The specification remains proposed until its documentation PR is explicitly approved and merged. Before merge it does not authorize tracker creation, node activation, live smoke execution, automatic polling, startup, MCP, or any high-risk operation.

After adoption, GitHub governance uses:

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

Roadmap v2 default sequence after specification adoption:

1. `RV2-00` — specification adoption and execution baseline.
2. `RV2-01` — one supervised B4-D live smoke through the existing path.
3. `RV2-02` — B4-D closeout and documentation truth synchronization.
4. `RV2-03` — B3 operational acceptance on the primary home Windows host.
5. `RV2-04` — Task Packet v1.1 to runtime execution-contract binding.
6. `RV2-05` — minimal thin `lawb` CLI facade.
7. `RV2-06` — execution profiles and evidence-based token control.
8. `RV2-07` — optional Phase B4 visible operator UX.
9. `RV2-08` — separately approved Phase B5 Windows login startup.
10. `RV2-09` — Phase C MCP feasibility and bounded integration.
11. `RV2-P1` — parallel product-mainline checkpoint after operational or runtime-binding milestones.

This order may change only through explicit user-approved change control. Completion or merge of one node does not automatically authorize the next node.

## Immediate Next Gate

The current task is documentation-only adoption of Roadmap v2.

Authorized scope for this adoption task:

- add `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md`;
- update `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`;
- update `PLANS.md`;
- commit, push, and open a documentation PR on the approved branch.

Not authorized by this task:

- merge the documentation PR;
- create the tracker or `RV2-01` Issue before merge;
- publish B4-D markers;
- execute B1, B2, B3, Dispatcher, Runner, Codex, or live B4-D;
- enable automatic polling, startup, tray UI, service, or MCP;
- modify labels;
- delete a branch;
- add commit, push, close, PR, merge, or approval-chaining authority to the bridge runtime.

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
- 2026-06-24: Merged B4-D smoke planning and manifest-validator preparation through PR #166; began Roadmap v2 documentation-only adoption with live smoke still separately gated.
- 2026-06-15: Completed Bridge Operator B1 through PR #139 and UTF-8 reliability follow-up PR #143; final post-merge verification passed with 102 tests and clean stderr; began B1 closeout documentation reconciliation through Issue #145.
- 2026-06-14: Began Workflow Governance Reset through Issue #135, clarified Issue #114 as historical roadmap evidence, and kept B1, Phase C, and high-risk operations separately approval-gated.
- 2026-06-13: Merged PR #134 into `master`, verified post-merge master state, cleaned up the merged feature branch, and returned focus to visible product value.
- 2026-06-13: Recorded B0 closeout status, completed/superseded Issue cleanup, and separate PR approval requirement for bridge discipline integration.
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.
