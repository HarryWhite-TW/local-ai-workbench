# Post-RV2-03 Minimal Evidence Collector V1

## Purpose

The Minimal Evidence Collector is a local OPT-02 prototype for collecting command evidence in the shape frozen by the OPT-01 workflow contracts. It records facts about explicitly provided local commands and writes reviewable JSON artifacts.

This prototype does not authorize Git writes, GitHub writes, Issue mutation, live Bridge execution, Dispatcher, Runner, Codex runtime task execution, dependency installation, tool installation, service, watcher, MCP, or RV2-04.

The collector is development workflow tooling only. It is not product runtime and does not decide whether a task is semantically accepted.

## Supported Profiles

Supported profiles are:

- `docs`
- `code`

Unsupported profiles fail closed. There is no `live`, `bridge`, `dispatcher`, `runner`, `codex`, or `github_write` profile.

## CLI Flow

This repository uses a `src` layout. For local CLI execution in this prototype, use a process-local `PYTHONPATH=src` so `python -m local_runner_bridge...` can import the package without any permanent config or PATH modification.

Example setup for the current shell only:

```powershell
$env:PYTHONPATH = "src"
```

Begin creates an evidence root and writes `session.json`:

```powershell
.\.venv-course\Scripts\python.exe -m local_runner_bridge.minimal_evidence_collector_cli begin --repo-root . --evidence-root <dir> --profile docs --label opt02-smoke
```

Run appends one Command Result to the session and captures stdout and stderr artifacts:

```powershell
.\.venv-course\Scripts\python.exe -m local_runner_bridge.minimal_evidence_collector_cli run --session <session.json> --id json-validate -- .\.venv-course\Scripts\python.exe -m json.tool docs\POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.schema.examples.json
```

Finalize writes `review_packet.json` and prints a compact summary:

```powershell
.\.venv-course\Scripts\python.exe -m local_runner_bridge.minimal_evidence_collector_cli finalize --session <session.json>
```

## Output Files

The evidence root contains:

- `session.json`
- `review_packet.json` after finalize
- `commands/<command-id>/stdout.txt`
- `commands/<command-id>/stderr.txt`

Empty stdout and stderr still produce artifact files and SHA-256 hashes.

## Session Schema

`session.json` includes:

- `schema_version`
- `session_id`
- `created_at`
- `repo_root`
- `evidence_root`
- `profile`
- `label`
- `commands`
- `safety`

Safety flags are explicit and remain false unless a future separately approved design changes the collector boundary:

- `github_write_performed`
- `git_write_performed`
- `issue_write_performed`
- `bridge_invoked`
- `dispatcher_invoked`
- `runner_invoked`
- `codex_invoked`
- `dependency_install_performed`
- `config_modified`
- `path_modified`

## Command Result Schema

Each command result includes:

- `schema_version`
- `command_id`
- `argv`
- `cwd`
- `started_at`
- `ended_at`
- `duration_ms`
- `exit_code`
- `timed_out`
- `killed`
- `stdout_path`
- `stderr_path`
- `stdout_bytes`
- `stderr_bytes`
- `stdout_sha256`
- `stderr_sha256`
- `decoding`

Commands are represented as argv arrays. The collector does not use `shell=True`.

## Review Packet Schema

`review_packet.json` includes:

- `schema_version`
- `session_id`
- `result`
- `profile`
- `label`
- `repo_root`
- `evidence_root`
- `command_count`
- `failed_command_count`
- `commands`
- `safety`
- `created_at`
- `finalized_at`

Allowed `result` values are:

- `success`
- `command_failed`
- `collector_error`

The review packet must not include semantic approval fields such as `accepted`, `approved`, or `done`.

## Denylist Limitations

The collector fails closed before execution when command words or standalone argv items match the prototype denylist:

```text
push commit merge reset clean checkout switch branch tag gh codex runner dispatcher poll auth token install pip npm
```

This denylist is a prototype safety belt, not a complete security sandbox. It does not replace reviewer judgment, command review, operating-system controls, repository governance, or task-specific approval boundaries.

## What The Collector Does Not Decide

The collector records command facts only. It does not decide:

- semantic acceptance
- task approval
- merge readiness
- release readiness
- whether evidence is sufficient for a reviewer
- whether a failed command can be ignored

Those remain human or ChatGPT review decisions under the approved workflow.

## Forbidden Authority

The collector must not:

- perform Git writes
- perform GitHub writes
- publish Issue comments
- mutate Issues, labels, milestones, branches, or PRs
- invoke live Bridge execution
- invoke Dispatcher
- invoke Runner
- invoke Codex runtime tasks
- install dependencies or tools
- modify config or PATH
- start services, watchers, schedulers, or background automation
- activate RV2-04

## OPT-03 Benchmark Handoff

OPT-03 may later compare the collector against historical task evidence if separately approved. This document does not authorize OPT-03. The handoff should use collector artifacts as factual inputs only, not as acceptance decisions.
