# PLANS.md

## Project Goal
Build a controlled local AI assistant prototype with a single Web entrypoint.
The system is read-first and approval-gated for any write-like action.

## Current Position
- Localhost only
- Single user only
- Prototype only
- Not a productization project

## M1 Scope
- Minimal Web UI skeleton
- Minimal Python API skeleton
- SQLite persistence
- Fake preview / approve / audit flow
- Initial `AGENTS.md` and `PLANS.md`

## M1 Acceptance
- Web and API start locally
- User can create a preview action
- User can approve that action
- Action state persists in SQLite
- Audit events are stored and visible
- No real Gmail, Calendar, LLM, or file-writing integration

## Deferred After M1
- Real LLM integration
- Local file ingestion
- Google OAuth
- Gmail read / draft create
- Calendar query / event create
- Prompt versioning system
- Real E2E automation

## Change Log
- 2026-04-10: M1 narrowed to local preview/approve/audit prototype.

