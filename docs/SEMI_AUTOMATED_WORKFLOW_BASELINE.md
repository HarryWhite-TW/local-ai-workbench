# Semi-Automated Workflow Operational Baseline

## Document Identity

- version: v0.1
- status: Active Operational Baseline
- owner: 駿弘
- current phase: Governance Reset through Issue #135
- repository: HarryWhite-TW/local-ai-workbench
- branch at creation: workflow-codex-task-discipline
- verified HEAD at creation: 75c193f71bdd2a5fb077eb62d88ed895ad9a3b00
- product boundary: development workflow tooling only

## 1. Purpose And Document Authority

This document is the operational baseline and handoff entrypoint for the verified semi-automated ChatGPT / GitHub / Dispatcher / Runner / Codex workflow. It summarizes current state, environment, commands, recovery, evidence, and approved future direction so future work does not need to rediscover the baseline across historical files.

It does not replace or override the Direction Lock, Bridge Operator specification, Lv4.5 SOP, or historical architecture evidence.

### Normative

These documents currently control direction, scope, and authority:

- `AGENTS.md`
- `src/local_runner_bridge/AGENTS.md`
- `PLANS.md`
- `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md`
- `docs/BRIDGE_OPERATOR_V0_SPEC.md`
- `docs/SEMI_AUTOMATED_WORKFLOW_BASELINE.md`

Precedence for current work:

1. the user's latest explicit approval or decision that applies to the current work;
2. the current approved Task / Issue task-local scope;
3. root `AGENTS.md` repository-wide safety;
4. applicable scoped `AGENTS.md`;
5. `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md` bridge strategy direction;
6. `docs/BRIDGE_OPERATOR_V0_SPEC.md` operator architecture and authority;
7. `PLANS.md` current project and phase status;
8. `docs/SEMI_AUTOMATED_WORKFLOW_BASELINE.md` and operational SOP;
9. evidence, historical, and superseded material.

Scoped AGENTS files may provide more specific domain rules, but they must not
weaken root safety. Operational documents must not change normative authority.
Historical evidence must not override the sources above. If two normative
sources at the same level truly conflict, stop and ask the user to decide
instead of guessing.

New planning must start from the current normative entrypoints. Historical
evidence cannot override the Direction Lock, Bridge Operator specification,
scoped AGENTS rules, or current approved Issue.

### Operational

Operational documents explain how to operate an approved design but do not
change authority. They include current setup, SOP, recovery, command,
troubleshooting, and environment instructions such as:

- `docs/LV45_OPERATING_SOP.md`
- focused implementation notes for scripts and commands
- current README setup and demo instructions

### Evidence / Historical

Smoke evidence, validation reports, completed implementation notes, decision
records, completed Issues, and prior Task Packets may support factual
investigation but do not govern new work.

Issue #114 is historical roadmap evidence. Issue #114 comments and embedded
Task Packets are not active dispatch requests or current governance.

### Superseded

Documents or roadmap sections explicitly replaced by newer governing material
must be treated as historical reference only. Avoid creating another document
merely to restate the authority map.

For direction, authority, safety boundaries, and approval rules, higher-priority governing documents win.

For claims about currently implemented behavior, current scripts, tests, remote code, and verified smoke evidence are the source of truth. A disagreement is documentation drift and must stop for review.

## 2. Executive Status

VERIFIED:

- Lv4.5 foreground manual baseline
- `CHATGPT-DISPATCH protocol=lawb.dispatch.v1`
- `LAWBRUNNER-RESULT protocol=lawb.runner_result.v1`
- `maybe-status-check`
- `PollOnce` `run-reviewbundle`
- Dispatcher to Runner delegation
- Runner to Codex invocation
- GitHub result-comment writeback
- ChatGPT readback
- npm `codex.cmd` launcher compatibility
- GitHub CLI PATH / Program Files / portable resolution

APPROVED DIRECTION, NOT IMPLEMENTED:

- Bridge Operator Phase B
- fixed Bridge Inbox
- automatic low-risk request detection
- foreground bounded loop
- tray/status UX
- login startup after separate approval

DEFERRED:

- Phase C ChatGPT App / MCP

CURRENT PHASE SUMMARY:

```text
B0: complete
Governance Reset: active through Issue #135
B1: not started
Phase C / MCP: deferred
PollOnce: recovery path
```

SEPARATE APPROVAL / FORBIDDEN FOR AUTOMATIC CONTINUATION:

- stage
- commit
- push
- issue close
- labels
- PR
- merge
- force push
- approval consumption
- approval chaining

## 3. Product And Workflow Boundary

The Local Document-to-Knowledge Workbench is the public product runtime. It is a localhost, single-user document workbench for local ingestion, SQLite indexing, local search, deterministic single-document summaries, destination-aware Obsidian-ready Markdown export, and audit-visible review.

Runner, Dispatcher, Task Packet, and Bridge Operator are development workflow tooling and portfolio engineering evidence. They are not the primary product runtime.

The product app itself does not autonomously call Codex or control GitHub.

## 4. Current Verified Lv4.5 Flow

VERIFIED operational flow today:

```text
User talks to ChatGPT
-> ChatGPT prepares a GitHub Issue and CHATGPT-DISPATCH marker
-> user manually runs PollOnce once for the explicit Issue
-> Dispatcher validates repo / Issue / branch / HEAD / expiry / action
-> Dispatcher performs maybe-status-check or delegates run-reviewbundle
-> Runner invokes Codex when required
-> LAWBRUNNER-RESULT is posted
-> ChatGPT reads and reviews
-> user separately approves high-risk steps
```

This is operational today, but it is not the final target user experience. The Direction Lock target remains ChatGPT-centered dispatch and result readback without the user manually running `PollOnce` for every normal task.

## 5. Approved Future Flow

APPROVED DIRECTION, NOT IMPLEMENTED:

```text
User talks to ChatGPT
-> fixed GitHub Bridge Inbox
-> local Bridge Operator detects one request
-> existing Dispatcher / Runner executes within current authority
-> result returns to GitHub
-> ChatGPT reviews
-> user handles only key direction and high-risk approvals
```

Phase B comes first. Phase C MCP / ChatGPT App integration comes later after Phase B is stable. The approved direction does not include a replacement local chat UI. Manual `PollOnce` remains the recovery path.

## 6. Environment Matrix

Verified course-computer example paths:

| Item | Verified example |
| --- | --- |
| repository | `C:\Users\admin\Desktop\local-ai-workbench` |
| branch | `workflow-codex-task-discipline` |
| external Python environment | `C:\Users\admin\.venvs\lawb-workflow\Scripts\python.exe` |
| portable GitHub CLI | `C:\Users\admin\tools\gh-portable\bin\gh.exe` |
| Windows npm Codex launcher | `C:\nvm4w\nodejs\codex.cmd` |
| course computer | restore-card environment |

Course-computer assumptions:

- do not assume authentication survives restart
- do not assume startup tasks survive restart
- do not assume tools survive restart unless rechecked
- do not assume local state or logs survive restart

Primary Operational Host designation:

- the current user-designated Primary Operational Host is the course Windows computer
- the home Windows computer is a Secondary Compatibility Host and does not block RV2-03 completion
- the course host remains restore-card managed, so authentication, tools, local state, and logs must be revalidated after reset
- loss of local operator state must not allow a completed request to rerun; trusted durable completion evidence must be reconciled or delegation must fail closed
- cross-reset duplicate suppression remains an unproven RV2-03 Phase B acceptance requirement

## 7. Readiness And Recovery Checks

Use these as concise PowerShell checks. Safety examples use `throw`, not `exit`.

```powershell
Set-Location -LiteralPath 'C:\Users\admin\Desktop\local-ai-workbench'
```

```powershell
git status --short
```

```powershell
$branch = git branch --show-current
$expectedHead = '<expected SHA from the current task>'
$head = (git rev-parse HEAD).Trim()
if ($branch -ne 'workflow-codex-task-discipline') { throw "Wrong branch: $branch" }
if ($head -ne $expectedHead) {
    throw "Wrong HEAD. Expected $expectedHead but found $head"
}
```

```powershell
& 'C:\Users\admin\tools\gh-portable\bin\gh.exe' auth status
```

```powershell
& 'C:\nvm4w\nodejs\codex.cmd' --version
```

```powershell
& 'C:\Users\admin\.venvs\lawb-workflow\Scripts\python.exe' --version
```

```powershell
if (-not (Test-Path -LiteralPath '.\scripts\local_dispatcher_v1.ps1' -PathType Leaf)) {
    throw 'Dispatcher script is missing.'
}
```

## 8. Current Manual Command

VERIFIED current baseline and future recovery command:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

Meaning:

- one explicit Issue
- one foreground run
- stops after the selected Issue
- success or failure can produce `LAWBRUNNER-RESULT` when the dispatcher reaches the result-publication path
- becomes recovery after Bridge Operator Phase B is operational

## 9. Supported Action Matrix

VERIFIED:

| Mode | Supported actions | Notes |
| --- | --- | --- |
| `PollOnce` | `maybe-status-check`, `run-reviewbundle` | `run-reviewbundle` delegates to Runner v1 ReviewBundle after Dispatcher validation and clean-repo preflight. |
| `BoundedPoll` | `maybe-status-check` only | Never imply BoundedPoll supports `run-reviewbundle`. |

RESERVED OR SEPARATE FLOWS:

- `run-reviewbundle-handoff`
- `read-final-audit`
- queue handoff behavior where already documented

SEPARATE APPROVAL / FORBIDDEN FOR AUTOMATIC CONTINUATION:

- stage
- commit
- push
- close
- labels
- PR
- merge
- force push
- approval consumption
- approval chaining

## 10. Failure And Troubleshooting Guide

| Case | Symptom | Likely cause | Safe response | Forbidden recovery behavior |
| --- | --- | --- | --- | --- |
| `gh` not on PATH | direct `gh` commands fail | shell PATH lacks GitHub CLI; Dispatcher or Runner fail only when no accepted candidate is available or authentication fails | on the verified course computer, use the full portable path for manual checks; Dispatcher and Runner resolve PATH, Program Files, or the verified portable path | do not bypass GitHub validation |
| expired `gh` authentication | `gh auth status` fails | token/session expired or restore-card reset | reauthenticate intentionally, then rerun readiness checks | do not store credentials in repo |
| `codex.ps1` versus `codex.cmd` | runner refuses PowerShell wrapper | only PowerShell wrapper resolved | use verified npm `codex.cmd` launcher | do not force direct `codex.ps1` execution |
| Codex missing | runner cannot resolve Codex command | Codex CLI not installed or not on PATH | install/repair intentionally, then rerun version check | do not switch to unbounded executor |
| Codex quota exhaustion | Codex exits nonzero or reports quota/provider failure | account quota/provider limit | record reviewable failure and stop | no repeated Codex retry storm |
| network outage | GitHub read/comment fails | network unavailable | determine whether failure happened before task execution, during task execution, or after execution but before GitHub result publication; preserve evidence before deciding next step | no blind Dispatcher / Runner / Codex rerun after network recovery; no infinite retry loop |
| dirty repo | `run-reviewbundle` stops before delegation | local changes exist | inspect and resolve intentionally | no auto-reset, no auto-stash, no auto-clean |
| wrong branch | branch check fails | repo not on expected branch | switch only after human review | do not run dispatch on wrong branch |
| wrong HEAD | dispatch marker does not match local HEAD | stale marker or changed repo state | ask ChatGPT to refresh marker after review | do not edit marker locally to force match |
| expired marker | dispatcher rejects marker | request expiry passed | ask ChatGPT to post a fresh request | do not ignore expiry |
| duplicate `request_id` | duplicate result detected | request already processed | treat idempotency stop as safety success | do not rerun to force a second result |
| malformed or duplicate marker | dispatcher fails closed | invalid or ambiguous `CHATGPT-DISPATCH` comments | correct marker through ChatGPT/GitHub review | no broad issue scan to find another task |
| result comment failure | local output exists but no GitHub result | GitHub writeback failed after local activity | inspect local stdout and stderr, determine whether the task already executed, preserve local evidence, and use the manual ChatGPT fallback when required | do not rerun execution solely to republish a GitHub comment; a future publish-only recovery path requires separate design and approval |
| PowerShell UTF-8 display problems | glyphs appear garbled in console | terminal encoding/font issue | verify file bytes/content before editing | do not "repair" Unicode as corruption without evidence |
| restore-card restart loss | tools/auth/logs disappear after restart | course computer state reset | rerun setup and readiness checks | do not assume prior local state survived |

General forbidden recovery examples:

- no auto-reset
- no auto-stash
- no force push
- no repeated Codex retry storm
- no broad issue scan

## 11. Local State And Future Logs

APPROVED DIRECTION, NOT IMPLEMENTED:

Future Bridge Operator Phase B local state should live outside the repo:

```text
%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator\
```

Planned files:

- `state.json`
- `processed_requests.jsonl`
- `operator.lock`
- `heartbeat.json`
- `operator.log`
- `last_failure.json`
- `pause.flag`
- `stop.flag`

These files are planned for Phase B. They are not currently implemented by this baseline document.

## 12. Verified Milestone Log

Do not infer that an Issue is closed from this table. Evidence labels describe the kind of local/supplied evidence recorded here.

| Evidence | Label | Summary |
| --- | --- | --- |
| #120 Runner v1 Codex CLI smoke | smoke | Runner v1 Codex CLI ReviewBundle smoke artifact recorded. |
| #121 Dispatcher `run-reviewbundle` implementation | implementation | Dispatcher v1 gained `run-reviewbundle` dispatch action. |
| #125 dispatcher-to-runner argument fix | fix | Dispatcher runner invocation argument passing corrected. |
| #127 failure-result publication fix | fix | Dispatcher result publication behavior fixed for runner failure cases. |
| #129 npm `codex.cmd` launcher support | fix | Runner v1 launcher resolution supports npm `codex.cmd`. |
| #131 Runner GitHub CLI fallback | fix | Runner GitHub CLI resolution supports PATH / Program Files / portable fallback. |
| #132 combined Runner launcher / gh fallback smoke | smoke | Combined Runner launcher and GitHub CLI fallback smoke recorded. |
| #122 Dispatcher GitHub CLI fallback | fix | Dispatcher GitHub CLI fallback path support added. |
| #133 Dispatcher portable gh fallback smoke | smoke | Dispatcher portable GitHub CLI fallback smoke recorded. |
| `16f6621` Bridge Operator v0 specification | governance | Bridge Operator v0 spec established. |
| `5306a86` Direction Lock v1.1 binding | governance | Direction Lock updated to v1.1 and bound to Bridge Operator spec. |
| `a85a289` B0-1 README / PLANS reconciliation | documentation | Product/workflow boundary reconciliation recorded. |
| `75c193f` B0-2 SOP / architecture reconciliation | documentation | Lv4.5 SOP and historical architecture reconciliation recorded. |

## 13. Current Integration Status

VERIFIED / DOCUMENTATION:

- B0-1 complete
- B0-2 complete
- B0-3 complete
- B0-4A complete
- B0-4B complete

B0 ISSUE CLEANUP:

- #120 completed
- #121 completed
- #125 completed
- #124 not planned
- #126 not planned

B0 reconciliation, verification, completed/superseded Issue cleanup, and PR #134 integration into `master` are complete.

The old boundary-layer expansion and local-repair loop is frozen. Current activity is Workflow Governance Reset through Issue #135. Issue #114 is historical roadmap evidence, not the active task source.

Bridge Operator Phase B implementation has not started. B1 requires a separately approved implementation task.

Manual `PollOnce` remains the verified current baseline and future recovery path, not the final daily UX. Phase C ChatGPT App / MCP remains deferred until Phase B is stable.

SEPARATE APPROVAL:

- B1 requires a separate approved implementation task

## 14. Conversation Handoff Rule

For future conversations:

- read Direction Lock
- read Bridge Operator spec
- read this baseline
- identify current phase
- identify current verified HEAD
- distinguish VERIFIED / APPROVED DIRECTION / DEFERRED / SEPARATE APPROVAL
- never treat manual `PollOnce` as final target UX
- never treat Bridge Operator as already implemented before evidence exists

## 15. Changelog

### v0.1 - 2026-06-12

Created the active operational baseline and handoff entrypoint for the verified semi-automated workflow, course-computer environment, commands, troubleshooting, milestone evidence, and approved Bridge Operator Phase B direction.

### B0 closeout - 2026-06-13

Recorded B0-4B completion, completed/superseded Issue cleanup state, and the remaining requirement for separate PR review and approval before integration into `master`.

### Governance Reset - 2026-06-14

Recorded Issue #135 as the active governance-reset entrypoint, classified
normative, operational, evidence / historical, and superseded material, and
clarified that Issue #114 is historical roadmap evidence only.
