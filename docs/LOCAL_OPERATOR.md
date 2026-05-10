# No-Agent Local Operator Workflow

## Purpose

The no-agent local operator workflow is the repo's deterministic, local-only way to create a review package without asking an external agent to operate the repository.

It is for a human operator running one explicit PowerShell command from the repo root, then giving the generated report package to ChatGPT or another human reviewer for inspection.

This workflow is documentation and review support only. It does not replace the project's preview-before-approve rule, and it does not authorize any write-like action beyond local report artifact creation.

## Why OpenClaw Is Not The Repo Operator
OpenClaw can still be useful for local chat, drafting, and low-risk experiments.

It is not currently trusted as the repository command operator because the earlier validation did not prove real command execution in the repo. For this project, repo operation must be deterministic, auditable, and tied to commands whose behavior can be inspected after the run.

The validated baseline is instead:

```text
7923dc4 Avoid Git top-level path normalization
```

At that baseline, `scripts/local_operator.ps1 -Mode Report` is the first validated no-agent local operator slice.

## Report Mode
Run Report mode from the repo root:

```powershell
.\scripts\local_operator.ps1 -Mode Report
```

Report mode creates a timestamped local artifact directory:

```text
data/local-operator-runs/<timestamp>-Report/
```

The required files in that directory are:

- `summary.md`
- `metadata.json`
- `commands.jsonl`
- `transcript.txt`
- `git-before.txt`
- `git-after.txt`
- `diff-stat-before.txt`
- `diff-stat-after.txt`
- `no-files-modified.txt`

## What Report Mode Does

Report mode records a local review package for the current repository state. It captures command records, transcript output, before/after git status information, before/after diff stats, metadata, and a marker that tracked source files were not modified by the operator run.

The artifacts are meant to make the local run reviewable by ChatGPT or a human reviewer without granting either one repository control.

## What Report Mode Does Not Do

Report mode does not modify tracked source files. It does not stage, commit, push, create a branch, close an issue, edit labels, create a pull request, merge, or run any approval/commit flow.

It also does not delegate to a runner, install dependencies, require an API key, call a paid API, start a daemon, schedule background work, clean the repo, reset state, stash changes, or revert changes.

## Reviewer Inspection

After a run, inspect the generated directory under:

```text
data/local-operator-runs/<timestamp>-Report/
```

Recommended review order:

1. Read `summary.md` for the run overview.
2. Read `metadata.json` for structured run metadata.
3. Read `commands.jsonl` and `transcript.txt` to confirm exactly what was executed and recorded.
4. Compare `git-before.txt` with `git-after.txt`.
5. Compare `diff-stat-before.txt` with `diff-stat-after.txt`.
6. Confirm `no-files-modified.txt` exists.

If Git top-level output is mojibake in this environment, treat it as diagnostic-only and use the PowerShell-resolved repo root as the trusted filesystem path.

## Cleanup Rule

Local operator run artifacts are review outputs, not source files. Do not commit files under:

```text
data/local-operator-runs/
```

Leave report packages local unless a human explicitly asks for a selected excerpt or summary.

## Safety Boundaries

The Report-mode boundary is intentionally narrow:

- no user-supplied command execution
- exact internal git command allowlist only
- no runner delegation
- no stage, commit, push, issue close, label edit, PR creation, or merge
- no daemon, scheduler, or background service
- no dependency install, API key, or paid API
- no clean, reset, stash, or revert

These boundaries keep the operator as a local report generator, not a repository automation system.

## Windows Path Caveat
On Windows, especially with OneDrive and Chinese path segments, this command may print mojibake:

```powershell
git rev-parse --show-toplevel
```

For this workflow, the PowerShell-resolved repo root is the trusted filesystem path. Git top-level stdout is diagnostic-only and must not be used as the canonical path when it disagrees with the resolved PowerShell path.
