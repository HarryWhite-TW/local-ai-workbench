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

The current Operating V1 verdict is:

```text
CHATGPT-FIRST OPERATING V1
— ACCEPTED / PUBLISHED
```

The implementation/test package and live acceptance are distinct. The package
used fake-gh test coverage and alone did not claim live Startup acceptance.
Subsequent Windows-login evidence on exact candidate
`4f154a6aec580c5aff7d39ed4d7f88ff7e44e92f` proves the visible, bounded B3-C
path: LAWB Issue #147 status comment `5241919507` binds
session `ec9567ea59ec4d1697e39328fe48b686`, branch
`codex/ov1-live-lifecycle-acceptance`, that exact HEAD, `result=running`, 960
cycles, 30-second polling, 600-second timeout, and no blocked reasons.

The confirmed nonfatal-continuation case is specifically an otherwise valid
health probe rejected with `health_probe_expiry_exceeds_5_minutes`. LAWB Issue
#253 records the deliberate overlong marker `5241948888`, later valid dispatch
`5241971961`, and matching successful `LAWBRUNNER-RESULT` `5241982406`. The
overlong request fails closed before Dispatcher without terminating that live
polling session, which remains available for the later valid request. The result
binds the exact candidate branch/HEAD, `result=success`, clean Git state, no
changed files, and no stage, commit, push, PR, merge, Issue-close, or other
trusted-parent action. Arbitrary malformed markers, already-expired Inbox
markers, invalid expiry syntax, and other pre-dispatch failures retain their
fail-closed contracts; this current claim does not assert the same continuation
behavior for them.

The live lifecycle acceptance occurred on candidate `4f154a6...` before
publication. PR #254 then published that exact accepted candidate at merge
`0aec6941b3f48730944dbf04a7b451c6c6cbb154`; post-publication repository
identity and diff review established no candidate content drift. The live test
is not attributed to the merge commit. Existing duplicate suppression and
durable reconciliation protections remain bounded.

The earlier manual-foreground daily-UX evidence remains valid as historical
foundation, but it is no longer the current completion line. This acceptance
does not prove a hidden Windows service, production-grade availability, fully
autonomous software development, automatic permanent or high-risk GitHub
operations, MCP, Independent HGW runtime, or removal of human approval
boundaries. Permanent and high-risk authority remains explicitly approval-gated.

The earlier manual-foreground capability matrix, evidence, and limitations are
recorded in `docs/CHATGPT_FIRST_DAILY_UX_PILOT_CLOSEOUT_2026-07-31.md` as
historical foundation rather than the current Operating V1 completion record.

## Canonical Ecosystem Forward Plan

The current cross-repository sequencing, completion lines, and stop lines are
maintained in:

[`WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md`](https://github.com/HarryWhite-TW/human-governed-workflow/blob/main/docs/WORKFLOW_HAG_ECOSYSTEM_ROADMAP_v2.0.md)

The roadmap separates two completion lines whose completion chronology did not
follow the original forecast exactly:

1. `ECO-CP1 — Human-Governed AI Core Demo Checkpoint`: the first stable,
   demonstrable ecosystem stop point, whose durable closeout is not declared
   complete by the Operating V1 evidence;
2. `CHATGPT-FIRST OPERATING V1`: accepted and published through LAWB PR #254
   under a subsequent explicitly approved path, removing routine local Bridge
   startup, recovery-command, and evidence relay from normal bounded work.

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

## Fixed Path to ECO-CP1

The original fixed path remains historical sequencing. Its HAG portion is now
complete:

1. `HAG-04-SECOND-REPAIR-01` — completed;
2. `HAG-04-INDEPENDENT-FINAL-REVIEW-02` — completed;
3. `HAG-04-PUBLICATION-01` — `HAG-04 DONE / PUBLISHED`;
4. `HAG-05A-CURRENT-TRUTH-AND-CONTRACT-LOCK` — completed;
5. `HAG-05B-MINIMAL-LOCAL-SURFACE` — completed;
6. `HAG-05C-ACCEPTANCE-AND-PUBLICATION` — `HAG-05 DONE / PUBLISHED`;
7. `WORKFLOW-DISPLAY-PILOT-CLOSEOUT-01` — not declared complete here;
8. `ECO-CP1-DURABLE-CLOSEOUT-01` — not declared complete here.

The published HAG-05 implementation preserves the accepted product contract:

`HAG-05 — Minimal Local API and Approval Surface`

A CLI-only substitute would be a product-contract change. HAG-05 must not
silently add a real LLM, credentials, real GitHub mutation, production
authentication, n8n, background workers, a broad UI framework, or deployment.

The ECO-CP1 target verdict, not asserted by this synchronization, remains:

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

## Subsequent Operating V1 Completion

The original roadmap placed `CHATGPT-FIRST OPERATING V1` after ECO-CP1 as an
optional goal. Under a later, explicitly approved evidence path, Operating V1
was completed and published through LAWB PR #254 without treating the forecast
chronology as having occurred exactly as written.

The accepted readiness route selected visible login-triggered Startup and
preserved visible health/status, reversible disable, bounded restart recovery,
duplicate suppression, and separate approval for permanent or high-risk
operations. Independent HGW runtime was not required and remains inactive.

This completion does not by itself close the separate Display Pilot or ECO-CP1
durable completion lines.

## Stop Lines

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
