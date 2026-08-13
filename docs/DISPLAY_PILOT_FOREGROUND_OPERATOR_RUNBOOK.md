# Display Pilot Operating and Interview Guide

## Purpose

This guide explains the current ChatGPT-first development workflow as a human
operator, reviewer, or interviewer should see it. It covers what is directly
observable, what is only established after durable evidence, where the workflow
fails closed, and what the user still controls.

The Display Pilot is development-workflow tooling. The product remains the
localhost, single-user **Local Document-to-Knowledge Workbench**. Bridge
Operator, Dispatcher, Runner, Codex, GitHub task/result comments, and lifecycle
state are not product runtime features.

This guide does not grant authority to start a Bridge, publish a request, run
Codex, mutate GitHub, or recover lifecycle state. Each live or write-capable
package still needs its own explicit authority.

## Current position

The evidence position as of the current documentation closeout is:

| Capability | Classification | Evidence qualifier |
| --- | --- | --- |
| Product runtime vs development-workflow separation | **VERIFIED** | The Local Document-to-Knowledge Workbench remains the product; Bridge tooling remains development-workflow tooling. |
| ChatGPT-First Operating V1 accepted and published | **VERIFIED** | The accepted and published Operating V1 completion line remains distinct from this Display Pilot closeout. |
| Routed engineering-workspace execution demonstrated by Issue #263 | **VERIFIED** | Issue #263 records the successful routed `run-reviewbundle` dogfood chain. |
| Explicit dispatch request identity behavior | **VERIFIED** | PR #265 added explicit dispatch request selection and validation. |
| Request-local execution/reconciliation visibility reset | **VERIFIED** | PR #265 prevents a new request identity from inheriting prior request visibility. |
| Typed Dispatcher outcomes `20` / `21` / `22` | **VERIFIED** | PR #266 preserves deterministic rejection, uncertain reach, and transient pre-Runner failure semantics. |
| Durable reconciliation and duplicate/fail-closed protection | **VERIFIED** | Conflicting or unresolved evidence blocks redispatch and unsafe settlement. |
| Reference-host launcher preflight plus bounded Bridge start and canonical `stop.flag` shutdown | **VERIFIED** | After exact Git trust correction, the realigned host passed preflight, started one bounded operator, and later shut down cleanly. |
| Historical Runner/Codex execution reach for `display-pilot-closeout-264-20260812T134800Z-r1` | **UNVERIFIED** | Absence of a trusted terminal result does not prove that Runner or Codex did or did not execute. |
| Live execution visibility across Bridge -> Dispatcher -> Runner -> Codex | **PARTIAL** | Bridge/preflight visibility exists, but Dispatcher/Runner/Codex execution progress is largely post-hoc and there is no trusted full live progress stream. |
| Fresh repaired health-to-real overlap E2E initiated directly by ChatGPT | **UNVERIFIED** | The latest live-ready session was platform-blocked before GitHub mutation; no fresh HEALTH marker, Inbox request, or `LAWBRUNNER-RESULT` was created. |
| Routine automatic recovery of `NOT_FOUND` dispatched execution uncertainty | **DEFERRED** | Current B3 preserves unresolved in-flight state and fails closed; no reusable automatic recovery capability is claimed. |

### Platform blocker evidence

After the local Bridge became live-ready, supervising ChatGPT attempted to
publish a fresh HEALTH dispatch. The current ChatGPT execution surface blocked
that GitHub write before mutation. Readback found no fresh HEALTH marker, Inbox
request, or `LAWBRUNNER-RESULT`, and the live window was then closed cleanly.

This is a limitation observed on that ChatGPT surface/session. It is not
evidence that the local Bridge is broken, and it does not prove that every
future ChatGPT plan or execution surface can never dispatch. Manual relay may
be used as fallback or recovery, but it must not be presented as the target UX.

## Operating model

```text
User and ChatGPT
-> explicit GitHub task and dispatch identity
-> fixed Bridge Inbox #147
-> visible bounded Bridge Operator
-> issue-scoped Dispatcher
-> bounded Runner
-> Codex
-> verification and LAWBRUNNER-RESULT evidence
-> ChatGPT review
-> user decision or separately approved permanent action
```

The fixed control repository supplies the operator, Dispatcher, and Runner.
For LAWB, a local-only route may select a separate validated engineering
workspace. GitHub text cannot choose or override a local filesystem path.

## Execution Progress View

The labels below are intentionally strict:

- **DIRECTLY OBSERVABLE NOW:** a human can inspect the current surface while
  that stage exists.
- **POST-HOC / DURABLE EVIDENCE ONLY:** the stage is concluded from validated
  logs, lifecycle records, process evidence, or GitHub result evidence after
  the relevant action.
- **NOT CURRENTLY OBSERVABLE:** no trusted live stage signal is exposed.

| Stage | Visibility | What the human can actually see | Intervention rule |
| --- | --- | --- | --- |
| Request prepared | **DIRECTLY OBSERVABLE NOW** | The proposed Task Packet, repository, Issue, branch, full HEAD, expiry, action, allowed files, and authority boundary in ChatGPT or the reviewed Issue body. | Correct scope or identity before publication. |
| Request published | **DIRECTLY OBSERVABLE NOW** | The exact `CHATGPT-DISPATCH` marker and matching fixed-Inbox request on GitHub, including author metadata and request ID. | If publication is blocked or identity is wrong, do not substitute an ambiguous marker. |
| Bridge / preflight | **DIRECTLY OBSERVABLE NOW** | Foreground console, launcher preflight result, `heartbeat.json`, `state.json`, `operator.lock`, and read-only diagnostics. | Stop on wrong route, dirty target, wrong HEAD, auth/tool failure, active lock, or lifecycle ambiguity. |
| Dispatcher | **POST-HOC / DURABLE EVIDENCE ONLY** | Operator summary/log fields and typed exit outcome show whether Dispatcher was invoked and what boundary was proven. There is no trusted continuous Dispatcher progress stream. | Use typed outcome and structured evidence; never infer reach from stderr text. |
| Runner | **POST-HOC / DURABLE EVIDENCE ONLY** | A trusted result or machine/process evidence may establish Runner outcome. Exit `21` means Runner may have started or absence cannot be proven. | Preserve uncertainty and do not redispatch automatically. |
| Codex | **NOT CURRENTLY OBSERVABLE** while running; **POST-HOC / DURABLE EVIDENCE ONLY** when trusted result evidence exists | A final ReviewBundle/result may report Codex completion. Missing result evidence does not prove non-execution. | Treat unknown reach as unknown; do not invent live telemetry. |
| Verification / result evidence | **DIRECTLY OBSERVABLE NOW** after publication; otherwise **POST-HOC / DURABLE EVIDENCE ONLY** locally | `LAWBRUNNER-RESULT`, ReviewBundle, canonical local evidence, final HEAD/index observations, and authority flags. | Compare request identity, repository, Issue, branch, HEAD, author, and result before accepting it. |
| ChatGPT review | **DIRECTLY OBSERVABLE NOW** when the result is readable to ChatGPT | ChatGPT can classify success, failure, uncertainty, evidence gaps, and any next approval. | No result or pending review is not acceptance. |
| User decision / completion | **DIRECTLY OBSERVABLE NOW** | The user explicitly approves direction or a separately gated high-risk action. Durable closeout is recorded only on authorized surfaces. | Never treat a prior approval as approval chaining. |

### LIVE EXECUTION VISIBILITY GAP

The workflow does not currently expose a trusted live progress feed for
Dispatcher, Runner, or Codex. Foreground Bridge health is visible, but detailed
execution reach is primarily reconstructed after the fact. Adding tray UI,
streaming telemetry, MCP, or another transport would be new architecture and is
not activated by this gap.

## Real success evidence map

### Current routed LAWB dogfood — Issue #263

```text
Issue #263 approved bounded routing probe
-> CHATGPT-DISPATCH comment 5255403752
-> fixed Bridge route selected the engineering workspace
-> Runner ReviewBundle comment 5255460713
-> LAWBRUNNER-RESULT comment 5255461063
-> result=success, runner exit=0
-> branch=codex/engineering-workspace-live
-> HEAD=714482594944be8f28125c6b1f67eccb12b0d9bc
-> final staged area clean and final HEAD unchanged
-> no trusted-parent stage/commit/push/PR/merge/Issue-close action
```

This proves the bounded routed control-plane path for that historical request.
The SHA and branch are evidence bindings for that run, not the current canonical
master identity. It does not prove automatic publication authority,
production-grade availability, or live stage-by-stage visibility.

### Historical #264 HEALTH evidence

Issue #264 HEALTH dispatch `display-pilot-health-264-20260812T134700Z-r1`
produced `LAWBRUNNER-RESULT` comment `5267689759` with `result=success`, clean
Git status, unchanged HEAD, and empty staged area on the then-current
`714482...` binding. The later REAL request is a separate incident and must not
borrow this HEALTH success.

## Real fail-closed evidence map

### Issue #264 stranded request and exceptional manual incident recovery

```text
LAYER 1 — NORMAL B3 CONTRACT
REAL dispatch comment 5267707353
-> fixed-Inbox request comment 5267709816
-> no trusted matching durable terminal result
-> processed-state exclusion
-> durable reconciliation=NOT_FOUND
-> execution reach remains uncertain
-> normal B3 restart result=dispatched_in_flight_uncertain
-> operator.lock and in_flight.json preserved
-> no redispatch
-> no routine quarantine or deletion

LAYER 2 — LATER EXCEPTIONAL MANUAL INCIDENT ACTION
-> separate explicit user authority
-> exact request and operator-session identity reviewed
-> lock owner proven dead; descendants proven absent
-> historical request expired
-> no processed completion
-> no durable terminal completion
-> no conflicting evidence
-> exceptional exact in_flight record removal
-> stale protocol-v2 lock quarantined with original bytes/hash preserved
-> not normal automatic B3 recovery
-> not a general replay-safe NOT_FOUND mechanism
-> historical Runner/Codex execution reach remains UNVERIFIED
```

The separately authorized incident action did not reinterpret the old request
as success or definite failure. It did not prove that Runner or Codex started,
and it did not prove that they did not start. Later independent runtime
alignment and launcher evidence showed that the host could operate again, but
that observation does not redefine the normal B3 fail-closed contract or create
a reusable recovery rule.

### Current typed Dispatcher boundary

| Exit | Meaning | Lifecycle treatment |
| --- | --- | --- |
| `20` | Structured deterministic admission rejection proves Runner was not started. | Terminal non-success settlement; do not redispatch that accepted rejection. |
| `21` | Runner may have started, or execution reach cannot be proven absent. | Preserve in-flight uncertainty and fail closed; never infer safety from stderr. |
| `22` | Transient or environmental failure is proven before Runner. | Do not permanently consume the request; a later independent run may retry after the condition is corrected. No automatic Codex retry occurs inside the failed run. |

Explicit dispatch identity prevents an unrelated current marker on the same
Issue from automatically creating Issue-wide ambiguity. Multiple or
conflicting markers for the same request still fail closed. When request
identity changes, request-local execution and reconciliation visibility resets
so request A cannot contaminate the displayed state for request B.

## Reference-host setup and verification

### 1. Separate control and execution roles

- **Stable runtime:** clean control/reference checkout containing the reviewed
  launcher, Bridge, Dispatcher, and Runner.
- **Routed engineering workspace:** exact clean Git root where an approved LAWB
  request may execute and create its bounded candidate.

At the current evidence checkpoint, the stable runtime is
`master@421979ee56b2ee6c97dac67feb0efb92154ed533`. The engineering workspace
must be independently checked for origin, branch, full HEAD, clean worktree,
and empty index before every launch.

### 2. Verify exact Git trust

The launcher incident `target_repository_not_git_repository` was traced to Git
dubious-ownership protection on the routed workspace. It was a host
trust/configuration incident, not a repository defect.

On this reference host, current-user global `safe.directory` must contain the
exact path:

```text
C:/Users/harry/Desktop/local-ai-workbench-engineering
```

Review with:

```powershell
git config --global --get-all safe.directory
```

If the exact path is missing, add only that reviewed path under a separately
authorized host-configuration step. Never add `*`, a broad parent directory, or
an unrelated checkout.

### 3. Verify local-only routing identity

The Bridge state root is:

```text
%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator\
```

The optional routing file under that directory must use the exact schema:

```json
{"protocol":"lawb.bridge_operator_local_routing.v1","repository":"HarryWhite-TW/local-ai-workbench","target_repo_root":"C:\\Users\\harry\\Desktop\\local-ai-workbench-engineering"}
```

The launcher reads but does not create or modify this file. Remote Issue,
comment, Task Packet, status, or result text cannot override the route. Do not
configure both `repository_routing.json` and `-TargetRepoRoot`; ambiguity fails
closed.

### 4. Run normal preflight first

From the stable runtime root:

```powershell
.\scripts\start_bridge_operator_b3c.ps1
```

The default invocation is preflight-only. It verifies reviewed bindings and
lifecycle state without starting another polling loop. A live foreground start
requires a separately approved package and explicit `-StartForeground`.

### 5. Use read-only diagnostics

```powershell
$env:PYTHONPATH='src'
.\.venv-course\Scripts\python.exe `
  -m local_runner_bridge.bridge_diagnostics `
  --repo-root . `
  --pretty
```

Diagnostics classify lock identity/liveness/descendants, in-flight state,
heartbeat freshness, quarantine evidence, and exceptional recovery reasons.
They do not delete or repair lifecycle state and do not invoke Dispatcher,
Runner, Codex, or GitHub.

## Safe operation and shutdown

- Keep the bounded operator visible.
- Confirm there is exactly one operator identity and one complete lock.
- Treat an active matching lock as active even if heartbeat appears stale.
- Use `pause.flag` to pause later cycles when the approved package calls for it.
- Use canonical `stop.flag` for graceful shutdown. It is observed at the next
  cycle boundary, allowing current bounded work to settle before exit.
- After shutdown, verify the exact PID/start identity is dead, descendants are
  absent, `operator.lock` and `in_flight.json` are settled as expected, and the
  launcher chain has exited. Only then remove the exact control flag before a
  later restart.

Never abruptly kill an operator merely because the console looks quiet. Never
delete `operator.lock` or `in_flight.json` to make preflight pass.

## Recovery guidance

| Situation | Safe response |
| --- | --- |
| Launcher preflight blocks | Read the exact blocked reason. Recheck target root, normalized origin, branch/full HEAD, worktree/index, route schema, tool/auth binding, and exact Git trust. Do not rewrite source or broaden trust to bypass the gate. |
| Active lock exists | Use diagnostics to compare protocol, session, PID, exact process-start identity, and descendants. A matching live owner blocks. Do not remove the lock from heartbeat age alone. |
| `in_flight.json` is unresolved | Preserve it. Review its exact request/session/stage, processed-state exclusion, lock identity, durable result evidence, and reconciliation outcome. Uncertainty blocks redispatch. |
| Durable result is missing | Classify execution reach as unknown unless structured parent-controlled evidence proves otherwise. Do not treat stderr, silence, or absence of a comment as proof that Runner did not start. |
| Request identity is ambiguous | Stop. Compare Inbox request ID, target dispatch request ID, repository, Issue, branch, full HEAD, expiry, action, trusted author metadata, and matching result identity. Same-request duplicate/conflict remains fail closed. |
| ChatGPT-side dispatch cannot be published | Record `platform-blocked`, verify no partial GitHub marker/Inbox/result mutation, and close or pause the live window safely. Manual relay is fallback only and does not validate the target ChatGPT-direct experience. |
| Dead owner coexists with unresolved dispatched in-flight evidence and `NOT_FOUND` reconciliation | Normal B3 behavior remains fail closed: preserve lifecycle evidence and do not redispatch. Do not delete or quarantine evidence merely because the owner is dead. Any exceptional manual incident recovery requires separate explicit authority and incident-specific adjudication; the prior #264 action creates no reusable rule. Do not manually rename or delete lifecycle files. |

Recovery authority is incident-specific. A prior recovery result does not grant
permission to recover a new request or start another Bridge.

## Limitations and authority boundary

- The latest ChatGPT-direct GitHub dispatch attempt was platform-blocked before
  mutation; the repaired health-to-real overlap path therefore lacks fresh
  ChatGPT-authored live E2E acceptance.
- Manual relay and manual `PollOnce` remain fallback/recovery, not the strategic
  target.
- Execution-stage visibility is partly post-hoc; there is no trusted live
  Dispatcher/Runner/Codex progress stream.
- This is bounded localhost workflow tooling, not production-grade service
  availability or fully autonomous software development.
- No automatic stage, commit, push, PR creation, merge, Issue close, label edit,
  deployment, credential change, approval consumption, or approval chaining is
  authorized.
- No hidden service, tray, MCP, Independent HGW runtime, new transport, or
  Phase C work is activated by this closeout.
- A success result proves only its exact request, repository, branch, HEAD,
  action, evidence scope, and recorded authority flags.

## Historical candidate note

The former “Display Pilot Foreground Operator Candidate” documented a non-live
DP4 path using a fixed HGW selector, HAG target, and separate Display Pilot
state root. Its process-evidence and fail-closed design remains useful history,
but its old branch/HEAD bindings and candidate launch commands are not current
reference-host instructions. Git history preserves that design detail.

## 5–10 minute interview or demo route

1. **Product separation — 45 seconds.** Show the localhost document workbench
   and state that Bridge tooling is development infrastructure, not the product.
2. **Request and authority — 60 seconds.** Open one Task Packet and point out
   repository, Issue, request ID, branch, full HEAD, allowed files, expiry, and
   forbidden permanent actions.
3. **Bridge and routing — 60 seconds.** Explain stable control checkout versus
   routed engineering workspace, fixed Inbox #147, local-only route, and exact
   Git-root/clean-index preflight.
4. **Execution Progress View — 60 seconds.** Distinguish visible Bridge health
   from post-hoc Dispatcher/Runner/Codex evidence. Name the live visibility gap.
5. **Success evidence — 60 seconds.** Walk Issue #263 from dispatch comment
   `5255403752` to result `5255461063`, emphasizing exact identity and unchanged
   HEAD/index.
6. **Fail-closed evidence — 90 seconds.** Walk Issue #264: old HEALTH success,
   separate stranded REAL request, missing trusted result, preserved lifecycle,
   exact dead-owner recovery, and still-unknown historical reach.
7. **Typed outcomes — 45 seconds.** Explain `20` deterministic rejection, `21`
   uncertainty, and `22` proven transient pre-Runner failure.
8. **Platform limitation — 45 seconds.** State that the latest ChatGPT-side
   write was blocked before GitHub mutation; this prevented fresh E2E validation
   but did not show a local Bridge failure.
9. **User control — 30 seconds.** Close with the rule that permanent/high-risk
   actions and recovery remain separately approved; the workflow never chains
   approvals automatically.

The honest demo ends with the evidence boundary. It does not start another
Bridge, replay an old request, publish a marker, or perform a permanent action
merely to make the presentation look live.
