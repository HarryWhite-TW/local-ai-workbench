@echo off
setlocal
cd /d "%~dp0"
if not defined NEXUS_PYTHON set "NEXUS_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%NEXUS_PYTHON%" (
  echo Create .venv and install requirements-companion.txt first. See README.md.
  pause
  exit /b 1
)
if not defined NEXUS_CODEX set "NEXUS_CODEX=%APPDATA%\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe"
if not exist "%NEXUS_CODEX%" (
  echo Install the pinned official Codex CLI 0.162.1 and sign in. See README.md.
  pause
  exit /b 1
)
set "NEXUS_VERSION="
for /f "delims=" %%V in ('""%NEXUS_CODEX%" --version 2^>nul"') do set "NEXUS_VERSION=%%V"
if not "%NEXUS_VERSION%"=="codex-cli 0.162.1" (
  echo Expected codex-cli 0.162.1. No model was started.
  pause
  exit /b 1
)
if not defined NEXUS_PORT set "NEXUS_PORT=56144"
set "PYTHONPATH="
set "NEXUS_LOCAL=%LOCALAPPDATA%\NEXUS\Daily"
if "%NEXUS_ENGINEERING_PILOT%"=="1" (
  if not exist "%NEXUS_LOCAL%\fixture" (
    mkdir "%NEXUS_LOCAL%\fixture"
    if errorlevel 1 exit /b 1
    copy /y "%~dp0examples\engineering-pilot\before\AGENTS.md" "%NEXUS_LOCAL%\fixture\AGENTS.md" >nul
    if errorlevel 1 exit /b 1
    copy /y "%~dp0examples\engineering-pilot\before\calculator.py" "%NEXUS_LOCAL%\fixture\calculator.py" >nul
    if errorlevel 1 exit /b 1
    copy /y "%~dp0examples\engineering-pilot\before\test_calculator.py" "%NEXUS_LOCAL%\fixture\test_calculator.py" >nul
    if errorlevel 1 exit /b 1
  )
  "%NEXUS_PYTHON%" -B -m src.companion_core.daily --workspace "%~dp0." --data-dir "%NEXUS_LOCAL%\state" --review-dir "%NEXUS_LOCAL%\reviews" --port "%NEXUS_PORT%" --codex "%NEXUS_CODEX%" --pilot-workspace "%NEXUS_LOCAL%\fixture"
) else (
  "%NEXUS_PYTHON%" -B -m src.companion_core.daily --workspace "%~dp0." --data-dir "%NEXUS_LOCAL%\state" --review-dir "%NEXUS_LOCAL%\reviews" --port "%NEXUS_PORT%" --codex "%NEXUS_CODEX%"
)
if errorlevel 1 pause
