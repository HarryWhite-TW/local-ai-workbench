@echo off
setlocal
pushd "%~dp0"
if not exist "%~dp0..\.venv\Scripts\python.exe" (
  echo HL-05 runtime is missing. Run Restore-HL05-Runtime.cmd first.
  popd
  exit /b 1
)
"%~dp0..\.venv\Scripts\python.exe" -I -B -X utf8 -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path.cwd())); from src.companion_core.daily import main; raise SystemExit(main())" --real-project-intelligence --port 47651 %*
set "trial_result=%errorlevel%"
popd
exit /b %trial_result%
