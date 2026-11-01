# PLANS.md

## NEXUS Node 01 — Current Consolidation Candidate

Updated 2026-11-01. This section owns the current local NEXUS direction and
Node 01 scope. Earlier document-only submissions were insufficient for the
user's expanded final outcome. The final consolidation adds a complete document
register, historical isolation, simpler root navigation and an executable
project-only capability entry that reuses existing requirement extraction.
Node 01 local consolidation is technically ACCEPTED by independent ChatGPT review.
[PR #362](https://github.com/HarryWhite-TW/local-ai-workbench/pull/362) publishes
the candidate on `codex/node01-consolidated-candidate-20261101`; at publication
it was awaiting merge to master. The PR tracks its current merge state. Real
daily-use acceptance remains outstanding; Node 02 is not activated.

The source identities, uncommitted-file descriptions and verification counts
below record the pre-publication local snapshot, not the publication state of
this candidate branch. The PR records publication checks and its exact head SHA.

### Direction and Authority

The user selected: Node 01 consolidation -> Node 02 single official product
blueprint -> Node 03 NEXUS single-entry engineering/self-iteration -> Node 04
real daily-use acceptance. Only Node 01 is authorized here. No later node is
automatically activated, and this sequence defines no new runtime permission.

NEXUS is intended to become the user's primary personal AI entrypoint for chat,
planning, delegation, results, previews and revisions. Work, Codex, document
services and other tools are potential capability sources behind that entry.
This intent does not claim current single-entry engineering integration.
The repository's canonical public showcase identity remains **Local
Document-to-Knowledge Workbench**. Any formal identity or safety-contract change
needs a concrete proposal and separate user approval; AGENTS remains unchanged.

The 2026-11-01 Independent Review is a dated research input, not a second plan.
Its recommendation to keep NEXUS optional does not override the user's selected
long-term direction. Existing Recoverable Baseline work is retained; this node
does not recreate backup, recovery engineering or a new roadmap system.

### Candidate and Version Binding

- Pre-publication working directory: the local Windows NEXUS candidate checkout.
- Local branch: `codex/lc-workux01-observation-reader`.
- Local HEAD: `6c1eac3e8be6f2b6efc5ba58e5289db5972a1f71`.
- GitHub `master`, freshly read for this node:
  `661f2b77a6f4d42d8583eb10e396e2a91a35a571` (PR #361).
- The local HEAD adds running cancellation and the M2-C4 syntax correction.
  At that snapshot master had the `surface.py:40` SyntaxError. The affected master
  Companion entry is not launchable; this does not invalidate unrelated
  document or Bridge acceptance.
- Starting tree: 10 tracked modifications, 67 untracked files, no staged files
  (`git status --porcelain=v1 --untracked-files=all`). The daily launcher, chat,
  resources and native reader are part of this uncommitted candidate, not master.
- Continuation starting tree: 13 tracked modifications, the same 67 untracked
  files, zero staged. Local `master` is stale at `4c38c672f09a25f5fa3754b2265afe4a110b63ca`;
  it must not be used as the remote-master or daily-candidate identity.
- Final consolidation starts at 17 tracked modifications / 67 untracked / zero
  staged, with prior fingerprint `68613aadca30d009a2c29d23a589d2170ad0b355967365d9eca798f640d510a9`.
  It archives only explicitly unreferenced old records, marks retained history,
  adds `src/project_capabilities.py` and focused tests, and clarifies two existing
  host module descriptions. Existing NEXUS algorithms/assets/tests are retained.
  No Git publication, recovery rebuild, safety-contract or showcase rename occurs.

At the pre-publication snapshot, local HEAD alone could not reproduce the
candidate without its uncommitted sources and Node 01 documentation diff.
PR #362 now carries the complete candidate; its merge state is tracked there.
Version observations are dated snapshots, not permanent branch assertions.

### Capability Disposition

The source/call/version ledger and complete document register in
`docs/ENGINEERING_RECORDS_INDEX.md` own detailed lookup. They are evidence, not
a second roadmap. Relative to the daily NEXUS candidate:

- 現役: daily/chat/project/text resources/fixed work/review/continuity/Native Reader.
- 待接入: existing document API and legacy read-only Codex adapter; integration choice remains Node 02.
- 獨立／備用: document showcase, Bridge execution/notification/observation family, HGW/HAG and visual prototypes.
- 歷史／已替代: prior activation queues, legacy relay assumptions, OPT07 adoption and superseded planning.

Document labels are CURRENT (effective entry/rules), REUSABLE (existing reusable
interfaces/assets), SPECIALIZED (valid scoped systems/contracts), HISTORICAL
(recorded prior claims only), UNCERTAIN (preserved draft/placeholder). A test
reference can require retaining a historical path without making it current
product authority. See the register for per-file references and dispositions.

### Source Relationships and Reuse Decisions

The [source connection and version ledger](docs/ENGINEERING_RECORDS_INDEX.md#node-01-source-connections-and-reuse)
is the evidence locator for the classification above. It records actual callers,
entrypoints, state ownership, applicable source versions, historical branches,
and tests. Finding an implementation there means reuse must be considered before
proposing new development; it does not mean the implementation is wired into NEXUS.

- The daily work path already connects chat proposals to Surface/Core/ReviewStore,
  then can explicitly preview a saved work result back into chat. Project context
  includes the same Surface snapshot; it is not a second work-state implementation.
- The older Codex adapter and Native Reader both use app-server transport, but
  have different process homes, login sources and contracts. Preserve both for
  their respective roles; do not connect their credentials or sessions implicitly.
- Document Web/API owns extraction/index/artifacts/export; NEXUS resources own
  bounded source preview and chat handoff. These overlap in reading needs but do
  not share the document pipeline. Reuse the existing API service if the blueprint
  selects richer document integration; do not describe PDF/DOCX as nonexistent.
- Core/ReviewStore is reused by the legacy Companion host and daily work. HGW
  contracts and HAG proposals are independent implementations for different
  boundaries; no HGW/HAG runtime migration is required for this candidate.
- Panel/Sanctuary/Unified Shell are already connected within the Bridge observer
  family. Preserve their shared truth source. NEXUS uses its own Surface snapshot,
  not those Bridge stores; Native Reader status cannot replace either authority.

No daily runtime repair is selected. The final consolidation adds a developer-only
capability entry and clarifies host descriptions; existing algorithms stay in place. The daily composition,
route dispatch, UI action callers and served static assets have matching source
edges. The missing connections (general engineering, rich document API, native
completion notification, OS overlay) are absent end-to-end product contracts,
not disconnected imports or a missing invocation in an existing approved flow.
Adding those would require choosing executor/data/authority contracts in Node 02.
Legacy `surface.main` requires a trusted credential host and shares today's UI;
its presence is not a claim that it is a complete SIWC daily entry. The test
launchers intentionally run synthetic fixtures and must not become the real entry.

### Evidence Limits and Node 02 Inputs

Confirmed source facts: daily.py wires ProjectWork rather than CodexRuntime;
chat invokes Responses without tools; resources are bounded text rather than
the showcase index; Native Reader only reads history; review remains explicit.
The first-submission runtime checks and continuation static/source checks are
recorded in `docs/ENGINEERING_RECORDS_INDEX.md`.

Still unverified: full real-SIWC plus native-history end-to-end acceptance,
correct deep-link navigation in the desktop app, cross-process live state,
Windows game-time notification/focus behaviour, and applicability of the
unread 10/28 MXC archive to this changing candidate. Existing synthetic tests
and historical test counts do not close these questions. None is silently
promoted to a Node 01 daily-use acceptance claim.

Node 02 must decide: the single-entry task/executor boundary; whether to reuse
the existing Codex adapter or platform capability; how document services enter
NEXUS; task/result/reviewer ownership; navigation/notification needs; and which
UI assets serve real data. A formal showcase rename or broader execution/write
contract requires separate approval. Node 01 implements none of these decisions.

## Document Showcase Position

The formal public product remains Local Document-to-Knowledge Workbench:
localhost, single-user, local-first document indexing, review and approved
Markdown export. Its setup/features are in README; the existing validation
record is `docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md`
(`PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED`). That historical verdict
does not activate Phase 5.4 or accept the NEXUS candidate.

## Development Workflow Position

Product runtime and development-workflow tooling remain separate.

The daily engineering baseline is Native-first Hybrid. When native capabilities
satisfy the task, the preferred route is:

`ChatGPT Work -> native Codex execution environment -> local repo/tools -> result returned to the same Work conversation`

This route has been demonstrated on the user's Windows environment for local
repository/source inspection, edits, Python tests, JavaScript checks, Chrome
rendering verification, diff/readback, and same-conversation result return.
Internal Codex technology does not require the user to manage a separate Codex
view/thread or relay prompts/results. ChatGPT owns the outcome and authority
boundaries. Independent ChatGPT final technical review of the exact candidate,
diff, and evidence against the approved task is required. When ChatGPT Work is
the execution surface, same-conversation review is preferred because it avoids
manual relay; it is not a permanent architectural requirement. Supervising
ChatGPT or a future Companion/control surface may perform that independent
final review. The user must not become the routine technical relay between
execution and review.
Executor completion remains distinct from final acceptance. Stage, commit,
push, PR creation, merge, and other remote, irreversible, or high-risk actions
remain separately authority-gated.

Bridge / Operator / Dispatcher / Runner remains incumbent specialised
governance, compatibility, recovery, or fallback infrastructure. It has not
been fully replaced; its governance applies whenever that route is used or
changed. It is not mandatory transport for every engineering task. Do not
build a duplicate custom terminal, diff viewer, file explorer, browser, generic
queue, memory system, or multi-agent framework merely to reproduce platform
capability. This route choice does not change the product runtime or activate
new custom infrastructure.

The accepted Phase 0 Final Daily-Use Acceptance remains the incumbent Bridge
baseline. Its supported scope is the visible, localhost, single-user Bridge path
already present on canonical `master`: ChatGPT remains the primary UI; GitHub
remains the auditable Task and Result Surface; the managed local Workflow and
Human View expose request-bound progress, terminal result, and final-review
truth; and automatic startup remains local-only. Manual copy/paste relay and
manual `PollOnce` remain fallback or recovery paths, not the target daily flow.

Grand Audit R1 and R2 remediation is complete on canonical `master`. R1, merged
through PR #330, makes ambiguous Task Packets fail closed when fields are
duplicated or non-comment content is not consumed. R2, merged through PR #332,
preserves unresolved final-review truth across requests, does not claim that a
dispatcher was reached before the durable dispatch transition succeeds, and
separates local Workflow readiness from external model execution availability.

This Bridge acceptance remains bounded. Local Workflow readiness does not prove that
external model execution is available; that is known only when an actual
execution is attempted. Continuous end-to-end telemetry through every
Dispatcher, Runner, and Codex transition is not claimed. The accepted baseline
does not add a service, tray, VM executor, repository extraction, new external
API, broader trusted actors, automatic publication, or approval chaining.

No subsequent Product or Workflow node activates automatically. The current
active engineering outcome must come from fresh project control or explicit
user direction, not this static planning paragraph. PRT items remain optional
reality-validation assets, not a mandatory numbered execution queue. MCP /
ChatGPT App integrations, custom Desktop Agent, VM executor, service, tray, and
repository extraction remain future or separately gated work. This restriction
does not defer use of the proven native Work capabilities above. No Product or Workflow node activates
automatically.

### Incumbent Bridge Final Regression Gate and Freeze

The Phase 0 baseline may be declared regression-frozen only after one separately
authorized final-regression run at an exact, freshly verified canonical
`master` HEAD. The gate must record the exact HEAD and commands, pass the full
committed `tests/local_runner_bridge` suite without failures, pass
`git diff --check`, preserve the R1 fail-closed Task Packet cases and the R2
cross-request lifecycle/readiness distinctions, and receive independent durable
result readback. This documentation reconciliation defines the gate; its
docs-only `git diff --check` does not satisfy the runtime regression gate.

After that freeze, incumbent Bridge implementation may thaw only through a separately
approved task with an explicit objective, scope, authority, and verification
plan, prompted by a reproducible regression or security defect, material
platform drift, or an explicitly approved product outcome. Thaw work must start
from freshly verified state, rerun impacted checks plus the final-regression
gate, and resynchronize durable truth if any current claim changes. An Issue,
roadmap ordering, optional PRT item, or stale document alone cannot thaw the
baseline or activate a next node.

These runtime regression and freeze rules govern the incumbent Bridge baseline;
they do not require routing ordinary native engineering through Bridge or running
its full suite for governance-only changes.

## Historical Ecosystem Context

The retained cross-repository roles, HAG/ECO-CP1 publication history and old
stop-line narrative are in [the archived checkpoint](docs/archive/PLANS_ECOSYSTEM_CHECKPOINT.md).
Current component owners are in the engineering index; the Bridge regression
and freeze rules immediately above remain effective and were not moved.

## Current Governance and Evidence Pointers

- Repository governance: `AGENTS.md`;
- Bridge-specific governance: `src/local_runner_bridge/AGENTS.md`;
- acceptance integrity: `docs/WORKFLOW_ACCEPTANCE_INTEGRITY_PROTOCOL.md`;
- engineering record navigation: `docs/ENGINEERING_RECORDS_INDEX.md`;
- execution governance when using or changing the incumbent Bridge route:
  `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md`;
- Direction Lock: `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`;
- Bridge Operator specification: `docs/BRIDGE_OPERATOR_V0_SPEC.md`;
- historical ECO-01 strategy: `docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md` (current NEXUS direction is the Node 01 section above);
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

- 2026-11-01: Node 01 local consolidation candidate: aligned current NEXUS
  ownership and version limits with README and the engineering index; preserved
  showcase identity, historical acceptance and authority; activated no later node.

- 2026-09-22: Reconciled the accepted Phase 0 Final Daily-Use baseline with
  completed Grand Audit R1/R2 remediation, preserved bounded supported-scope
  and limitation wording, and defined the final-regression freeze and explicit
  thaw conditions without activating another node.
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
