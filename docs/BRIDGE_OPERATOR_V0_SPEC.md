# Bridge Operator v0 Specification

## Document Identity

- title: Bridge Operator v0 Specification
- version: v0.1
- status: Active Design Baseline
- owner: 駿弘
- repository: `HarryWhite-TW/local-ai-workbench`
- scope: Near-zero-touch ChatGPT-to-Codex development workflow tooling
- product boundary: Development workflow tooling only; not Local Document-to-Knowledge Workbench runtime

## Decision Lock

The approved direction is:

1. **Phase B first:** build a bounded local Bridge Operator that keeps ChatGPT as the user's primary interface and GitHub as the auditable task/result surface.
2. **Phase C later:** after Phase B is stable, evaluate a ChatGPT App / MCP connector to reduce the remaining bridge trigger gap.
3. **Do not build a replacement local chat product.** A separate OpenAI API chat UI is not the current direction.
4. **Keep manual PollOnce as recovery only.** It is not the target daily workflow.

This specification is subordinate to `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md` and must not weaken its approval or safety boundaries.

## Primary User Experience Goal

The intended daily workflow is:

```text
User talks to ChatGPT
-> ChatGPT creates or updates an explicit GitHub task and dispatch request
-> local Bridge Operator detects one eligible request automatically
-> Bridge Operator delegates to the existing Dispatcher / Runner path
-> Codex performs one bounded task
-> result is written back to GitHub
-> ChatGPT reads and reviews the result
-> user makes only key direction and high-risk approval decisions
```

The user should not need to:

- copy long ChatGPT prompts into Codex;
- copy long Codex reports back into ChatGPT;
- manually run `PollOnce` for every normal task;
- use a second required chat interface;
- manually search GitHub for the next executable request.

The local operator may expose status, pause, resume, stop, logs, and recovery controls. It must not become a second conversational interface.

## Current Baseline

The current verified Lv4.5 baseline already provides:

- `CHATGPT-DISPATCH protocol=lawb.dispatch.v1`;
- `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`;
- explicit issue-scoped `PollOnce`;
- `maybe-status-check`;
- `run-reviewbundle` delegation to Runner v1;
- bounded Codex execution through the Windows npm `codex.cmd` launcher;
- GitHub CLI resolution through PATH, Program Files, or a portable user tools path;
- GitHub result comment writeback;
- ChatGPT-readable result review;
- separate approval rails for commit, push, close, labels, PRs, merges, and approval-consuming operations.

Manual recovery command:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Architecture Decision

### Phase B: Local Bridge Operator

Build `Bridge Operator v0` as a visible, bounded local process on the user-designated Primary Operational Host.

Core flow:

```text
ChatGPT
-> fixed GitHub Bridge Inbox
-> local Bridge Operator
-> explicit target Issue
-> local_dispatcher_v1.ps1 PollOnce
-> local_runner_v1.ps1 ReviewBundle when allowed
-> Codex
-> LAWBRUNNER-RESULT on the target Issue
-> ChatGPT review
```

### Fixed Bridge Inbox

The default control surface is one dedicated GitHub Issue in this repository.

The exact Issue number may be assigned during implementation, but the operator must be configured with one fixed inbox identity and must not broadly scan open issues.

A Bridge Inbox request must reference exactly one explicit target Issue and one explicit dispatch request. The target Issue remains the authority for its current `CHATGPT-DISPATCH` marker and execution binding.

The inbox is a wake-up/control surface, not an approval surface.

### Existing Dispatcher Reuse

The operator must not reimplement Dispatcher policy.

For an accepted request it delegates to:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

The Dispatcher remains responsible for validating:

- repository identity;
- explicit target Issue;
- target Issue is `OPEN` immediately before delegation;
- exactly one current dispatch marker;
- target `CHATGPT-DISPATCH` marker comment author is trusted;
- protocol and action allowlist;
- branch and HEAD binding;
- expiry;
- `requested_by=chatgpt`;
- request identity;
- clean-repository requirements for `run-reviewbundle`;
- result comment publication.

## Allowed Operator Authority

Bridge Operator v0 may automatically:

- poll one fixed Bridge Inbox;
- read one explicit request at a time;
- validate request shape before delegation;
- resolve one explicit target Issue;
- check local readiness;
- invoke the existing Dispatcher `PollOnce` path;
- allow the Dispatcher to execute `maybe-status-check`;
- allow the Dispatcher to execute `run-reviewbundle` only after its existing clean-repo checks;
- record local heartbeat, lock, processed-request, and diagnostic logs;
- pause after bounded failure;
- expose local status and recovery controls.

Bridge Operator v0 must never automatically:

- stage files;
- create commits;
- push refs;
- close issues;
- add or remove labels;
- create or merge PRs;
- force push;
- consume approval markers;
- chain approval-gated actions;
- stash, reset, clean, or repair a dirty repository;
- infer a target Issue from latest/next/open issue ordering;
- scan broad issue ranges;
- modify the Local Document-to-Knowledge Workbench product runtime.

## Safety Model

### Fixed Scope

- fixed repository: `HarryWhite-TW/local-ai-workbench`;
- fixed Bridge Inbox;
- one explicit target Issue per request;
- one task executing at a time;
- one allowlisted action per dispatch;
- no cross-repository execution in v0.

### State Binding

Each executable request must remain bound to:

- `request_id`;
- repository;
- target Issue;
- branch;
- exact expected HEAD;
- expiry;
- requested action.

The operator must recheck expiry and local state immediately before delegation.

### Trusted Request Origin

Bridge Operator v0 and the existing Dispatcher path must treat GitHub author
metadata as the identity source of truth.

- the fixed Bridge Inbox request author must be in the configured trusted
  GitHub actor allowlist;
- the target `CHATGPT-DISPATCH` marker comment author must be in the same
  trusted GitHub actor allowlist;
- the initial default trusted actor is `HarryWhite-TW`;
- the dispatch marker field `requested_by` must equal `chatgpt`;
- the target Issue must be `OPEN` immediately before delegation;
- a closed Issue, untrusted author, or `requested_by` mismatch fails closed;
- author display text inside the marker is not identity evidence. GitHub
  comment metadata is authoritative.

### Idempotency

- processed `request_id` values must be stored durably outside the repository working tree;
- a processed request must not execute again;
- an in-progress lock must prevent concurrent execution;
- stale locks must not be silently removed without an explicit recovery rule;
- duplicate or ambiguous requests fail closed.

### Local Runtime State

Preferred local state location:

```text
%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator\
```

Suggested contents:

```text
state.json
processed_requests.jsonl
operator.lock
heartbeat.json
operator.log
last_failure.json
pause.flag
stop.flag
```

Runtime state must not dirty the Git repository.

### Retry Policy

- no infinite retries;
- network/auth read failures may use a small bounded retry count;
- execution failures must not automatically rerun Codex;
- Codex quota exhaustion, missing launcher, dirty repo, wrong HEAD, expired marker, or malformed request must pause/block the request;
- after retry exhaustion the operator records a reviewable failure and returns to a safe paused or waiting state according to the failure class.

### Visibility And Emergency Control

The initial operator must remain visible as a foreground console or tray process.

Required controls:

- running;
- paused;
- blocked;
- executing;
- failed;
- resume;
- pause;
- stop;
- open logs;
- documented process-kill recovery.

A hidden Windows service is out of scope for v0.

## Failure Model

The operator must fail closed for:

- missing or expired GitHub authentication;
- network loss after bounded retry;
- malformed or duplicate inbox request;
- untrusted Bridge Inbox request author;
- missing target Issue;
- closed target Issue;
- missing or duplicate target dispatch marker;
- untrusted target dispatch marker author;
- target dispatch marker `requested_by` mismatch;
- wrong repository, branch, or HEAD;
- unsupported action;
- dirty repository where clean state is required;
- missing Dispatcher or Runner script;
- missing GitHub CLI;
- missing or unusable Codex launcher;
- Codex quota or provider failure;
- active task lock;
- corrupted local state;
- unexpected partial execution.

The operator must never hide partial failure. Logs must state whether Dispatcher, Runner, Codex, or GitHub result publication was reached.

## Windows Deployment Model

### Primary Operational Host

The Primary Operational Host is the Windows computer explicitly designated by the user for current normal Bridge operation and operational acceptance.

The current Primary Operational Host is the course Windows computer. The home Windows computer is a Secondary Compatibility Host and may provide optional cross-host evidence without blocking RV2-03 completion.

Designation is not an operational-readiness claim and does not grant startup, request-publication, execution, retry, or other authority.

Initial deployment order:

1. manual foreground launch;
2. bounded-loop foreground smoke;
3. visible tray wrapper if useful;
4. separate user approval for Windows login startup;
5. no Windows service in v0.

Automatic startup must not be enabled until the operator has passed dry-run, one-shot, bounded-loop, pause/stop, restart, auth-loss, network-loss, dirty-repo, and duplicate-request smokes.

### Current Course-Computer Primary Host

The restore-card course Windows computer is the current Primary Operational Host. It remains an ephemeral environment and must be treated as untrusted after every reset, restore, or machine handoff.

Do not assume persistent:

- authentication;
- installed Codex;
- portable GitHub CLI path;
- Python environment;
- startup task;
- local operator state;
- logs.

Before live B3 operation after a reset, environment recovery, authentication, executable resolution, repository identity, branch, HEAD, clean-tree state, and operator-state continuity must be revalidated.

Loss or absence of local operator state must never be treated as evidence that a request has not run. Before delegation, the operator must reconcile trusted durable completion evidence or fail closed when prior execution cannot be ruled out. Cross-reset duplicate suppression remains unproven until it is separately implemented, tested, and accepted.

Manual `PollOnce` remains a recovery path and requires its existing separate authority.

### Secondary Compatibility Host

The home Windows computer is the current Secondary Compatibility Host. It may retain authentication, tools, logs, and operator state more reliably, but evidence from that host is supplementary and does not block RV2-03 completion.

## Phase C: ChatGPT App / MCP

Phase C is optional and begins only after Phase B is stable.

Goal:

```text
ChatGPT
-> approved ChatGPT App / MCP tool call
-> local Bridge service
-> existing Dispatcher / Runner contract
-> GitHub result and ChatGPT review
```

Phase C must preserve:

- explicit target Issue;
- branch/HEAD/expiry binding;
- one-task scope;
- current Dispatcher policy;
- no automatic high-risk continuation;
- local pause/stop controls;
- auditable GitHub result surfaces.

Phase C must not bypass GitHub auditability or convert ChatGPT tool invocation into commit/push/close approval.

## Explicitly Rejected Direction

Do not build a separate local OpenAI API chat application as the primary interface in the current roadmap.

Reasons:

- duplicates ChatGPT conversation and project context;
- creates a second review surface;
- requires separate API billing and lifecycle management;
- risks turning workflow tooling into a new product scope;
- weakens the user-only-interfaces-with-ChatGPT goal.

## Implementation Phases

### Phase B0 — Specification And Documentation

- adopt this specification;
- bind future operator work to this file and the Direction Lock;
- reconcile README, PLANS, SOP, and architecture language;
- no operator code yet.

### Phase B1 — Inbox Read-Only Dry Run

- read one fixed Bridge Inbox;
- parse one explicit request;
- validate fixed Bridge Inbox request author against the trusted actor allowlist;
- resolve one target Issue;
- validate request and local readiness;
- emit local dry-run evidence;
- do not invoke Dispatcher.

### Phase B2 — One-Shot Delegation

- process one request and stop;
- recheck target Issue is open, trusted marker author, and `requested_by=chatgpt`
  immediately before delegation;
- invoke existing Dispatcher PollOnce;
- prove `maybe-status-check` first;
- then prove `run-reviewbundle`;
- verify one result and no high-risk side effects.

### Phase B3 — Foreground Bounded Loop

- poll only the fixed Inbox;
- one task at a time;
- durable idempotency;
- lock, heartbeat, pause, stop, logs;
- bounded retry;
- no login startup yet.

### Phase B4 — Visible Operator UX

- optional tray wrapper or small status panel;
- no chat interface;
- show state, current request, last result, pause, resume, stop, and logs.

### Phase B5 — Login Startup

Requires a separate explicit user approval after all prior acceptance tests pass.

Preferred initial mechanism: Startup folder or Task Scheduler with visible user-session execution. Do not use a hidden Windows service in v0.

### Phase C — MCP Feasibility And Integration

- separate feasibility probe;
- explicit security review;
- no implementation until Phase B is stable and accepted.

## Acceptance Criteria

Phase B is considered operational only when all of the following are proven:

- user can remain in ChatGPT for normal task creation and result review;
- operator detects one fixed-inbox request without manual PollOnce;
- one explicit target Issue is processed;
- Bridge Inbox and target dispatch marker authors are trusted by GitHub comment
  metadata;
- closed target Issues fail closed before delegation;
- `requested_by` mismatch fails closed before delegation;
- duplicate `request_id` does not rerun;
- malformed, expired, wrong-HEAD, dirty-repo, auth-loss, and network-loss cases fail closed;
- `maybe-status-check` succeeds end to end;
- `run-reviewbundle` succeeds end to end;
- Codex failure remains reviewable and does not retry indefinitely;
- no stage, commit, push, close, label, PR, merge, approval consumption, or approval chaining occurs;
- manual PollOnce recovery remains documented and working;
- local state and logs do not dirty the repository;
- pause, stop, restart, and stale-lock recovery are documented and tested.

## Documentation And Conversation Binding

For every future conversation or Codex task that changes Bridge Operator behavior, architecture, deployment, polling, startup, Inbox semantics, authority, or Phase C integration:

1. read `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`;
2. read `docs/BRIDGE_OPERATOR_V0_SPEC.md`;
3. classify the task as `core`, `support`, `fallback`, or `drift_detected`;
4. state the current implementation phase;
5. identify whether the task changes authority or only usability/reliability;
6. stop for user approval before expanding polling scope, startup behavior, action allowlists, write authority, or external connectivity.

Required audit block:

```text
BRIDGE-OPERATOR-SPEC-READ-AUDIT protocol=lawb.bridge_operator_spec_read.v1
spec_path=docs/BRIDGE_OPERATOR_V0_SPEC.md
spec_version=v0.1
spec_read=<true|false>
current_phase=<B0|B1|B2|B3|B4|B5|C>
task_alignment=<core|support|fallback|drift_detected>
authority_change_requested=<true|false>
chatgpt_remains_primary_interface=<true|false>
manual_pollonce_is_recovery_only=<true|false>
high_risk_actions_remain_separate=<true|false>
failure_reason=<none or exact reason>
```

## Change Control

This specification may be changed only through explicit user approval.

The following changes always require a separate decision:

- enabling automatic polling;
- choosing or changing the fixed Bridge Inbox;
- enabling `run-reviewbundle` in the operator;
- enabling a bounded loop;
- enabling login startup;
- adding a tray or local status UI;
- adding MCP or another remote connector;
- changing the action allowlist;
- adding any write or approval authority;
- changing the primary host model;
- replacing GitHub as the audit surface;
- replacing ChatGPT as the primary user interface;
- adding another trusted bot, app, or user to the actor allowlist.

Changing the trusted actor allowlist is an authority and trust-boundary change.
It requires separate explicit approval.
