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

`setup`, `verify`, `start`, and `recover` reject a state root equal to or below the LAWB
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
- `requests\<request_id>\runner_process_evidence.json`: immutable,
  parent-owned process facts written before Runner machine evidence is trusted;
- `processed_requests.jsonl`: durable request-id replay protection;
- `replay_tombstones\<request_id>.json`: permanent replay prohibition for an
  exactly recovered uncertain request;
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

## Exact uncertain-incident recovery

`recover` is an explicit, offline, local-only action for one reviewed
`delegating_runner` incident. Manual deletion of `in_flight.json` is forbidden:
deleting it before durable replay prohibition creates a window in which the old
request could be delegated again.

The action requires four reviewed incident identity values plus three explicitly
reviewed protected repository roots. It does not infer a latest request, scan
for an incident, read GitHub, invoke Runner or Codex, render HGW output, run
pytest, or mutate a repository:

```powershell
.\scripts\display_pilot.ps1 `
  -Action recover `
  -StateRoot "<reviewed-state-root-outside-git-worktrees>" `
  -RequestId "<exact-old-request-id>" `
  -TargetIssue <exact-target-issue> `
  -InFlightSha256 "<exact-reviewed-sha256>" `
  -LawbRoot "<reviewed-LAWB-checkout>" `
  -HgwRoot "<reviewed-HGW-checkout>" `
  -TargetRepoRoot "<reviewed-HAG-checkout>"
```

Recovery requires all three explicitly reviewed protected repository roots in
addition to the four incident identity values. It rejects StateRoot equal to or
beneath LAWB, HGW, HAG, or the control checkout. Before acquiring its lock or
mutating any recovery path, it resolves the lock, in-flight, processed record,
request, snapshot, incident, tombstone-store, tombstone, and owned pending paths.
Every resolved path must remain within StateRoot and outside every protected
root; symlink, junction, reparse-point, or equivalent escapes fail closed.

Recovery then acquires the normal exclusive operator lock and verifies the
exact in-flight bytes, request ID, target Issue, `delegating_runner` state,
timestamp, R1 request-directory inventory, processed-record exclusion, and
absence of conflicting recovery evidence. A valid
`runner_process_evidence.json` is a recognized incident artifact: recovery
validates its protocol and request identity, records it in the observed
inventory, and preserves its exact bytes. Malformed, mismatched, conflicting,
or unknown request artifacts fail closed. Process evidence alone never changes
the incident outcome from `uncertain`. Recovery performs this fixed ordering:

1. atomically preserve the exact original bytes at
   `requests\<request_id>\original_in_flight.json`;
2. atomically write the versioned uncertain incident at
   `requests\<request_id>\recovery_incident.json`;
3. atomically write the permanent replay tombstone at
   `replay_tombstones\<request_id>.json`;
4. reread and exactly verify all three records;
5. only then remove the active `in_flight.json`.

The outcome remains `uncertain`. Recovery does not claim success, definite
failure, that Runner or Codex started, or that either definitely did not start.
It does not add an entry to `processed_requests.jsonl`.

An interrupted recovery may be rerun with the same four reviewed values only
when no `operator.lock` remains. A controlled Python exception follows normal
lock cleanup, after which exact pre-existing phases can be verified and reused
without changing historical timestamps. A tombstone present while
`in_flight.json` remains allows such a controlled rerun to complete the final
release safely. If in-flight is absent, all three exact recovery records must
already exist; otherwise the state remains fail closed. Conflicting or partially
unrecognized evidence is never overwritten or repaired automatically.

Each recovery-owned canonical write first uses one deterministic `.pending`
file. After the snapshot and incident are durable, recovery creates the bounded
`replay_tombstones` directory and immediately re-resolves the directory,
canonical tombstone, and pending tombstone paths. They must remain beneath
StateRoot, outside every protected root, and the store must remain a directory
before use. Exact pending records left by a controlled interruption can be
verified and promoted on the next invocation. The durable incident timestamp is
preserved, and the tombstone must use that exact timestamp. Arbitrary
temporary-looking files, malformed or conflicting pending content, and
conflicting canonical records remain fail closed. `in_flight.json` is not
removed until the canonical snapshot, incident, and tombstone have all been
reread and verified.

A genuine process death may leave `operator.lock`. An existing lock always
blocks recovery as `active_lock_present`: R1 does not inspect PID ownership,
infer liveness, promote pending records, or remove, rename, overwrite, or
reclaim the lock. Stale-lock inspection or removal requires a separately
reviewed procedure and separate approval. Therefore R1 does not claim automatic
hard-process-death recovery.

The old request ID is permanently replay-prohibited and is treated as stale by
`start`. Recovery does not authorize a new live request. A later supervised
cycle requires a different request ID and separate approval.

R1 supports only the exact `delegating_runner` shape and its bounded known
request-directory artifacts, including an optional valid
`runner_process_evidence.json`. It does not establish what historically
happened inside Runner or Codex, and it does not recover other state shapes.
Implementation tests use temporary StateRoots only; they do not authorize or
perform recovery against the real StateRoot or authorize a new live request.

## Evidence

Runner is invoked only with `MachineEvidencePath`, `DisplayPilotRequestId`, and
`SuppressReviewBundleComment`. The request-directory name, selector request ID,
Runner argument, and machine-evidence request ID must be identical. The Runner
writes UTF-8 JSON through a same-folder replacement and does not post its normal
ReviewBundle comment on that path.

The Operator separately owns
`requests\<request_id>\runner_process_evidence.json`. The CLI captures Runner
stdout and stderr as raw bytes without implicit decoding. After the process
returns, times out, or fails to launch, the parent records exact process
start/exit/timeout/exception facts, byte counts and SHA-256 values, and a
deterministic preview bounded to 4,096 source bytes per stream. Invalid UTF-8 is
decoded only for that bounded preview with replacement explicitly reported.
The parent also records whether the expected machine-evidence file was
observed, plus its size and hash when present.

Process evidence uses protocol
`lawb.display_pilot.runner_process_evidence.v1`, schema version 1, a
same-directory temporary file, atomic replacement, and mandatory readback
validation. Its canonical path is immutable. A pre-existing file, write or
readback failure, launch failure, timeout, missing machine evidence, or rejected
machine evidence retains `in_flight.json` and does not create processed,
canonical, rendered, or retry output. Process evidence reports process facts
only: it does not claim that Codex started or completed, pytest ran, repository
mutation occurred, the HAG task succeeded, or external effects were absent.

Parent verification begins only after process evidence is durable and Runner
machine JSON is independently readable and valid. The machine evidence remains
the authority for child/task claims, and its final HEAD, staged-state, and
changed-file evidence must exactly match a fresh parent Git observation.
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

- `runner_process_evidence.json`;
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
timeout. A timeout is not retried, preserves any partial raw stdout/stderr in
process evidence, and leaves `in_flight.json` for explicit uncertain-state
review. Exit 0 without machine evidence blocks as
`runner_machine_evidence_missing`; nonzero exit without it blocks as
`runner_nonzero_exit_without_machine_evidence`; launch failure blocks as
`runner_process_launch_failed`; timeout blocks as `runner_timeout`; and process
evidence persistence failure blocks as
`runner_process_evidence_write_failed`. The PowerShell wrapper uses the
repository venv with an explicit process-local `src` import path; it does not
install the package or change persistent `PATH` or `PYTHONPATH`.

The candidate does not stage, commit, push, create or merge a PR, close an Issue,
edit labels, broaden an Issue scan, infer a latest/next task, consume approval,
run in the background, install startup behavior, change credentials, or grant
authority from transport prose or rendered text.

Known limitations:

- no supervised live DP4 chain or actual GitHub result publication is proven;
- no background, startup, service, tray, or automatic permanent action exists;
- uncertain recovery is explicit, exact-bound, local-only, and fail-closed;
- parallel multi-host safety and universal cross-platform behavior are not
  claimed;
- this candidate does not establish production cutover or complete Independent
  Workflow v1.0.
