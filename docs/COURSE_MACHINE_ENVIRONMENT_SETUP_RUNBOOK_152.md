# Course Machine Environment Setup Runbook (#152)

## 1. Purpose

This runbook records a repeatable setup flow for course machines, shared lab machines, and other temporary Windows environments used to run Codex tasks for this repository.

It focuses on safe setup for:

- `GITHUB_TOKEN` process visibility
- Codex environment checks
- repository sync checks
- local Git author identity
- end-of-session cleanup decisions

## 2. When To Use This Runbook

Use this runbook after each reset, reboot, restore-card refresh, machine handoff, or new VS Code / Codex session on a course machine.

Course machines with restore cards may lose local environment settings after reboot. Treat every new session as untrusted until the checks below pass.

## 3. Safety Rules

- Never commit, print, paste into ChatGPT, paste into Codex prompts, screenshot, or store any real token value in repository docs.
- Never save token values to repository files.
- Do not include actual private credentials in notes, issues, prompts, terminal output evidence, or screenshots.
- Do not use commands that print token values.
- If a token appears in terminal output or screenshots, revoke it and create a new token.
- This runbook does not authorize GitHub writeback, Result Packet write, runner, dispatcher, watcher, broad scan, issue close, label change, PR, or merge.

## 4. Daily Startup Checklist

From the repository root:

1. Confirm the repository is clean.
2. Confirm local `HEAD` matches `origin/master`.
3. Confirm the latest commit message matches the task's expected baseline.
4. Set a process-level `GITHUB_TOKEN` only when a task explicitly requires authenticated GitHub access.
5. Confirm Codex can see the process-level token before token-based tasks.
6. Confirm local Git author identity is configured before commit tasks.

## 5. Repository Sync Check

Before starting a task, run:

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/master
git log -1 --pretty=%B
```

Expected values must match the task instructions. If the working tree is dirty or the hashes do not match, stop and resolve the mismatch before continuing.

## 6. GitHub Token Setup

Use a process-level token for the current PowerShell session only when needed. This avoids storing the token in the repository or relying on machine-wide state.

Set process-level `GITHUB_TOKEN`:

```powershell
$secure = Read-Host "Paste GitHub token" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$env:GITHUB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
```

Do not save the token value in docs, scripts, Git config, shell history notes, issue comments, or prompt text.

## 7. Confirm Codex Can See GITHUB_TOKEN

Codex may run in a different process or user than the visible VS Code terminal. User-level environment variables may not be visible to Codex sandbox users.

The important check before token-based tasks is process-level visibility:

```powershell
if ($env:GITHUB_TOKEN) { "process GITHUB_TOKEN is set" } else { "process GITHUB_TOKEN is missing" }
```

Optional user-level presence check without printing the value:

```powershell
if ([Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")) { "user GITHUB_TOKEN is set" } else { "user GITHUB_TOKEN is missing" }
```

If the process-level check reports missing, do not run authenticated tasks until the process environment is corrected.

## 8. Local Git Author Identity Setup

For temporary or shared machines, prefer local repository Git config, not global config.

Use the latest existing commit author identity:

```powershell
$authorName = git log -1 --format="%an"
$authorEmail = git log -1 --format="%ae"

if (-not $authorName -or -not $authorEmail) {
    "author_identity_missing_from_previous_commit"
    exit 1
}

git config user.name "$authorName"
git config user.email "$authorEmail"
```

Do not use `git config --global` on shared or course machines unless that is explicitly intended by the machine owner and the task.

## 9. Before Running Strict Lane Tasks

Before any strict lane task:

- Read the task boundary carefully.
- Verify the allowed file list.
- Confirm no unrelated files are dirty.
- Confirm the required `HEAD`, `origin/master`, and latest commit message.
- Confirm process-level `GITHUB_TOKEN` only when the task requires it.
- Avoid broad scans, latest issue inference, alternate references, and any unapproved GitHub writeback.

## 10. After Running Codex Tasks

After a Codex task:

- Check `git status --short`.
- Confirm only approved files changed.
- Review staged files before commit.
- Confirm no token value was written to docs or stdout evidence.
- Commit and push only when the task explicitly permits it.
- Do not create PRs, merge, close issues, change labels, or write GitHub comments unless the task explicitly authorizes those actions.

## 11. End-of-Session Shutdown Checklist

Before leaving a course machine, run:

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/master
git log -1 --pretty=%B
```

Confirm `HEAD` equals `origin/master`.

If the working tree is dirty before leaving, do not rely on the course machine to preserve it. Either finish the approved commit/push flow, save work through an approved non-secret channel, or document the blocker before ending the session.

## 12. Home PC vs Course Machine Notes

Home machines may preserve environment variables, Git config, and local working files across reboots. Course machines with restore cards may not.

On course machines:

- Recheck environment state every session.
- Prefer process-level secrets over persistent machine configuration.
- Prefer local repo Git config over global Git config.
- Assume unsaved local changes may be lost after reboot or reset.

## 13. Common Failure Cases

- `process GITHUB_TOKEN is missing`: set the process-level token in the same session Codex can use.
- `user GITHUB_TOKEN is set` but process token is missing: the User-level variable may not be visible to the Codex process or sandbox user.
- Git commit fails with missing author identity: configure local repository `user.name` and `user.email` from the latest commit.
- `HEAD` does not equal `origin/master`: stop and resolve the sync mismatch before running task-specific work.
- Working tree is dirty before task start: stop and inspect the changed files before proceeding.
- Token appeared in terminal output or screenshots: revoke it and create a new token.

## 14. Final Boundary Statement

This runbook is a support document for safe course-machine setup. It does not implement code, tests, dependencies, runner behavior, dispatcher behavior, watcher behavior, broad issue scans, autonomous execution, GitHub writeback, Result Packet writes, issue close, label changes, PR creation, or merge behavior.
