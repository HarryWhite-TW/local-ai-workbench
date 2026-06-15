# Course-Computer Environment Recovery

This is bounded environment support for restore-card or temporary course
computers. It does not expand Bridge Operator authority and does not create a
background service, startup task, secrets file, or second setup framework.

## One Command

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

It does not invoke Dispatcher, Runner, Codex tasks, commits, pushes, Issue
close, labels, PRs, merges, or approvals.

## Home Computer Versus Course Computer

The home computer is the expected persistent Bridge Host. It may retain GitHub
CLI auth, Codex sign-in, local logs, and operator state.

A restore-card course computer is a fallback environment. Do not assume it keeps
authentication, installed Codex, portable GitHub CLI, Python environment,
startup tasks, local operator state, or logs after reboot.

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
