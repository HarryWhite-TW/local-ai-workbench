# AGENTS.md

## Project Positioning
- This repo is a localhost, single-user, personal-use prototype.
- It is not the mainline of a formal product.
- It is not a SaaS or multi-user system.

## Non-Goals
- No automatic email sending.
- No automatic modification of original source documents.
- No background schedulers or long-running automation.
- No multi-agent chaining.
- No productization-first abstractions.

## Core Rule
- Default is read-only.
- Any write-like action must go through preview before approve.
- In M1, approve only changes local status and audit records. It does not trigger external side effects.

## Architecture Principles
- Prefer the simplest maintainable design that works on localhost.
- Avoid premature package extraction, infra setup, or platform abstractions.
- Keep logic in the Python API. Keep the Web app focused on display and user interaction.
- Use SQLite with the smallest schema that supports the current milestone.

## Development Rules
- Root-level rule files stay at repo root: `AGENTS.md`, `PLANS.md`.
- General documentation can go under `docs/`.
- `docs/prompts/` is a placeholder in M1, not a full prompt versioning system.
- `tests/e2e/` may exist as a placeholder, but M1 testing focuses on API tests.

## Testing Focus for M1
- Protect preview creation.
- Protect approve state transition.
- Protect audit event creation.
- Do not spend effort on full E2E infrastructure in M1 unless scope changes later.

