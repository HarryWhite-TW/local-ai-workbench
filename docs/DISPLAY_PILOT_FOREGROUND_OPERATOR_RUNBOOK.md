# Display Pilot Foreground Operator Candidate

## Candidate status

DP4-BR is a non-live foreground candidate. It binds one fixed selector,
`HarryWhite-TW/human-governed-workflow#1`, to one explicit OPEN Issue in
`HarryWhite-TW/human-approval-automation-gateway`. The target body must contain
exactly one canonical LAWB Task Packet v1.1. Selector prose and rendered reports
do not grant authority.

This node did not start the Bridge, read or write a live GitHub task, invoke the
real Runner or Codex, publish a result, or perform a supervised live chain.

## Local state

Choose a state directory outside every Git worktree. The recommended Windows
location is:

```text
%LOCALAPPDATA%\LocalAIWorkbench\DisplayPilot\
```

`setup`, `verify`, and `start` reject a state root equal to or below the LAWB
control checkout, the supplied HAG checkout, or the pinned HGW checkout. Path
containment is normalized and case-insensitive on Windows.

`setup` requires explicitly reviewed LAWB, HGW, and HAG roots so it can apply
the complete StateRoot exclusion without scanning for repositories. It fails
closed if any protected root is omitted, then idempotently creates only the
state root and its `requests` directory:

```powershell
.\scripts\display_pilot.ps1 `
  -Action setup `
  -StateRoot "$env:LOCALAPPDATA\LocalAIWorkbench\DisplayPilot" `
  -LawbRoot "C:\Users\admin\Desktop\local-ai-workbench" `
  -HgwRoot "C:\Users\admin\Desktop\human-governed-workflow" `
  -TargetRepoRoot "C:\path\to\human-approval-automation-gateway"
```

Runtime state is local and includes:

- `operator.lock`: exclusive foreground-owner lock;
- `heartbeat.json`: current bounded polling cycle;
- `pause.flag` and `stop.flag`: checked before every selector read;
- `in_flight.json`: written before Runner delegation and retained after an
  uncertain interruption;
- `processed_requests.jsonl`: durable request-id replay protection;
- `requests\<request_id>\`: canonical and rendered request evidence.

An unresolved `in_flight.json`, active lock, corrupt processed record, or invalid
Task Surface fails closed. An already processed selector is stale/idle: it is
not rerun, and the bounded foreground loop keeps polling for a new request. The
operator does not silently retry an uncertain Runner execution.

## Read-only verification

`verify` does not create the state directory and does not invoke GitHub, Runner,
or Codex. Supply reviewed absolute paths for every later start dependency:

```powershell
.\scripts\display_pilot.ps1 `
  -Action verify `
  -StateRoot "$env:LOCALAPPDATA\LocalAIWorkbench\DisplayPilot" `
  -LawbRoot "C:\Users\admin\Desktop\local-ai-workbench" `
  -LawbBranch "dp4-b-foreground-operator" `
  -LawbHead "2705db84b16fdeae9cdc4ebf6e1edb77303fa7d6" `
  -HgwRoot "C:\Users\admin\Desktop\human-governed-workflow" `
  -TargetRepoRoot "C:\path\to\human-approval-automation-gateway" `
  -PythonPath "C:\Users\admin\Desktop\local-ai-workbench\.venv-course\Scripts\python.exe" `
  -PowerShellPath "C:\Program Files\PowerShell\7\pwsh.exe" `
  -GhPath "C:\Program Files\GitHub CLI\gh.exe" `
  -CodexPath "C:\reviewed\codex.cmd" `
  -RunnerPath "C:\Users\admin\Desktop\local-ai-workbench\scripts\local_runner_v1.ps1"
```

Verification checks the LAWB and HAG Git roots, exact origins, clean HAG
worktree and staged area, the supplied exact LAWB branch and full HEAD, the
empty LAWB staged area, the pinned clean HGW checkout at
`main@19ef3e0dfcc364b3d90557747db964f919fc6afc`, the canonical Runner path,
and each explicitly reviewed executable path.

The default LAWB expectation is a clean checkout. A separately reviewed dirty
candidate can enumerate its exact expected tracked modifications by repeating
`-LawbExpectedModifiedFile <repository-relative-path>`; untracked or staged
paths still fail closed.

## Future supervised foreground start

The following is the candidate interface for a later separately reviewed live
package. It was not executed in DP4-BR:

```powershell
.\scripts\display_pilot.ps1 `
  -Action start `
  -StateRoot "$env:LOCALAPPDATA\LocalAIWorkbench\DisplayPilot" `
  -LawbRoot "C:\Users\admin\Desktop\local-ai-workbench" `
  -LawbBranch "dp4-b-foreground-operator" `
  -LawbHead "2705db84b16fdeae9cdc4ebf6e1edb77303fa7d6" `
  -HgwRoot "C:\Users\admin\Desktop\human-governed-workflow" `
  -TargetRepoRoot "C:\path\to\human-approval-automation-gateway" `
  -PythonPath "C:\Users\admin\Desktop\local-ai-workbench\.venv-course\Scripts\python.exe" `
  -PowerShellPath "C:\Program Files\PowerShell\7\pwsh.exe" `
  -GhPath "C:\Program Files\GitHub CLI\gh.exe" `
  -CodexPath "C:\reviewed\codex.cmd" `
  -RunnerPath "C:\Users\admin\Desktop\local-ai-workbench\scripts\local_runner_v1.ps1" `
  -MaxCycles 100 `
  -PollIntervalSeconds 5
```

The process remains visible and foreground-only. It polls at most the configured
cycle count, sleeps between empty cycles, reads only the fixed selector and its
explicit target Issue, and processes at most one request. A fixed selector Issue
with no occurrence of the DP4-B selector label safely waits for the next cycle.
If the label or an opening labelled fence is present but no single complete
labelled selector can be parsed, the cycle fails closed. An already processed
selector is ignored while polling for a new request. Multiple complete labelled
selectors and malformed labelled selectors also fail closed.

Create `pause.flag` to stop at the next cycle with a reviewable blocked result.
Create `stop.flag` for the same bounded stop behavior. If the process is killed,
do not delete `in_flight.json` merely to resume: inspect the prior Runner and
durable result state under a separately reviewed recovery procedure.

## Evidence

Runner is invoked only with `MachineEvidencePath`, `DisplayPilotRequestId`, and
`SuppressReviewBundleComment`. The request-directory name, selector request ID,
Runner argument, and machine-evidence request ID must be identical. The Runner
writes UTF-8 JSON through a same-folder replacement and does not post its normal
ReviewBundle comment on that path. Parent verification begins only after this
JSON is readable and valid and its final HEAD, staged-state, and changed-file
evidence exactly match a fresh parent Git observation.
The schema is complete and type-checked, including every required safety flag;
missing flags are not filled from HGW defaults. Suppression evidence must say
the comment was suppressed and no GitHub comment was posted. The selected Task
Packet, runtime binding, and embedded runtime contract `allowed_files` must be
the same canonical normalized exact set: order, slash direction, and accepted
leading `./` spelling do not create false mismatches, while duplicates, unsafe
paths, missing paths, and additional paths fail closed. Blocked Runner evidence
must carry at least one explicit non-empty string reason; the Operator and HGW
renderer do not invent a reason for incomplete evidence.

The ordinary Runner path, when neither opt-in flag is present, posts the
existing ReviewBundle directly and does not construct or parse Display Pilot
machine evidence. If machine evidence is requested without suppression, the
comment result is observed before the sole canonical evidence write so a
successful post cannot leave a stale record claiming no GitHub write.

Each completed request directory contains:

- `runner_machine_evidence.json`;
- `canonical_evidence.json`;
- `result_surface.json`;
- `reviewer_report.md`;
- `plain_language_zh_TW.md`;
- exactly one `result_comment_candidate.md`;
- `operator_summary.json`.

The Result Surface, reviewer report, and zh-TW report derive from the same
canonical evidence. The local comment candidate is not published automatically.

## Fail-closed and authority boundary

Only one or two explicit commands equivalent to
`python -m pytest <repository-relative arguments>` are accepted. Parent
verification uses the reviewed absolute Python executable, `shell=False`, the
explicit HAG root as `cwd`, bounded output, and a finite timeout. A nonzero result
produces `status=blocked`.

Only a small pytest option allowlist is accepted. `--pyargs`, arbitrary plugins,
basetemp/config/root redirection, absolute selectors, traversal, shell syntax,
`--collect-only`, and selectors outside `tests/` are rejected. Git HEAD, staged
paths, complete short status, effective changed paths, and a worktree fingerprint
are captured at the Runner-to-parent handoff and before/after runtime
verification. A handoff mismatch skips pytest and blocks with both observations
preserved. Any parent-test mutation also blocks and is included in canonical
evidence.

Runner invocation uses the reviewed PowerShell path, passes the reviewed
GitHub CLI path into Runner as its actual binding, and has a 1,500-second parent
timeout. A timeout is not retried and leaves `in_flight.json` for explicit
uncertain-state review. The PowerShell wrapper uses the repository venv with an
explicit process-local `src` import path; it does not install the package or
change persistent `PATH` or `PYTHONPATH`.

The candidate does not stage, commit, push, create or merge a PR, close an Issue,
edit labels, broaden an Issue scan, infer a latest/next task, consume approval,
run in the background, install startup behavior, change credentials, or grant
authority from transport prose or rendered text.

Known limitations:

- no supervised live DP4 chain or actual GitHub result publication is proven;
- no background, startup, service, tray, or automatic permanent action exists;
- uncertain recovery is fail-closed rather than automatic;
- parallel multi-host safety and universal cross-platform behavior are not
  claimed;
- this candidate does not establish production cutover or complete Independent
  Workflow v1.0.
