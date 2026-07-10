# Bridge Roadmap v2 Execution Specification

## Document Identity

- title: Bridge Roadmap v2 Execution Specification
- version: v1.0
- status: Active Execution Baseline
- owner: 駿弘
- repository: `HarryWhite-TW/local-ai-workbench`
- canonical_ref: `master`
- activation_pr: `#167`
- activation_commit: `9baf606197bbdf886b23782d1c67f2a872e76e09`
- scope: Execution governance for the ChatGPT-centered local Codex bridge roadmap after B4-D preparation

## Governing Documents And Precedence

This specification is subordinate to:

1. `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`
2. `docs/BRIDGE_OPERATOR_V0_SPEC.md`

The precedence order is:

```text
CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md
-> BRIDGE_OPERATOR_V0_SPEC.md
-> BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md
-> active Roadmap v2 tracker Issue
-> one active node Issue
-> bounded Codex task packet
```

A lower-level artifact must not expand authority, weaken an approval boundary, replace ChatGPT as the primary interface, or redefine the public product runtime.

This specification became active after explicit approval and squash merge through PR #167 at commit `9baf606197bbdf886b23782d1c67f2a872e76e09`. Its activation does not by itself authorize live smoke execution, automatic polling, startup, MCP, or any high-risk action.

## Strategic Goals

### Bridge workflow goal

Establish a small, auditable, local-first bridge in which:

```text
User
-> ChatGPT plans, scopes, reviews, and requests key approvals
-> GitHub stores explicit task and result records
-> Bridge Operator validates and delegates one bounded request
-> Dispatcher and Runner preserve existing policy boundaries
-> local Codex performs one constrained engineering task
-> structured evidence returns to GitHub
-> ChatGPT reads back and reviews the result
```

The user should normally make only key direction and high-risk approval decisions through ChatGPT. Manual copy and paste and manual Dispatcher `PollOnce` remain recovery paths, not the target daily workflow.

### Product-mainline goal

The public product mainline remains the Local Document-to-Knowledge Workbench. Bridge Operator, Dispatcher, Runner, Task Packet, execution-manifest, CLI facade, and MCP work are development workflow tooling and portfolio engineering evidence. They must not be presented as autonomous product-runtime features unless the user explicitly changes the product direction.

### Engineering-evidence goal

The roadmap should demonstrate:

- contract-first task definition;
- explicit authority and approval boundaries;
- fixed-scope and fail-closed validation;
- exact branch, HEAD, target, request, and expiry binding;
- local Windows reliability and recovery;
- runtime scope enforcement;
- structured result and readback evidence;
- bounded AI-assisted engineering rather than uncontrolled autonomy.

## Non-Goals

Roadmap v2 does not authorize or target:

- a general-purpose autonomous agent platform;
- a second required chat interface;
- broad GitHub Issue scanning or latest/next target inference;
- hidden unattended services in Bridge Operator v0;
- automatic commit, push, Issue close, label change, PR creation, merge, force push, or branch deletion;
- approval consumption or approval chaining;
- automatic repair loops or unbounded retries;
- early multi-user, RBAC, SSO, or enterprise productization;
- replacement of GitHub audit surfaces without separate approval;
- replacing the Local Document-to-Knowledge Workbench product mainline with bridge tooling.

## Execution Principles

1. **One active execution node:** only one Roadmap v2 execution node may be `ACTIVE` at a time. A parallel product checkpoint may exist, but it must not share or silently expand bridge authority.
2. **No automatic phase continuation:** completing, merging, or closing one artifact does not automatically authorize the next node.
3. **Evidence before expansion:** prove the existing production path before adding a facade, UX, startup, or external connector.
4. **Policy reuse:** facade and adapter layers must delegate to existing Bridge Operator, Dispatcher, and Runner policy rather than reimplementing it.
5. **Runtime binding:** task limits must eventually bind the actual Runner/Codex execution and post-execution diff, not remain validator-only documentation.
6. **Fail closed:** malformed, ambiguous, expired, mismatched, duplicate, untrusted, dirty, unsupported, or partially executed work must not be treated as success.
7. **Product investment limit:** bridge work must be justified by measurable reduction of risk, manual relay, or operational friction. It must not indefinitely displace product-facing work.

## GitHub Governance Model

Roadmap v2 uses:

- one versioned specification in the repository;
- one long-lived Roadmap v2 tracker Issue;
- one active execution-node Issue at a time;
- PRs for repository changes;
- explicit post-merge verification and node closeout.

The initial implementation does not depend on GitHub Projects, milestones, or labels. Labels may be introduced only through a separate approved governance change.

### Tracker Issue

After this specification is merged, create one tracker titled:

```text
Bridge Roadmap v2 Execution Tracker
```

It records:

- specification version and canonical path;
- current active node;
- completed, planned, blocked, superseded, and cancelled nodes;
- latest accepted evidence;
- pending authority decisions;
- product-mainline checkpoint status.

The tracker remains open until Roadmap v2 is completed or superseded.

### Active-node Issue

A node Issue must contain:

- Node ID and status;
- governing specification and tracker references;
- dependencies and entry criteria;
- background and objective;
- allowed scope and files;
- forbidden operations;
- verification commands;
- acceptance criteria;
- required evidence;
- approval gates;
- close rule;
- next-node candidate.

Creation of a node Issue records planned work. It does not itself authorize live execution, GitHub writes beyond its explicitly approved setup, merge, branch deletion, startup, polling, MCP, or other high-risk behavior.

## Node Status Model

A Roadmap v2 node uses one status in its Issue body:

```text
PLANNED
READY
ACTIVE
REVIEW
BLOCKED
DONE
SUPERSEDED
CANCELLED
```

Normal progression:

```text
PLANNED -> READY -> ACTIVE -> REVIEW -> DONE
```

Rules:

- `READY` means entry criteria are proven, not merely expected.
- `ACTIVE` requires explicit user approval for the bounded node task.
- `REVIEW` means implementation or execution evidence is available but closeout is incomplete.
- `DONE` requires all completion and close rules to pass.
- `BLOCKED` must include an exact blocker and may not silently fall back to a broader or weaker task.
- `SUPERSEDED` and `CANCELLED` require a recorded reason and tracker update.

## Node Lifecycle And Close Rule

For each execution node:

1. Read governing documents, tracker, and active node.
2. Emit the required read audits.
3. Verify entry criteria with current evidence.
4. Request separate approval for any authority-changing or live action.
5. Execute only the bounded scope.
6. Review Codex, test, PR, and runtime evidence.
7. Merge only after separate explicit merge approval.
8. Perform post-merge verification when repository changes are involved.
9. Update the tracker and node closeout.
10. Close the node only after all acceptance criteria pass.
11. Evaluate the next node's entry criteria before creating or activating it.

The following are not equivalent:

```text
Codex reports completion != implementation accepted
PR opened != PR approved
PR merged != node completed
Issue closed != technical success
```

A node closes only when:

- its acceptance criteria pass;
- required tests or runtime checks are recorded;
- ChatGPT has reviewed the evidence;
- required PRs are merged;
- post-merge verification is complete;
- tracker and durable documentation are synchronized;
- no hidden residual task is required for the node's stated objective.

## Approval And Authority Rules

The following always require separate explicit approval when applicable:

- live B4-D or other real execution;
- publishing dispatch or Inbox request markers;
- enabling automatic polling;
- enabling `run-reviewbundle` in a new authority path;
- bounded-loop activation beyond an already approved test;
- commit and push;
- PR creation;
- merge;
- Issue close when not already included in a narrowly approved closeout action;
- label changes;
- branch deletion;
- login startup;
- tray or local status UX when it changes deployment or control behavior;
- MCP or another remote connector;
- action allowlist changes;
- trusted-actor changes;
- new write or approval authority.

Approval for one action must not be interpreted as approval for later actions. In particular:

- request publication does not authorize execution;
- execution does not authorize retry;
- Codex changes do not authorize commit or push;
- PR creation does not authorize merge;
- merge does not authorize branch deletion;
- Phase B acceptance does not authorize startup or Phase C.

## Evidence Contract

Every node closeout must preserve, as applicable:

- repository and target identity;
- base and head branch;
- exact expected and actual HEAD;
- request, packet, manifest, and result identities;
- changed-file list;
- verification commands and results;
- relevant Issue and PR references;
- Codex or execution exit status;
- current limitations and unresolved risks;
- safety assertions for prohibited actions;
- post-merge state;
- next recommended action.

Raw local evidence may remain local when it includes environment-specific detail, but durable conclusions and canonical references must be preserved in GitHub or repository documentation.

## Roadmap Nodes

### RV2-00 — Specification Adoption And Execution Baseline

Objective:

- adopt this specification through a documentation-only PR;
- bind the Direction Lock and planning documents to Roadmap v2;
- establish the future tracker and node-management rules.

Current status: `DONE`.

Acceptance:

- this file is merged to `master`;
- Direction Lock references it and requires its read audit for Roadmap v2 work;
- `PLANS.md` reflects the current post-B3 and B4-D-preparation state;
- no production code, test, Runner, Dispatcher, product runtime, polling, live smoke, tracker, or node Issue is changed before merge;
- post-merge verification confirms canonical content.

After acceptance:

- create the tracker;
- record `RV2-00` as `DONE`;
- create `RV2-01` as the only active-node candidate.

### RV2-01 — B4-D Supervised Live Smoke

Objective:

Prove one fresh-reboot, foreground-only, explicitly approved `run-reviewbundle` path through the existing production chain on the course computer.

Current status: `DONE`.

Required path:

```text
ChatGPT
-> Bridge Inbox Issue #147
-> Bridge Operator one-shot delegation
-> Dispatcher PollOnce
-> Runner v1 ReviewBundle
-> Codex
-> target-Issue review bundle and LAWBRUNNER-RESULT
-> ChatGPT readback
```

Boundaries:

- use the existing merged production path;
- do not add the `lawb` facade, execution-manifest runtime binding, startup, tray, service, MCP, retry, repair, or new authority as part of this node;
- use separate request-publication and execution approvals;
- perform no commit, push, close, label, PR, merge, or branch deletion as part of the smoke.

Acceptance:

- exact repository, `master`, HEAD, target, action, request IDs, expiry, and manifest hash are bound;
- preflight and diagnostics satisfy the B4-D plan;
- exactly one approved execution occurs;
- exactly one matching trusted result is read back;
- no retry or prohibited side effect occurs;
- success or failure is unambiguous and reviewable.

Accepted outcome:

- one supervised `run-reviewbundle` smoke succeeded on clean `master` at full HEAD `f41172b1ab25b2f4db4408f2fa825deb6e754cbb`;
- manifest SHA-256 was `34d17e23f94f939765b5ed761d34aa1b3ec018e31f868857431c02314e9bf080`;
- dispatch comment `4795080463`, Inbox comment `4795082149`, Runner review-bundle comment `4795131449`, and matching `LAWBRUNNER-RESULT` comment `4795131543` preserve the evidence;
- exactly one B2/Dispatcher/Runner/Codex chain ran;
- result was success, Codex exit code was `0`, no retry occurred, no files changed, and the worktree remained clean;
- the result does not establish daily B3 operational acceptance.

### RV2-02 — B4-D Closeout And Documentation Truth Sync

Objective:

- record B4-D outcome and limitations;
- reconcile README, PLANS, runbooks, and current-status language with the actual merged B2/B3/B4-D state;
- remove stale statements such as B2 not started or the permanent Inbox not selected when those statements are no longer true.

Acceptance:

- public and governing documentation agree on current capabilities and limits;
- B4-D evidence and failure/success conclusion are recorded;
- no new runtime authority is introduced;
- next-node entry requirements are explicit.

This node also records the approved design direction for eventual repository separation. The bridge is intended to become reusable cross-project development infrastructure, with `local-ai-workbench` as its first validated reference host. This node authorizes documentation and design only. Physical extraction, a new repository, file movement, package publishing, import rewiring, runtime-boundary changes, or activation of another node require separate approval.

### RV2-03 — B3 Operational Acceptance

Objective:

Prove that the existing B3 foreground bounded loop can serve as a safe daily foreground operator on the user-designated Primary Operational Host without requiring manual `PollOnce` for every normal task. The current designated host is the course Windows computer; the home Windows computer is a Secondary Compatibility Host.

Required acceptance cases:

- one normal request succeeds;
- duplicate request does not rerun;
- wrong HEAD, dirty repo, expired request, closed target, and untrusted or mismatched data fail closed;
- pause and stop work;
- restart preserves reviewable state;
- active and stale lock recovery is documented and tested;
- Dispatcher or Codex failure does not cause an automatic execution retry;
- local state and logs do not dirty the repository;
- manual `PollOnce` remains a working recovery path;
- the explicitly designated Primary Operational Host passes the applicable environment, fresh-shell, reset, recovery, and readiness checks;
- when that host may lose local operator state, reset or state loss does not cause an already completed request to rerun;
- if trusted durable completion evidence cannot be reconciled after state loss, delegation fails closed;
- optional compatibility evidence from the home Windows computer does not block RV2-03 completion.

These are the historical acceptance requirements for RV2-03. They remain the contract that was required; they are not a statement that the acceptance is still pending.

High-priority future defect acceptance requirements:

- request lifecycle handling must immediately transition a successfully completed request to explicit `CONSUMED` state;
- expiry must remain a failure-safe fallback invalidation boundary, not the lock lifetime for a successfully completed request;
- publication of a new request must require `current_request_count = 0`;
- one-shot execution requests must use a short execution TTL;
- current-marker telemetry must expose comment ID, request ID, expiry, and the evaluator's current UTC time;
- Windows tool resolution must pass acceptance in a new shell and after a fresh reboot, not only in a shell whose `PATH` was manually repaired;
- before B2 delegation, preflight must validate that the runtime resolver can actually resolve and execute the configured tools.

#### Current Status And Accepted Outcome

RV2-03 is `DONE`. Formal Primary Operational Host acceptance passed on the course Windows computer on 2026-07-10 at `master@180d966e46194c0cd0d542d90376c52e84dda05b`, using manifest SHA-256 `50d7a481987c16e052e47d635d338c16afdf5a117ed48a2c513733e28382078c`.

The accepted request identities are Inbox `rv2-03-final-primary-inbox-20260710T044049Z-1b1bd31e` and dispatch `rv2-03-final-primary-dispatch-20260710T044049Z-1b1bd31e`. Durable evidence is dispatch marker `4932081797`, Inbox marker `4932081856`, Runner review bundle `4932108053`, and trusted matching success result `4932108148`.

The normal request succeeded exactly once: one Dispatcher, one Runner, one Codex execution, one trusted matching success, and one local `CONSUMED` record. Complete local operator-state loss did not rerun the request. Durable `COMPLETED` reconciliation reconstructed one `CONSUMED` record without Dispatcher, Runner, or Codex rerun, and the later local duplicate gate prevented another execution. No automatic retry or unexpected GitHub write occurred, and the repository remained clean.

RV2-03 completion does not automatically authorize or activate RV2-04. RV2-04 remains a future candidate. This closeout authorizes no startup, tray, service, MCP, automatic Git/GitHub mutation, trusted-actor expansion, allowlist expansion, or approval chaining.

### RV2-04 — Runtime Contract Binding

Objective:

Convert Task Packet v1.1 limits from validator-only discipline into a traceable execution contract enforced before and after Runner/Codex execution.

Target flow:

```text
Task Packet v1.1
-> validated execution manifest
-> bounded Runner/Codex input
-> post-execution diff and verification validation
-> structured result
```

Minimum bindings:

- task mode;
- objective;
- allowed files;
- maximum allowed-file count;
- context scope;
- verification command policy and explicit commands;
- repair-attempt limit;
- `scope_expansion_allowed=false`;
- repository, branch, HEAD, target, and request identity.

High-priority future defect contract requirements:

- the versioned Host Profile contract must carry reviewed executable paths for `gh`/`gh.exe` and Codex;
- bootstrap and runtime must use one shared tool-resolution contract;
- `manifest_review_expires` and `execution_request_expires` must be distinct fields with distinct semantics;
- B1 and B2 must emit a safe, stage-specific diagnostic schema rather than only `github_read_unavailable` or a generic `RuntimeError`;
- Runner evidence must propagate consistently to the outer result, including `changed_files`, `review_id`, `diff_fingerprint`, and `files_fingerprint`.

These are future RV2-04 contract requirements only. This specification update does not mark RV2-04 active, ready, started, or done, and does not claim that any requirement is implemented.

Pre-execution enforcement:

- schema and identity validation;
- clean repository when required;
- safe allowed paths;
- supported execution profile;
- valid explicit verification commands;
- no unauthorized scope expansion.

Post-execution enforcement:

- actual changed files remain inside the allowlist;
- changed-file count remains within the limit;
- no forbidden path is touched;
- verification outcome is structured;
- a claimed Codex success does not override an execution-contract violation.

This node must preserve existing Dispatcher and Runner authority boundaries and must not add commit, push, merge, retry, repair-loop, or approval-chaining authority.

### RV2-05 — Minimal `lawb` CLI Facade

Objective:

Provide a thin, stable, JSON-first command facade over proven components without reimplementing policy.

Initial command model:

```text
lawb preflight
lawb status
lawb task validate
lawb task compile
lawb operator run
lawb readback
```

Requirements:

- each command emits a documented structured summary;
- the facade delegates to existing validators, Bridge Operator, Dispatcher, and Runner contracts;
- blocked reasons identify the layer reached;
- secrets are not stored by the facade;
- removal of the facade does not break the underlying production path;
- the facade itself does not acquire new execution or approval authority.

A generic ambiguous `lawb exec` command is deferred until its authority and delegation semantics can be made explicit.

### RV2-06 — Execution Profiles And Token Control

Objective:

Reduce unnecessary context, output, and scope expansion without lowering correctness or reviewability.

Candidate profiles:

- `status-only`;
- `verify-only`;
- `docs-only`;
- `lean-patch`.

Profile controls may include:

- context-scope limits;
- allowed-file limits;
- verification-command limits;
- repair-attempt limits;
- output schema;
- verbosity policy;
- model-policy resolution.

Rules:

- model names and provider capabilities must not be permanently assumed without current verification;
- numeric limits such as turns or file counts must be validated empirically per profile rather than imposed as universal constants;
- token reduction is not success if it increases rework, scope violations, or unverifiable output.

Acceptance metrics should include:

- request context size where measurable;
- execution rounds;
- files touched;
- scope violations;
- first-pass verification rate;
- human rework;
- result length and readback quality.

### RV2-07 — Phase B4 Visible Operator UX

Objective:

Add an optional visible tray wrapper or small status panel that displays and controls the same underlying operator state.

Minimum UX:

- running, paused, blocked, executing, and failed states;
- current request and last result;
- pause, resume, stop, and open-logs controls.

Boundaries:

- no chat interface;
- no independent policy engine;
- no hidden service;
- no new action, write, approval, or trusted-actor authority.

### RV2-08 — Phase B5 Windows Login Startup

Objective:

After prior acceptance tests pass, optionally start the visible operator in the logged-in user session on the user-designated Primary Operational Host, only when that host's persistence and startup behavior are separately accepted.

Requirements:

- separate explicit startup approval;
- visible foreground or tray execution;
- only one instance;
- safe blocked behavior for auth loss, wrong repo/HEAD, missing tools, or state corruption;
- pause and stop remain available;
- startup can be disabled and recovered cleanly;
- no hidden Windows service in v0.

### RV2-09 — Phase C MCP Feasibility And Integration

Objective:

Evaluate, and only after approval integrate, a ChatGPT App or MCP connector that reduces trigger and polling friction while preserving the existing contract and GitHub audit path.

Feasibility must cover:

- supported transport and deployment;
- authentication and trust boundary;
- local network exposure or relay requirements;
- tool schema;
- cost and plan dependencies;
- audit retention;
- pause, stop, and fallback behavior;
- compatibility with current Dispatcher and Runner policy.

Integration rules:

- MCP is an adapter, not a replacement policy engine;
- target, branch, HEAD, expiry, request, action, and one-task scope remain explicit;
- GitHub remains auditable unless separately changed;
- a ChatGPT tool call does not become commit, push, close, label, PR, merge, or other high-risk approval.

### RV2-P1 — Product Mainline Parallel Checkpoint

Objective:

Prevent bridge work from indefinitely displacing visible Local Document-to-Knowledge Workbench value.

This checkpoint may be evaluated after RV2-03 and again after RV2-04. Candidate product priorities include:

- core scan, index, search, summary, preview, destination-check, export, and readback reliability;
- demo dataset and guided walkthrough;
- onboarding and setup clarity;
- architecture, security boundary, and known-limitations documentation;
- portfolio screenshots, demo evidence, and interview narrative.

Product work must remain separate from Bridge Operator runtime and authority.

## Roadmap Entry Sequence

Default sequence:

```text
RV2-00 specification adoption
-> RV2-01 B4-D supervised live smoke
-> RV2-02 B4-D closeout and truth sync
-> RV2-03 B3 operational acceptance
-> RV2-04 runtime contract binding
-> RV2-05 minimal lawb facade
-> RV2-06 execution profiles and token control
-> RV2-07 visible operator UX
-> RV2-08 login startup
-> RV2-09 MCP feasibility and integration
```

`RV2-P1` is a parallel checkpoint and must be considered after RV2-03 or earlier if bridge effort begins displacing product value.

The sequence may change only through explicit user-approved change control. A changed sequence must document why the previous entry criteria or risk ordering no longer applies.

## Auth And Dependency Preflight Policy

Roadmap v2 should add structured preflight evidence for:

- repository and local environment;
- Python and expected virtual environment;
- GitHub CLI discovery and authentication;
- Codex launcher discovery and usability;
- expected branch and HEAD;
- local state directory and control flags;
- required scripts and dependencies.

The roadmap may evaluate whether Codex can expose a stable machine-readable distinction between ChatGPT subscription sign-in and API-key-backed execution. Until that is proven:

- do not claim that the bridge can guarantee a specific billing path;
- do not silently configure an API-key fallback;
- record what can and cannot be verified;
- fail closed where a node explicitly requires a verified auth mode that the installed tool cannot prove.

## Required Roadmap Read Audit

After this specification is merged, every Roadmap v2 planning or execution task must read:

1. `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`;
2. `docs/BRIDGE_OPERATOR_V0_SPEC.md`;
3. `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md`;
4. the Roadmap v2 tracker;
5. the active node Issue when one exists.

It must emit:

```text
ROADMAP-V2-READ-AUDIT protocol=lawb.bridge_roadmap_v2_read.v1
spec_path=docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md
spec_version=v1.0
spec_read=<true|false>
tracker_issue=<number|not_created>
active_node=<RV2-XX|none>
active_node_issue=<number|not_created|none>
entry_criteria_met=<true|false|not_evaluated>
task_alignment=<core|support|fallback|drift_detected>
authority_change_requested=<true|false>
chatgpt_remains_primary_interface=<true|false>
high_risk_actions_remain_separate=<true|false>
product_runtime_boundary_preserved=<true|false>
failure_reason=<none or exact reason>
```

If this specification is missing, unreadable, not merged, or not acknowledged for Roadmap v2 work, stop before producing a Codex execution task or performing a Roadmap v2 write.

## Drift Detection

Flag `drift_detected` for proposals that:

- treat B4-D as permission for general daily automation;
- skip B3 operational acceptance and jump directly to startup or MCP;
- add a facade that reimplements or bypasses Dispatcher/Runner policy;
- claim Task Packet runtime enforcement when only schema validation exists;
- call a manual relay or per-task manual PollOnce the final experience;
- use Codex success text instead of changed-file and verification evidence;
- allow model or token optimization to weaken correctness or reviewability;
- expand bridge scope while hiding product-mainline displacement;
- create many active node Issues without proven entry criteria;
- interpret an Issue, PR, merge, or prior approval as authority for the next phase.

## Change Control

This specification may be changed only through an explicit user-approved repository change.

A proposed change must state:

- current and proposed version;
- exact changed sections;
- reason and supporting evidence;
- affected nodes;
- whether authority, polling, startup, action allowlist, trusted actors, external connectivity, primary interface, audit surface, or product boundary changes;
- migration or supersession impact on the tracker and active node.

Authority-changing revisions always require a separate decision and must not be bundled into ordinary usability, documentation, or test maintenance.

## Initial Activation Plan

After merge and post-merge verification:

1. create the Roadmap v2 tracker without labels or milestone dependency;
2. record `RV2-00` as `DONE`;
3. create `RV2-01` as the sole active-node candidate;
4. set `RV2-01` to `PLANNED` or `READY` only after checking its entry criteria;
5. do not publish smoke markers or execute B4-D until the required separate approvals are obtained.

This section records the historical activation procedure. Tracker #168 is the designated canonical GitHub Roadmap surface. GitHub Issue #168 and Issue #175 were last synchronized on 2026-07-02 and still record the pre-D1 gate and baseline. They have not yet been synchronized with PR #181 or D1 completion, and their update requires a separately approved GitHub truth-sync operation. No other Roadmap v2 node is active.

## Current Authority Boundary

Adopting this specification does not itself authorize:

- tracker or node creation before merge;
- live B4-D execution;
- request or result publication;
- B1, B2, B3, Dispatcher, Runner, or Codex execution;
- automatic polling;
- runtime contract implementation;
- facade implementation;
- token/profile implementation;
- tray UX;
- login startup;
- MCP;
- commit, push, Issue close, label edit, PR creation, merge, force push, or branch deletion beyond the separately approved documentation PR used to adopt this specification.
