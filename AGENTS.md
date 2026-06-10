# AGENTS.md

## Project Positioning
- The canonical showcase identity for this repo is `Local Document Assistant Prototype`, presented as a local document workbench.
- This repo is a localhost, single-user, personal-use prototype.
- This repo is also intended as a public portfolio engineering project for a local-first document assistant prototype centered on the local document workbench showcase.
- Do not change the project's positioning, target audience, or showcase storyline unless the user explicitly asks.

## Non-Goals
- No automatic email sending.
- No automatic modification of original source documents.
- No background schedulers or long-running automation.
- No multi-agent chaining.
- No productization-first abstractions.
- Do not add new features, milestones, or scope that the user did not request.

## Core Rule
- Default is read-only.
- Any write-like action must go through preview before approve.
- In the current baseline, approve only changes local status and audit records. It does not trigger external side effects.

## Architecture Principles
- Prefer the simplest maintainable design that works on localhost.
- Avoid premature package extraction, infra setup, or platform abstractions.
- Keep logic in the Python API. Keep the Web app focused on display and user interaction.
- Use SQLite with the smallest schema that supports the current baseline.

## Development Rules
- Root-level rule files stay at repo root: `AGENTS.md`, `PLANS.md`.
- General documentation can go under `docs/`.
- `docs/prompts/` is a placeholder in the current baseline, not a full prompt versioning system.
- `tests/e2e/` may exist as a placeholder, but the current baseline keeps testing focused on API tests.

## Testing Focus for Current Baseline
- Protect preview creation.
- Protect approve state transition.
- Protect audit event creation.
- Do not spend effort on full E2E infrastructure in the current baseline unless scope changes later.

## Codex Collaboration Rules
- Keep diffs small, reviewable, and easy to inspect.
- Stay aligned with the README public showcase path instead of drifting into completeness-first work.
- Do not assume Unicode, full-width punctuation, box-drawing characters, or other special symbols are mojibake; verify before editing.
- Do not stage or commit playground files, scratch outputs, temporary logs, cache directories, or unapproved Codex drafts.
- Do not make unilateral decisions about the main direction, large refactors, or scope expansion.
- Respect any task-local edit boundary from the user; if only certain files are allowed, edit only those files.
- Do not auto-commit unless the user explicitly asks.

## Verification
- After code changes, run `pytest -q` by default when the repo provides a pytest-based test suite, unless the user gives a narrower command.
- For CLI-related changes, run the documented CLI command from `README.md` or project docs. If no CLI entrypoint exists, report that explicitly in the final report.
- For Docker-related changes, run `docker build` and `docker run` for the affected flow. If Docker assets are absent, report that the check is not applicable.
- For documentation changes, verify that the written description still matches current repo behavior, commands, and visible structure.
- If a task does not modify code, explain why `pytest -q` was not run.
- If a requested verification cannot be run, report the exact blocker instead of claiming it passed.

## Response Format
For every completed task, report in this order:
1. Summary
2. Modified files
3. Commands run
4. Test results
5. Risks / assumptions
6. Suggested next step

## Decision Boundary
- Codex may implement requested changes, run verification, tidy docs, and make bounded suggestions.
- Codex may not unilaterally decide the project direction, repo positioning, large refactors, or new features.
- If a task would change the mainline direction, public positioning, or scope, stop and list the decisions that require user approval first.

## Codex Task Modes

- `PLAN ONLY`: Inspect the explicitly relevant files and return a plan. Do not modify files.
- `PATCH ONLY`: Modify only the approved files for one approved objective. Do not expand scope.
- `VERIFY ONLY`: Run the requested checks and report results. Do not modify files unless explicitly asked.
- `DOCS ONLY`: Update documentation only. Do not touch code, tests, API contracts, or UI files.

## Task Size Budget

- One Codex task must have one objective.
- Prefer 1–3 allowed files per task.
- If more than 3 files seem necessary, stop and propose a task split before editing.
- UI tasks must not combine layout redesign, state model changes, CSS polish, bug fixes, and copywriting in the same task.
- Architecture or state-machine changes must use `PLAN ONLY` first unless the user explicitly provides an approved implementation plan.
- Do not rewrite an entire page, component, module, or document unless explicitly approved.

## Stop Conditions

- If a required file anchor or expected code section is missing, stop and report instead of guessing.
- If build or tests fail after one focused repair attempt, stop and report the failure, changed files, and suspected cause.
- If the task appears larger than requested, stop and propose smaller follow-up tasks.
- If the requested change conflicts with `README.md`, `AGENTS.md`, `PLANS.md`, or an explicit task document, stop and report the conflict.
- Do not continue into unrelated cleanup, refactors, or visual polish after the requested task is complete.

## Token and Context Discipline

- Do not inspect unrelated files.
- Do not summarize the whole repository unless explicitly asked.
- Use `README.md`, `AGENTS.md`, `PLANS.md`, and explicit task documents as the primary context.
- Prefer targeted file reads over broad repository exploration.
- Keep final reports short and structured according to the existing response format.
