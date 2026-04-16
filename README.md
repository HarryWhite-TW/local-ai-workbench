# Local Document Assistant Prototype

This repository is a localhost, single-user, personal-use prototype for working with a local document collection. It is not the mainline of a formal product, not a SaaS system, and not a productization-first codebase.

Current baseline:
- `M1` through `M8` complete
- `v1` complete
- showcase UI workbench redesign complete

The app stays intentionally simple:
- one configured root folder
- manual scan into local SQLite
- local deterministic processing only
- no external LLM or background automation

## Project Positioning

- Localhost only
- Single-user and personal-use
- Read-oriented workflow with explicit preview and approve boundaries
- Simplest maintainable design that works for the current milestone history

## Core Capabilities

- Configure one root folder through the API
- Manually scan `md`, `txt`, `pdf`, and `docx` files into SQLite
- List indexed documents and open document detail
- Generate a deterministic single-document summary artifact
- Search locally by keyword across title, relative path, and content
- Review summary and audit information in the current workbench UI

## Current UI

The current web app is a three-column local document workbench:
- Header: data source and scan status
- Left column: search and document list
- Center column: document detail
- Right column: summary as the primary panel and audit as secondary context

This is not a chat-first interface.

## Repository Layout

- `api/`: FastAPI app, SQLite access, schemas, and route handlers
- `web/`: React + TypeScript workbench UI built with Vite
- `data/`: local runtime database area and local validation artifacts
- `tests/`: API-focused tests plus placeholder directories for future expansion
- `docs/`: lightweight project documentation and prompt placeholders
- `AGENTS.md`: repo-level collaboration and scope guardrails
- `PLANS.md`: project planning notes kept at repo root

## Local Setup

### API

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r api\requirements.txt
uvicorn api.app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`.

### Web

```powershell
cd web
npm install
npm run dev
```

The Vite dev server runs on `http://127.0.0.1:5173`.

### Tests

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests\api -q -p no:cacheprovider
```

## Basic Usage Path

1. Start the API and web app locally.
2. Configure the document root folder.
3. Run a manual scan to index supported files into SQLite.
4. Use the left pane to search and select a document.
5. Read document detail in the center pane.
6. Review the generated summary and related audit context in the right pane.

## Non-Goals And Known Limits

- No OCR
- No scanned-PDF recognition
- No multi-folder support
- No watcher or background sync
- No external LLM
- No semantic search, embeddings, vector database, or FTS5
- No search filters, search history, or match highlighting
- No parser platform or orchestration layer
- No new file types beyond the current set
- No rich markdown rendering
- No multi-document summary
- No productization, auth, multi-user support, or SaaS framing
- No chat-first main UI

## AI Collaboration

This repo is designed to be worked on with human review and AI-assisted development, but the application itself does not call any external AI service.

When collaborating through an agent workflow:
- follow the repo-root guardrails in `AGENTS.md`
- keep scope aligned with the active baseline instead of inventing new milestones
- treat write-like actions as preview-before-approve work

## Notes

- `data/app.db` is created automatically when the API starts.
- Public-release prep should keep local private assets, walkthrough outputs, and validation databases out of version control.
