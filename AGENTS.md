# AGENTS.md

## Repository Scope

These rules apply across the entire repository. More-specific nested
`AGENTS.md` files govern their own folder scope while inheriting these
repository-wide safety rules.

Any bridge, dispatcher, runner, Task Packet, Bridge Operator, or ChatGPT-to-Codex
workflow task must also read and follow `src/local_runner_bridge/AGENTS.md` as
the bridge-specific governance reference, whether the touched files are under
`src/`, `scripts/`, `tests/`, or `docs/`.

## Project Positioning

- The canonical showcase identity for this repo is `Local Document-to-Knowledge Workbench`, presented as a local document-to-knowledge workbench.
- This repo is a localhost, single-user, personal-use local-first workbench prototype.
- This repo is also intended as a public portfolio engineering project for a local-first document-to-knowledge workbench centered on the local document workbench showcase.
- Product runtime and development-workflow tooling are separate. Bridge, dispatcher, runner, and operator tooling must not be presented as the product runtime unless the user explicitly changes the project direction.
- Do not change the project's positioning, target audience, showcase storyline, product direction, or authority boundaries unless the user explicitly asks.

## Repository-Wide Safety

- Default is read-only.
- Any write-like product action must go through preview before approve.
- In the current product baseline, approve only changes local status and audit records. It does not trigger external side effects.
- Do not expose, store, commit, or print secrets, credentials, tokens, private keys, or authentication material.
- Do not automatically stage, commit, push, force push, merge, close Issues, edit labels, create PRs, or consume approvals.
- High-risk actions require separate explicit user approval.
- Do not add background schedulers, hidden long-running automation, automatic email sending, or automatic modification of original source documents.
- Do not create unauthorized autonomous multi-agent chaining or approval chaining.
- The bounded ChatGPT-to-Codex bridge approved by `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md` and `docs/BRIDGE_OPERATOR_V0_SPEC.md` is not prohibited by the autonomous multi-agent chaining rule, but any implementation still requires a separately approved task and must not expand Bridge authority.
- Do not add new features, milestones, authority, side effects, or scope that the user did not request.

## Architecture Principles

- Prefer the simplest maintainable design that works on localhost.
- Avoid premature package extraction, infrastructure setup, platform abstractions, or productization-first abstractions.
- Keep product logic in the Python API. Keep the Web app focused on display and user interaction.
- Use SQLite with the smallest schema that supports the current approved baseline.

## Development Rules

- Root-level rule files stay at repo root: `AGENTS.md`, `PLANS.md`.
- General documentation can go under `docs/`.
- `docs/prompts/` is a placeholder in the current baseline, not a full prompt versioning system.
- `tests/e2e/` may exist as a placeholder, but the current baseline keeps testing focused on API tests.
- Keep diffs small, reviewable, and easy to inspect.
- Respect task-local edit boundaries. If only certain files or paths are allowed, edit only those files or paths.
- Do not make unrelated cleanup, formatting churn, or broad rewrites while completing a scoped task.
- Do not assume Unicode, full-width punctuation, box-drawing characters, or other special symbols are mojibake; verify before editing.
- Do not stage or commit playground files, scratch outputs, temporary logs, cache directories, or unapproved Codex drafts.

## Task Boundaries And Modes

Task size is governed by objective, authority, side effects, allowed paths, and
verification needs, not file count alone. If a task appears to expand beyond
the approved objective or authority boundary, stop and report the decision that
needs user approval.

### MICRO PATCH

- one small defect or narrowly scoped edit;
- usually a small number of files;
- minimal change preferred.

### BOUNDED FEATURE

- one end-to-end result;
- may span multiple explicitly approved files or modules;
- must not expand authority or side effects.

### ARCHITECTURE AUDIT

- read-only;
- may inspect a complete explicitly scoped folder;
- no arbitrary repository-wide exploration.

### GOVERNANCE CLEANUP

- documentation and rule changes only;
- no runtime, script, test, API, or UI behavior changes.

### VERIFY ONLY

- run approved checks and report;
- no modifications unless separately authorized.

## Verification

- After code changes, run `pytest -q` by default when the repo provides a pytest-based test suite, unless the user gives a narrower command.
- For CLI-related changes, run the documented CLI command from `README.md` or project docs. If no CLI entrypoint exists, report that explicitly in the final report.
- For Docker-related changes, run `docker build` and `docker run` for the affected flow. If Docker assets are absent, report that the check is not applicable.
- For documentation-only or governance-only changes, verify the written description still matches current repo behavior, commands, visible structure, and approved authority.
- If a task does not modify code, explain why `pytest -q` was not run.
- If a requested verification cannot be run, report the exact blocker instead of claiming it passed.
- Report verification results and blockers honestly.

## Decision Boundary

- Codex may implement requested changes, run verification, tidy docs, and make bounded suggestions.
- Codex may not unilaterally decide the project direction, repo positioning, large refactors, authority expansion, or new features.
- If a task would change the mainline direction, public positioning, approval boundary, or side-effect authority, stop and list the decisions that require user approval first.

## Stop Conditions

- If a required file anchor or expected code section is missing, stop and report instead of guessing.
- If build or tests fail after one focused repair attempt, stop and report the failure, changed files, and suspected cause.
- If the task appears larger than requested, stop and propose smaller follow-up tasks.
- If the requested change conflicts with `README.md`, `AGENTS.md`, `PLANS.md`, a scoped `AGENTS.md`, or an explicit task document, stop and report the conflict.
- Do not continue into unrelated cleanup, refactors, or visual polish after the requested task is complete.

## Token And Context Discipline

- Do not inspect unrelated files.
- Do not summarize the whole repository unless explicitly asked.
- Use `README.md`, `AGENTS.md`, scoped `AGENTS.md` files, `PLANS.md`, and explicit task documents as the primary context.
- Prefer targeted file reads over broad repository exploration.
- Keep final reports short and structured according to the user's requested format when one is provided.
