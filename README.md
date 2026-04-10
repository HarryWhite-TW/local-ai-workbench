# Local AI Assistant Prototype

This repository is a localhost, single-user, personal-use prototype for a controlled AI assistant. It is not the mainline of a formal product, and it is not a productization project.

M1 focuses on a fake `preview -> approve -> audit` flow:
- no real LLM integration
- no Google OAuth
- no Gmail or Calendar writes
- no external side effects

## Repository Layout

- `api/`: FastAPI backend with SQLite persistence
- `web/`: React + TypeScript frontend
- `data/`: local SQLite database and export placeholder
- `tests/`: API tests and future placeholders
- `docs/prompts/`: prompt placeholder only in M1

## API Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r api\requirements.txt
uvicorn api.app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`.

## Web Setup

```powershell
cd web
npm install
npm run dev
```

The Vite dev server runs on `http://127.0.0.1:5173`.

## Tests

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests\api -q -p no:cacheprovider
```

## Known Limitations

- No real LLM integration
- No Google OAuth, Gmail integration, or Calendar integration
- No external writes or background automation
- Approval in M1 only updates local SQLite state and audit records

## Notes

- `data/app.db` is created automatically when the API starts.
- M1 does not use the existing `.docx` files or `integrate_docx.py`.
