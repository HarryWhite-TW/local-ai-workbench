# Course-Computer Environment Recovery

This is bounded environment support for restore-card or temporary course
computers. It does not expand Bridge Operator authority and does not create a
background service, startup task, secrets file, or second setup framework.

## Daily Quick Restore Entry

For the compressed daily reset workflow, start with:

    docs/COURSE_HOST_QUICK_RESTORE_RUNBOOK.md

That runbook is the preferred short-path entry for routine course-computer resets. This file remains the detailed recovery reference.
## 2026-07-08 Incident Note

The 2026-07-08 course-host restore succeeded, but it took too many manual
iterations. The repository already had recovery assets, yet the process started
with broad read-only discovery instead of the bootstrap manifest/script
contract, produced long terminal output that was easy to truncate, and drifted
into unnecessary virtual-environment activation confusion.

The corrected recovery guidance is to keep the flow short, evidence-producing,
and bounded. Treat this as engineering recovery guidance, not a complaint about
the host or tooling.

What went wrong:

- broad discovery happened before reading the bootstrap manifest and script;
- terminal output was too large and got truncated;
- manual venv activation was attempted even though the reviewed absolute Python
  path was sufficient;
- `bootstrap_course_environment.ps1 -Apply` partially succeeded but surfaced an
  unclear `unexpected_bootstrap_failure`;
- Host Check was stricter than bootstrap `READY`;
- Bash heredoc syntax was mistakenly used in a PowerShell context;
- `$Host` was mistakenly used as a variable name even though PowerShell reserves
  it as a read-only automatic variable.

## REC-02 Complete Recovery v2

Run the review wrapper from a visible PowerShell window:

```powershell
.\scripts\course_environment_restore_review.ps1 `
    -RepoRoot "C:\Users\admin\Desktop\local-ai-workbench" `
    -ExpectedBranch "master" `
    -ExpectedHead "<reviewed-full-head>" `
    -CompleteRecovery
```

The intended path is:

```text
initial audit
-> conditional restore only when Layer 1 is not READY
-> fresh post-audit and stale-failure reconciliation
-> current-process reviewed PATH and repo-local identity hygiene
-> conditional browser GitHub authentication, auth recheck, and repository read
-> focused tests, Host Check, compact result
-> STOP before live acceptance
```

Audit-only mode remains read-only. Complete recovery never persists PATH, changes global Git identity, performs GitHub writes, or invokes live Bridge runtime.

The wrapper writes long command output to an evidence root and prints only a
concise summary: evidence paths, Layer 1 restore status, Layer 2 Host Check
status, Layer 3 drift reasons, and a stop marker.

Do not manually activate the venv during recovery. Use the reviewed Python
absolute path, such as:

```powershell
.\.venv-course\Scripts\python.exe
```

If the wrapper or bootstrap reports a failed action and stage, inspect the JSON
diagnostics first. Perform focused repair only for that failing area.

## Readiness Layers

Layer 1: Tool restore readiness.

Bootstrap `READY` means the tools and dependencies were restored according to
the manifest contract. It does not prove operational host acceptance.
Bootstrap READY differs from Host Check READY.

Layer 2: Operational Host Check readiness.

Host Check `READY` means the stricter RV2-03 host harness accepted the current
repository state, reviewed paths, fresh-shell visibility, authentication checks,
and safety assertions.

Layer 3: Hygiene and drift items.

Some findings are local host setup or drift items rather than bootstrap restore
failures. Examples include PATH or fresh-shell visibility drift and `.gitignore`
coverage for `.venv-course`.

`git_identity_missing` is a local host setup issue. Recovery scripts must not silently set `git config user.name` or `git config user.email`. The user should make that host-local decision visibly when needed.

PATH and fresh-shell drift should be presented separately from tool usability.
A tool may be usable through the reviewed absolute path while still differing
from current-process or fresh-shell PATH resolution.

## Legacy One Command

Run from the repository root in a visible PowerShell window:

```powershell
.\scripts\restore_course_computer_environment.ps1
```

The script must be started from the real `HarryWhite-TW/local-ai-workbench` Git
repository root. It rejects another repository and rejects repository
subdirectories.

Use `-AssumeYes` only when you already understand the installs and want the
script to proceed through its prompts.

## What It Installs

The script installs only when a required tool is missing and the user confirms:

- portable GitHub CLI at `%USERPROFILE%\tools\gh-portable\bin\gh.exe`, downloaded
  from the official `cli/cli` GitHub release assets;
- the official npm package `@openai/codex`, using `npm install -g @openai/codex`.

Known limitation: automatic portable-GH installation calls the official GitHub
latest-release API to discover release assets. A shared-IP rate limit may
prevent automatic asset discovery, and the script currently has no automatic
fixed-asset fallback. The safe response is to stop and use a reviewed official
manual fallback rather than guessing or downloading from an unreviewed source.

## What It Only Verifies

The script verifies and reports:

- current branch, HEAD, and working-tree state;
- Git, Node.js, and npm presence and versions;
- GitHub CLI version and authentication status, including rerunning
  `gh auth status` after interactive login and reporting `gh=ready` only when
  the native exit code passes;
- a native Codex launcher and version, preferring `.exe`, then `.cmd`, then
  `.bat`, then another non-`.ps1` application.

The script never reports `codex.ps1` alone as ready. Failed version checks or
failed readiness checks are summarized as blocked and stop the script rather
than being reported as ready.

`codex --version` success proves only that the reviewed launcher can run a
version probe. It does not prove interactive ChatGPT sign-in.

It does not invoke Dispatcher, Runner, Codex tasks, commits, pushes, Issue
close, labels, PRs, merges, or approvals.

## Primary Operational Host And Secondary Compatibility Host

The course Windows computer was the user-designated Primary Operational Host for RV2-03, whose formal acceptance is complete. REC-02 remains recovery tooling, not live Bridge authority.

The home Windows computer is a Secondary Compatibility Host. It may retain
GitHub CLI auth, Codex sign-in, local logs, and operator state, but its additional
evidence does not block RV2-03 completion.

The restore-card course computer remains ephemeral. Do not assume it keeps
authentication, installed Codex, portable GitHub CLI, Python environment,
startup tasks, local operator state, or logs after reboot.

After every reset or restore, rerun environment recovery and readiness checks.
Missing local operator state must not be interpreted as proof that a request has not run. The accepted RV2-03 contract proved durable reconciliation and duplicate suppression; REC-02 does not invoke that runtime path.

## Manual Fallback Steps

If the script stops:

1. Install Git for Windows.
2. Install Node.js LTS with npm.
3. Install GitHub CLI manually or place `gh.exe` at
   `%USERPROFILE%\tools\gh-portable\bin\gh.exe`.
4. Run `gh auth login --web` in a visible terminal.
5. Rerun `gh auth status` and confirm it exits successfully.
6. Run `npm install -g @openai/codex` if a native Codex launcher is absent.
7. Launch Codex once manually for interactive ChatGPT sign-in.

Manual `PollOnce` remains a recovery path only after the relevant bridge
authority allows it:

```powershell
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> -PostResultComment
```

## Known Tool Paths

- Portable GitHub CLI:
  `%USERPROFILE%\tools\gh-portable\bin\gh.exe`
- GitHub CLI installed by the official installer:
  `%ProgramFiles%\GitHub CLI\gh.exe`
- npm global Codex launcher:
  a PATH-visible native `codex.exe`, `codex.cmd`, `codex.bat`, or other
  non-`.ps1` application

## Shared-Computer Logout Checklist

Before leaving a shared or course computer:

1. Run `gh auth logout` and confirm the account is removed.
2. Sign out of Codex / ChatGPT sessions used by the launcher.
3. Sign out of browser GitHub, ChatGPT, and related identity-provider sessions.
4. Close all terminal and browser windows.
5. Reboot if the course process requires it.

A restore card does not replace explicit logout. Browser sessions and CLI
credentials can remain active until the machine is actually restored.

## Authority Boundary

This recovery script is environment support tooling only. It must not be treated
as Bridge Operator authority, approval, a production installer, a startup
mechanism, or permission to run B2/B3 behavior.
