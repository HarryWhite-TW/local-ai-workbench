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

- The verified Lv4.5 baseline uses ChatGPT-authored `CHATGPT-DISPATCH` requests, Dispatcher v1 `PollOnce`, Runner v1 ReviewBundle, Codex, and `LAWBRUNNER-RESULT` readback.
- B0 bridge discipline was integrated through PR #134.
- Governance Reset #135 is completed.
- Bridge Operator B1 is completed through PR #139 and follow-up PR #143.
- Current B1-integrated `master`: `e03e04729edba08a74c1ef3f45a51e0092fba72d`.
- Final B1 verification passed with 102 tests, compileall, a real fixed-Inbox read-only dry run, clean stderr, and a clean working tree.
- B1 stops before Dispatcher, Runner, or Codex delegation by design.
- B2 has not started and requires a separate bounded task and explicit approval.
- The permanent Bridge Inbox has not yet been selected.
- Manual `PollOnce` remains the verified recovery path, not the target daily experience.
- Phase C ChatGPT App / MCP remains deferred until Phase B is stable.
- High-risk operations remain separately approval-gated.
- Raw local audit packets remain local; their durable conclusions and canonical references are preserved in GitHub and `docs/BRIDGE_OPERATOR_B1_CLOSEOUT.md`.

Bridge Operator remains development workflow tooling and portfolio engineering evidence, not product runtime.

## Current Integration Sequence

1. B0 documentation reconciliation - complete.
2. Governance Reset #135 - complete.
3. B1 implementation through #137 / #138 and PR #139 - complete.
4. Traditional Chinese Windows UTF-8 repair through #142 and PR #143 - complete.
5. Final post-merge B1 verification - complete.
6. B1 closeout documentation reconciliation through #145 - current activity.
7. Select one permanent fixed Bridge Inbox - separate decision required.
8. Create one bounded B2 implementation Issue - separate approval required.
9. B2 proves one-shot `maybe-status-check`, then one-shot `run-reviewbundle`.
10. B3 begins only after B2 passes and is separately approved.
11. Product-facing demo, onboarding, and portfolio work remain valid parallel priorities.

This documentation task does not authorize automatic polling, delegation, bounded loops, startup, tray UI, MCP, new authority, commit, push, Issue close, labels, PR, merge, branch deletion, or approval chaining.

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
- 2026-06-15: Completed Bridge Operator B1 through PR #139 and UTF-8 reliability follow-up PR #143; final post-merge verification passed with 102 tests and clean stderr; began B1 closeout documentation reconciliation through Issue #145.
- 2026-06-14: Began Workflow Governance Reset through Issue #135, clarified Issue #114 as historical roadmap evidence, and kept B1, Phase C, and high-risk operations separately approval-gated.
- 2026-06-13: Merged PR #134 into `master`, verified post-merge master state, cleaned up the merged feature branch, and returned focus to visible product value.
- 2026-06-13: Recorded B0 closeout status, completed/superseded Issue cleanup, and separate PR approval requirement for bridge discipline integration.
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.
