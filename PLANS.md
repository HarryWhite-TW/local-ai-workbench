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

- The verified Lv4.5 baseline uses ChatGPT-authored `CHATGPT-DISPATCH` requests, Dispatcher v1 `PollOnce`, Runner v1 ReviewBundle, Codex, and `LAWBRUNNER-RESULT` readback for ChatGPT review.
- The B0 bridge discipline baseline was integrated into `master` through PR #134 on 2026-06-13. Merge commit: `29381d16d438f8fcf9807f48e93544f99df9301e`.
- B0 governance and integration baseline is complete.
- Current activity is `Workflow Governance Reset`, tracked by Issue #135.
- Issue #114 is historical roadmap evidence, not the active task source.
- Bridge Operator Phase B is the approved next direction for development workflow tooling: fixed Bridge Inbox, bounded local operator, existing Dispatcher / Runner delegation, and ChatGPT-readable GitHub result readback.
- The old boundary-layer expansion and local-repair loop is frozen.
- Bridge Operator B1 remains separately approval-gated and is not yet implemented.
- Bridge Operator B1 has not been started by this task.
- Manual `PollOnce` remains the verified recovery path, not the target daily experience.
- Phase C ChatGPT App / MCP work is deferred until Phase B is stable.
- High-risk operations continue to require separate approvals.
- The next implementation decision after Governance Reset must be separately reviewed and approved.

Bridge Operator is development workflow tooling and portfolio engineering evidence. It is not the primary product runtime.

## Current Integration Sequence

1. B0 documentation reconciliation - complete.
2. Verification - complete.
3. Completed or superseded Issue cleanup - complete.
4. Integration into `master` through PR #134 - complete.
5. Workflow Governance Reset through Issue #135 - current activity.
6. Return to visible product, demo, onboarding, and portfolio value - after Governance Reset review.
7. B1 implementation - only through a separately approved task.

This task does not authorize automatic polling, bounded loop execution, login startup, tray UI, MCP, new action authority, automatic commit, push, issue close, label edit, PR creation, merge, or approval chaining.

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
- 2026-06-14: Began Workflow Governance Reset through Issue #135, clarified Issue #114 as historical roadmap evidence, and kept B1, Phase C, and high-risk operations separately approval-gated.
- 2026-06-13: Merged PR #134 into `master`, verified post-merge master state, cleaned up the merged feature branch, and returned focus to visible product value.
- 2026-06-13: Recorded B0 closeout status, completed/superseded Issue cleanup, and separate PR approval requirement for bridge discipline integration.
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.

