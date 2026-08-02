# PLANS.md

## Project Goal

Build a controlled local document-to-knowledge workbench with a single Web
entrypoint. The system is read-first and approval-gated for write-like product
actions.

## Current Product Position

Local AI Workbench is a localhost, single-user, local-first prototype and public
portfolio project for document-to-knowledge workflows. Its current product
identity includes:

- local document ingestion through a configured root folder;
- SQLite indexing for supported local documents;
- local search by title, relative path, and extracted content;
- deterministic single-document summaries;
- Obsidian-ready Markdown export after preview;
- export destination intelligence for Vault roots, Vault subfolders, normal
  Markdown folders, missing folders, and non-folder paths.

The public product mainline remains the **Local Document-to-Knowledge
Workbench**. It is not a SaaS product, background automation platform, or
chat-first product.

Phase 5.1–5.3 product-validation evidence is recorded in
`docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md` with verdict:

`PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED`

The five-minute continuous timing claim remains unproven; summary usefulness and
encoding/rendering remain bounded gaps. Phase 5.4 is not active and is not an
upper-level gate for Workflow continuation.

## Development Workflow Position

Product runtime and development-workflow tooling remain separate.

Local AI Workbench is the accepted canonical daily runtime and
rollback/reference host for the bounded ChatGPT-to-Codex engineering path. It
owns the current B3-C foreground loop, Dispatcher, Runner, Codex execution, and
GitHub status/result route. Bridge Operator remains development tooling and
portfolio engineering evidence, not the document-workbench product runtime.

Workflow v1 is:

`DONE — FINAL DURABLE TRUTH SYNCHRONIZED`

The accepted bounded daily-UX verdict is:

```text
CHATGPT-FIRST CORE DAILY UX ACCEPTED
— MANUAL FOREGROUND, BOUNDED, NO ROUTINE TASK/RESULT RELAY
```

After one reviewed local setup and one visible foreground Bridge start, the user
can work through ChatGPT without routinely relaying task packets, terminal
output, raw diffs, tests, result JSON, ReviewBundle content, or Codex reports.

This does not prove zero-touch startup, a permanent background service,
unattended restart recovery, parallel isolation, automatic remote actions, or
independent Workflow runtime cutover.

The accepted capability matrix, evidence, and limitations are recorded in
`docs/CHATGPT_FIRST_DAILY_UX_PILOT_CLOSEOUT_2026-07-31.md`.

## Canonical Ecosystem Forward Plan

The current cross-repository sequencing, completion lines, and stop lines are
maintained in:

[`WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md`](https://github.com/HarryWhite-TW/human-governed-workflow/blob/main/docs/WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md)

The roadmap separates two completion lines:

1. `ECO-CP1 — Human-Governed AI Core Demo Checkpoint`: the first stable,
   demonstrable ecosystem stop point;
2. `CHATGPT-FIRST OPERATING V1`: the later optional goal that removes routine
   local startup, recovery-command, and evidence relay from normal bounded work.

The first checkpoint no longer requires Independent HGW runtime. Local AI
Workbench remains the runtime owner unless a later readiness review proves a
safe, valuable, single-owner migration path.

## Repository Roles

### Local AI Workbench

- canonical daily engineering runtime and reference host;
- owns current Bridge, Dispatcher, Runner, Codex, and GitHub result/status path;
- remains the Local Document-to-Knowledge Workbench product repository;
- must not be duplicated by a second daily runtime.

### Human-Governed Workflow

- published pure authority, Task Surface, Result Surface, deterministic reviewer,
  and zh-TW renderer layer;
- non-executing and not cut over;
- N4+ and independent runtime work remain inactive unless separately justified.

### Human Approval Automation Gateway

- bounded human-approval product and reference target;
- does not dispatch Codex or own Workflow runtime;
- HAG-04 covers fake execution safety semantics;
- HAG-05 is the local API and approval-surface completion node.

## Current HAG Status

HAG-01, HAG-02, HAG-03, exception-boundary stabilization, and RequestEvaluation
invariant recovery are published on HAG `main`.

HAG-04 exists as a local, unstaged fake-execution and reconciliation candidate.
Independent cross-review found two production blockers even though the existing
candidate suites passed:

1. replayed execution repository can diverge from the exact authoritative
   Proposal repository;
2. two coordinators created before first dispatch can each attempt the same
   Proposal and each call an adapter.

`HAG-04-SECOND-REPAIR-01` is approved, paused, and not started. The approval is
limited to `execution.py`, `audit.py`, and `test_execution_contracts.py`. It does
not authorize publication, HAG-05, credentials, real GitHub mutation, or broader
runtime authority.

## Fixed Path to ECO-CP1

1. `HAG-04-SECOND-REPAIR-01`;
2. `HAG-04-INDEPENDENT-FINAL-REVIEW-02`;
3. `HAG-04-PUBLICATION-01`;
4. `HAG-05A-CURRENT-TRUTH-AND-CONTRACT-LOCK`;
5. `HAG-05B-MINIMAL-LOCAL-SURFACE`;
6. `HAG-05C-ACCEPTANCE-AND-PUBLICATION`;
7. `WORKFLOW-DISPLAY-PILOT-CLOSEOUT-01`;
8. `ECO-CP1-DURABLE-CLOSEOUT-01`.

HAG-05 must preserve the accepted product contract:

`HAG-05 — Minimal Local API and Approval Surface`

A CLI-only substitute would be a product-contract change. HAG-05 must not
silently add a real LLM, credentials, real GitHub mutation, production
authentication, n8n, background workers, a broad UI framework, or deployment.

ECO-CP1 completes with:

`ECO-CP1 ACCEPTED — STABLE STOP POINT`

Then stop. No later node activates automatically.

## Display Pilot Closeout

The ChatGPT-first core daily UX is accepted, but the full Display-Ready package
remains open. Its remaining bounded outputs are:

- reference-host setup and verification guide;
- deterministic sample reviewer and plain-language reports from canonical
  evidence;
- success and fail-closed evidence map;
- limitations and recovery guide;
- concise interview/demo guide;
- final public-claim consistency review.

This is documentation and presentation work only. It does not add runtime,
adapters, queueing, credentials, startup, service behavior, or cutover.

## Post-ECO Optional Goal

Only after ECO-CP1 and a fresh user decision may the project evaluate
`CHATGPT-FIRST OPERATING V1`.

The readiness review must choose the smallest route among:

- keep manual foreground operation;
- add login-triggered startup;
- add a narrow persistent launcher;
- stop because of a host or platform limitation.

Any approved implementation must preserve visible health/status, reversible
disable, bounded restart recovery, duplicate suppression, and separate approval
for permanent or high-risk operations. Independent HGW runtime is not assumed to
be necessary.

## Stop Lines

Before ECO-CP1, do not activate:

- Independent HGW runtime or N4+;
- HAG-06, HAG-07, or HAG-08;
- real LLM access, credentials, or real GitHub mutation;
- queue, isolated worktree, shadow mode, or cutover;
- n8n, background service, startup, tray, MCP, or deployment;
- automatic commit, push, PR, merge, Issue close, or approval chaining.

After ECO-CP1, pause by default and choose at most one separately approved next
phase. Roadmap ordering never grants authority.

## Current Governance and Evidence Pointers

- Repository governance: `AGENTS.md`;
- Bridge-specific governance: `src/local_runner_bridge/AGENTS.md`;
- acceptance integrity: `docs/WORKFLOW_ACCEPTANCE_INTEGRITY_PROTOCOL.md`;
- engineering record navigation: `docs/ENGINEERING_RECORDS_INDEX.md`;
- active Bridge execution governance:
  `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md`;
- Direction Lock: `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`;
- Bridge Operator specification: `docs/BRIDGE_OPERATOR_V0_SPEC.md`;
- ecosystem strategy: `docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md`;
- native-capability overlap review:
  `docs/WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md`.

Historical Issues, PRs, dated closeouts, manifests, and the prior detailed change
log remain durable evidence in GitHub, the engineering-record index, and Git
history. They are not a competing current forward plan.

## Historical M1 Baseline

The original M1 baseline remains historical:

- minimal Web and Python API skeletons;
- SQLite persistence;
- fake preview, approve, and audit flow;
- no real Gmail, Calendar, LLM, or file-writing integration.

Its historical status does not activate product or Workflow work.

## Change Log

- 2026-08-02: Adopted Ecosystem Roadmap v2.0 candidate publication wording,
  separated ECO-CP1 from the later ChatGPT-First Operating V1 goal, updated HAG
  current truth through the paused HAG-04 second repair, preserved Local AI
  Workbench as canonical runtime owner, and activated no implementation node.
- 2026-07-31: Published the evidence-supported ChatGPT-first core daily-UX
  verdict with success and fail-closed evidence while preserving full
  Display-Ready package gaps and runtime non-claims.
- 2026-07-18: Completed Workflow v1 durable truth synchronization and preserved
  no-auto-activation for later engineering nodes.
