@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please install requirements-companion.txt in .venv first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -m src.companion_core.daily --workspace "%~dp0."
if errorlevel 1 pause
