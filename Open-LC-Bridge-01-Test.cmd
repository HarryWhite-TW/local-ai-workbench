@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
python -B tests\companion_core\browser_fixture.py --interactive --data "%LOCALAPPDATA%\LocalAIWorkbench\LCBridge01-Test"
if errorlevel 1 pause
