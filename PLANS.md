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

The accepted/published/closed #281 outcome is the current Workflow
reconciliation anchor. PR #283 published request-bound Workflow operator
visibility. The fixed normal relay and status surface remains open Issue #279.
ChatGPT remains the primary UI; manual copy/paste relay and manual `PollOnce`
remain fallback or recovery only, never the target daily workflow.

Request-bound non-terminal progress is established where the accepted #281 / PR
#283 evidence proves it. This is a Machine View capability: it makes the
request-local state and bounded operator evidence inspectable. It does not
claim continuous, end-to-end live telemetry through Dispatcher, Runner, and
Codex, and it does not claim a complete comfortable human-facing presentation.
Those deeper telemetry and Human View limitations remain explicit current gaps.

No active implementation node exists. The current priority is a comfortable,
repeatable Human-Governed Workflow daily loop, but
`WORKFLOW-COMFORTABLE-DAILY-LOOP-ACCEPTANCE-01` is not activated by this plan.
PRT items are optional reality-validation assets, not a mandatory numbered
execution queue. MCP / ChatGPT App, Desktop Agent, VM executor, service, tray,
and repository extraction remain future or separately gated work. No Product or
Workflow node activates automatically.

Roadmap tracker #168 remains outside this approved two-document reconciliation.
If its tracker wording is inconsistent with this post-#281 current truth, that
is a residual external durable-truth gap for separate review; this plan does
not silently treat it as reconciled.

## Canonical Ecosystem Forward Plan

Cross-repository completion history and separately reviewed future planning are
maintained in:

[`WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md`](https://github.com/HarryWhite-TW/human-governed-workflow/blob/main/docs/WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md)

That roadmap is not a current activation queue. It does not supersede the
post-#281 reconciliation above or grant a next node, runtime expansion, or
high-risk authority without separate review and approval.

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
- HAG-04 fake execution safety semantics are done and published;
- HAG-05 minimal local API and approval surface is done and published, with a
  fake-only loopback foreground approval surface.

## Current HAG Status

HAG-01 through HAG-05, exception-boundary stabilization, and RequestEvaluation
invariant recovery are published on HAG `main`.

- `HAG-04 DONE / PUBLISHED`;
- `HAG-05 DONE / PUBLISHED`.

The HAG-05 loopback foreground local approval surface remains fake-only. HAG
has no real credential, LLM, GitHub mutation, worker, queue, service, deployment,
or Workflow-runtime authority.

## Historical Path to ECO-CP1

The original fixed path remains historical sequencing. Its HAG portion is now
complete:

1. `HAG-04-SECOND-REPAIR-01` — completed;
2. `HAG-04-INDEPENDENT-FINAL-REVIEW-02` — completed;
3. `HAG-04-PUBLICATION-01` — `HAG-04 DONE / PUBLISHED`;
4. `HAG-05A-CURRENT-TRUTH-AND-CONTRACT-LOCK` — completed;
5. `HAG-05B-MINIMAL-LOCAL-SURFACE` — completed;
6. `HAG-05C-ACCEPTANCE-AND-PUBLICATION` — `HAG-05 DONE / PUBLISHED`;
7. `WORKFLOW-DISPLAY-PILOT-CLOSEOUT-01` — its documentation package was
   published through LAWB PR #267, Issue #264 was subsequently completed, and
   the later supervising ChatGPT source review and acceptance adjudication
   established `DONE / ACCEPTED / PUBLISHED / DURABLY CLOSED`;
8. `ECO-CP1-DURABLE-CLOSEOUT-01` — accepted and durably synchronized across
   canonical LAWB, HGW, and HAG.

The published HAG-05 implementation preserves the accepted product contract:

`HAG-05 — Minimal Local API and Approval Surface`

A CLI-only substitute would be a product-contract change. HAG-05 must not
silently add a real LLM, credentials, real GitHub mutation, production
authentication, n8n, background workers, a broad UI framework, or deployment.

The historical durable verdict is:

`ECO-CP1 ACCEPTED — STABLE STOP POINT`

It is retained as history, not as a current activation queue. The current
post-#281 state and limitations are recorded above. No later node activates
automatically.

## Historical Stop Lines

Before ECO-CP1, do not activate:

- Independent HGW runtime or N4+;
- HAG-06, HAG-07, or HAG-08;
- real LLM access, credentials, or real GitHub mutation;
- queue, isolated worktree, shadow mode, or cutover;
- n8n, hidden background service, tray, MCP, deployment, or additional startup
  authority beyond the accepted visible login-triggered path;
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

- 2026-08-13: Recorded Display Pilot package publication, the later supervising
  ChatGPT closeout adjudication, and the final canonical LAWB/HGW/HAG
  durable-truth record. That record becomes effective only after the exact
  publication commits merge and are independently read back; no next node was
  activated.
- 2026-08-13: Reconciled the Display Pilot documentation package with current
  routed-workspace, request-identity, transient-failure, lifecycle-recovery,
  runtime-realignment, Git-trust, clean live-start/stop, and ChatGPT-side
  platform-block evidence. Activated no runtime or transport work.
- 2026-08-10: Synchronized the accepted and published ChatGPT-First Operating
  V1 truth from LAWB PR #254, updated HAG-04/HAG-05 to published, preserved LAWB
  runtime ownership and approval boundaries, and left Display Pilot/ECO-CP1
  durable completion as separate unproven questions.
- 2026-08-02: Adopted Ecosystem Roadmap v2.0 candidate publication wording,
  separated ECO-CP1 from the later ChatGPT-First Operating V1 goal, updated HAG
  current truth through the paused HAG-04 second repair, preserved Local AI
  Workbench as canonical runtime owner, and activated no implementation node.
- 2026-07-31: Published the evidence-supported ChatGPT-first core daily-UX
  verdict with success and fail-closed evidence while preserving full
  Display-Ready package gaps and runtime non-claims.
- 2026-07-18: Completed Workflow v1 durable truth synchronization and preserved
  no-auto-activation for later engineering nodes.
