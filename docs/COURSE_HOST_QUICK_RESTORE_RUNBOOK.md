# Course Host Quick Restore Runbook

## Purpose

This runbook defines the short daily recovery path for reset or restore-card course Windows computers.

It exists because course-host recovery is a recurring operational workflow, not an occasional troubleshooting event.

Normal target: one approved complete-recovery package, one repository-native command, conditional browser interaction only if needed, then paste the compact result back for ChatGPT adjudication. The command stops before live acceptance, Dispatcher, Runner, Codex task, or GitHub write.

## When To Use

Use this runbook when the user asks to quickly restore the course computer after a reboot or restore-card reset.

Do not begin with broad discovery unless the quick-restore path fails.

## Non-Authorization

This runbook does not authorize:

- source, test, or script changes;
- dependency or tool installation;
- `-Apply`;
- `-PersistUserPath`;
- permanent PATH changes;
- GitHub write;
- commit, push, PR, merge, Issue mutation, labels, milestones, or assignees;
- live Bridge acceptance;
- Dispatcher, Runner, PollOnce, or Codex runtime task execution;
- RV2-04, OPT-06, or later Roadmap activation.

## Daily Quick Restore: Complete Recovery

From the repository root:

    Set-Location "C:\Users\admin\Desktop\local-ai-workbench"

    $expectedHead = git rev-parse HEAD
    $evidenceRoot = "$env:TEMP\lawb-course-quick-restore-audit"

    Remove-Item -LiteralPath $evidenceRoot -Recurse -Force -ErrorAction SilentlyContinue

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\course_environment_restore_review.ps1 `
        -RepoRoot "C:\Users\admin\Desktop\local-ai-workbench" `
        -ExpectedBranch "master" `
        -ExpectedHead $expectedHead `
        -EvidenceRoot $evidenceRoot `
        -CompleteRecovery

    Write-Output "===== wrapper exit ====="
    Write-Output $LASTEXITCODE

    Write-Output "===== summary json ====="
    Get-Content -Raw "$evidenceRoot\course_environment_restore_review_summary.json"

    Write-Output "===== final git state ====="
    git status --short
    git rev-parse HEAD
    git rev-parse origin/master
    git rev-list --left-right --count HEAD...origin/master

Expected normal result:

    Layer 1 restore status: READY
    Layer 2 Host Check status: READY
    Layer 3 drift reasons: none
    wrapper exit: 0
    working tree: clean
    HEAD == origin/master
    divergence: 0 0

## Decision Rules

### Case A: Layer 1 READY and Layer 2 READY

Stop. The course host is ready.

Do not run `-Apply`.

### Case B: Layer 1 READY but Layer 2 BLOCKED by Git identity or PATH drift

Use the Host Hygiene Repair path.

This may set repo-local Git identity and current-process PATH only.

It must not use:

    git config --global
    -PersistUserPath
    -Apply

### Audit-Only Mode

Omit `-CompleteRecovery` to run the read-only audit path. It creates no venv, installs nothing, changes no Git identity or PATH, and does not start browser authentication.

### Case D: GitHub authentication is missing

Do not run `gh auth login` unless explicitly approved.

Authentication repair is a separate user-visible operation.

### Case E: Codex launcher check is confusing

Prefer the reviewed launcher path:

    & "C:\Users\admin\AppData\Local\LocalAIWorkbench\npm\codex.cmd" --version

Do not rely only on bare `codex`, because PowerShell may resolve `codex.ps1`.

## Host Hygiene Repair

Use only after audit shows Layer 1 READY but Host Check is blocked by local hygiene drift.

    Set-Location "C:\Users\admin\Desktop\local-ai-workbench"

    git config --local user.name "HarryWhite-TW"
    git config --local user.email "harry061892@gmail.com"

    $reviewedGhDir = "C:\Users\admin\AppData\Local\LocalAIWorkbench\gh\current"
    $reviewedCodexDir = "C:\Users\admin\AppData\Local\LocalAIWorkbench\npm"

    $pathParts = @($env:PATH -split ";" | Where-Object { $_ })
    if (-not ($pathParts | Where-Object { $_.TrimEnd("\") -ieq $reviewedGhDir.TrimEnd("\") })) {
        $env:PATH = "$reviewedGhDir;$env:PATH"
    }

    $pathParts = @($env:PATH -split ";" | Where-Object { $_ })
    if (-not ($pathParts | Where-Object { $_.TrimEnd("\") -ieq $reviewedCodexDir.TrimEnd("\") })) {
        $env:PATH = "$reviewedCodexDir;$env:PATH"
    }

Then rerun the audit-only wrapper.

## Venv Rule

Do not manually activate the venv during quick restore.

Use the reviewed Python path directly:

    .\.venv-course\Scripts\python.exe

## Evidence To Paste Back

Paste only:

    Layer 1 restore status
    Layer 2 Host Check status
    Layer 3 drift reasons
    wrapper exit
    summary JSON if requested
    final git status / HEAD / origin/master / divergence

Do not paste large raw JSON unless reviewer asks for it.

## Stop Marker

A successful wrapper run should print:

    COURSE_ENVIRONMENT_RESTORE_REVIEW_DONE
    NO_LIVE_ACCEPTANCE_NO_DISPATCHER_NO_RUNNER_NO_CODEX_TASK_NO_GITHUB_WRITE

If these markers are missing, treat the result as incomplete evidence.
