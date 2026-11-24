@echo off
setlocal
pushd "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" -I -B -X utf8 -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path.cwd())); from src.companion_core.daily import main; raise SystemExit(main())" --codex-subscription-trial --port 47641 %*
set "trial_result=%errorlevel%"
popd
exit /b %trial_result%
