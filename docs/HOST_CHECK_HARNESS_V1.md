# Host Check Harness v1

## Purpose

`lawb.rv2_03_host_check.v1` is a read-only RV2-03 diagnostic harness created during Phase A and still useful during Phase B change-control.
It characterizes the current Windows host, reviewed absolute tool paths, fresh
shell tool visibility, and bootstrap contract drift before later operational
acceptance work.

This is not the RV2-04 Host Profile implementation. It does not repair the
host, install packages, create a virtual environment, modify PATH, run
Dispatcher, run Runner, run PollOnce, invoke Bridge Operator, or execute a
Codex task.

## Entry Points

The PowerShell wrapper is the canonical Windows entry point. It sets
`PYTHONPATH` for the child Python process only, using the wrapper checkout's
`src` directory as the module source, launches Python with `-B`, sets
process-local `PYTHONDONTWRITEBYTECODE=1`, restores the previous environment
values, and preserves the harness exit code. `RepoRoot` is the repository being
inspected; it is not used as the Python import source.

PowerShell wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_check_v1.ps1 `
    -RepoRoot "C:\Users\admin\Desktop\local-ai-workbench" `
    -ExpectedRepository "HarryWhite-TW/local-ai-workbench" `
    -ExpectedBranch "<approved-branch-from-current-task>" `
    -ExpectedHead "<approved-full-head>" `
    -ReviewedPythonPath "C:\Users\admin\.venvs\lawb-workflow\Scripts\python.exe" `
    -ReviewedGhPath "C:\Users\admin\tools\gh-portable\bin\gh.exe" `
    -ReviewedCodexPath "C:\nvm4w\nodejs\codex.cmd" `
    -Pretty
```

Use the complete reviewed HEAD SHA for the exact execution gate. After a new
approved commit, update the command argument to that new full HEAD.

Python module:

```powershell
$oldPythonPath = $env:PYTHONPATH
$oldDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONPATH = "C:\Users\admin\Desktop\local-ai-workbench\src;$oldPythonPath"
$env:PYTHONDONTWRITEBYTECODE = "1"
& "C:\Users\admin\.venvs\lawb-workflow\Scripts\python.exe" `
    -B `
    -m local_runner_bridge.host_check `
    --repo-root "C:\Users\admin\Desktop\local-ai-workbench" `
    --expected-repository "HarryWhite-TW/local-ai-workbench" `
    --expected-branch "<approved-branch-from-current-task>" `
    --expected-head "<approved-full-head>" `
    --reviewed-python-path "C:\Users\admin\.venvs\lawb-workflow\Scripts\python.exe" `
    --reviewed-gh-path "C:\Users\admin\tools\gh-portable\bin\gh.exe" `
    --reviewed-codex-path "C:\nvm4w\nodejs\codex.cmd" `
    --pretty
$env:PYTHONPATH = $oldPythonPath
$env:PYTHONDONTWRITEBYTECODE = $oldDontWriteBytecode
```

The direct module form requires the package to be importable, either through a
process-local `PYTHONPATH` like the example above or another approved import
setup. Do not install the repository merely to run this check.

For direct Python API or module usage, child probes are also launched with an
environment containing `PYTHONDONTWRITEBYTECODE=1`. This keeps the no temporary
repository files assertion independent from bytecode-cache behavior.

Use `-Json` or `--json` for compact machine-readable JSON. Use `-Pretty` or
`--pretty` for pretty JSON with no surrounding prose.

For machine-consumable exit-code checks, launch the wrapper as a separate
PowerShell process with `powershell.exe -File`. Dot-sourcing or invoking the
script inside an already-running automation runspace can make the outer wrapper
display its own process status. The supported script-process contract is still:
`0` for `READY` or operational `ATTENTION`, `2` for `BLOCKED`, and `3` for an
unexpected harness failure.

## Status Model

Top-level JSON uses:

```text
protocol=lawb.rv2_03_host_check.v1
status=READY|ATTENTION|BLOCKED
operational_readiness=true|false
```

`READY` means no blocking or attention reasons were found.

`ATTENTION` means no blocking condition was found, but observational drift or
visibility mismatch exists. Known RV2-03 A1 drift can still return
`operational_readiness=true`.

`BLOCKED` means a readiness condition failed, such as unavailable repository
identity reads, wrong repository, wrong branch, wrong HEAD, dirty working tree,
missing Git identity, missing reviewed tool path, failed imports, failed GitHub
authentication, failed repository read, unsafe Codex launcher, failed Codex
version probe, unreadable manifest, or invalid manifest schema.

Exit codes:

```text
0 = READY or ATTENTION with operational_readiness=true
2 = BLOCKED
3 = unexpected harness failure
```

Exit code `1` is not used for normal diagnostic findings.

## Read-Only Assertions

The harness reports safety fields asserting that it did not:

- install packages;
- create a venv;
- modify PATH;
- invoke git fetch, pull, switch, reset, clean, or stash;
- perform GitHub writes;
- invoke Bridge Operator, Dispatcher, Runner, or PollOnce;
- execute a Codex task;
- create temporary repository files.

It captures Git working-tree status before and after the checks. Repository
identity and integrity reads fail closed. These read failures are blocking:

```text
origin_url_unavailable
branch_unavailable
head_unavailable
working_tree_status_unavailable
final_working_tree_status_unavailable
```

The wrapper and Python harness disable Python bytecode writes because ignored
`__pycache__` directories and `.pyc` files may not appear in `git status`.
Therefore, a clean Git status alone is not sufficient evidence that no ignored
temporary repository files were created.

The harness reports `repository_integrity_verified=true` only when the initial
status read succeeded, the final status read succeeded, and both status outputs
match exactly. If the final status read fails, `working_tree_clean_after=null`,
`working_tree_unchanged=false`, `repository_integrity_verified=false`, and
`repository_modified_by_check=true`. If both status reads succeed but differ,
the result is `BLOCKED` with `working_tree_changed_during_check`.

The harness deliberately keeps repository readiness fail-closed during local
development. The historical A1 acceptance sequence was:

```text
uncommitted A1 files
-> working_tree_dirty is expected

committed but not pushed A1 HEAD
-> upstream_head_mismatch is expected

pushed and synchronized A1 HEAD
-> final full Host Check may become operationally ready
```

Do not add an option to ignore current task files. Final clean-host acceptance
belongs after the applicable separate commit and push approvals for that task.

The reported origin URL is sanitized before output. URL userinfo, query
strings, and fragments are not included. The harness never reads or emits Git
credentials.
Malformed or unparseable origin URLs are sanitized conservatively;
credential-like userinfo is removed or the display value is redacted.

## Authentication Evidence

GitHub executable visibility and GitHub authentication are separate facts.
The harness records reviewed path, PATH-resolved path, fresh-shell path,
selected path, version probe exit code, authentication probe exit code, and
repository-read result. It does not store raw authentication output and does not
expose tokens or credential material.

If the current execution context cannot authenticate, the harness reports
`gh_auth_failed`. It does not run `gh auth login` or add any credential repair
behavior.

Executable visibility is not authentication evidence. The harness reports the
reviewed executable, selected executable, version probe, current execution
context authentication probe, repository read probe, and fresh-shell path
visibility as separate facts.

Tool probe failures use safe stage metadata with fields such as `stage`, `ok`,
`exit_code`, `error_type`, and `safe_message`. The recorded stages distinguish
`python_version`, `python_pip`, `python_pytest`, `python_imports`,
`gh_version`, `gh_auth`, `gh_repository_read`, and `codex_version`. Raw GitHub
authentication output is not stored.

## Codex Version Probe

The Codex check runs only:

```text
codex --version
```

For `.cmd` and `.bat` launchers, the Python harness uses an argument vector
equivalent to:

```text
COMSPEC /d /s /c call <launcher-path> --version
```

The launcher path remains a separate argument in the vector. The harness never
runs `codex exec`, `codex review`, or interactive Codex.

If the reviewed Codex path is missing, the harness reports
`reviewed_codex_missing` and does not invoke that path. If the reviewed Codex
path exists but has an unsafe or unknown suffix, the harness reports
`codex_unsafe_launcher` and does not invoke that path. In both cases the
`codex_version` probe metadata records `executed=false` with a safe message.

## Test Temporary Directories

On the reviewed course-computer context, pytest's default temp root may raise a
`PermissionError` for:

```text
C:\Users\admin\AppData\Local\Temp\pytest-of-admin
```

That is an environment observation, not a product test failure. Verification may
use an external `--basetemp` outside this repository, then remove that directory
after the run.

## Contract Drift

The bootstrap contract section compares:

- manifest venv path versus the reviewed operational venv;
- manifest Codex version versus the installed reviewed Codex version;
- manifest venv path coverage in `.gitignore`;
- current process and fresh-shell resolution versus reviewed absolute paths.

Drift is observational only. The harness does not edit `.gitignore`, edit the
manifest, create `.venv-course`, install the manifest Codex version, or choose a
permanent Host Profile.

The manifest must be valid JSON with this minimum schema:

```text
top-level object
protocol: non-empty string
paths: object
paths.venv: non-empty string
codex: object
codex.version: non-empty string
```

Missing or invalid JSON reports `manifest_unreadable`. Valid JSON with an
invalid schema reports `manifest_invalid`. Neither condition may return
`operational_readiness=true`. Invalid `paths.venv` values, including objects,
arrays, numbers, booleans, `null`, empty strings, and whitespace-only strings,
report `manifest_invalid` without escaping an exception or being mislabeled as
an unexpected harness failure.

## Environment Injection

The Python API's `environment` mapping is used for current-process PATH
resolution, child process environment, and COMSPEC selection for `.cmd` and
`.bat` launchers. This is dependency injection for deterministic checks; the
harness does not mutate global environment variables, user PATH, or machine
PATH.
