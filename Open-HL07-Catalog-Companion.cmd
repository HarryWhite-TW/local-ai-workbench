@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist "%~dp0..\.venv\Scripts\python.exe" (
  echo HL-07 isolated runtime is missing. Follow README.md or run Restore-HL05-Runtime.cmd.
  popd
  exit /b 1
)
"%~dp0..\.venv\Scripts\python.exe" -I -B -X utf8 -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path.cwd())); from src.companion_core.daily import main; raise SystemExit(main())" --natural-engineering-collaboration --port 47671 %*
set "trial_result=%errorlevel%"
popd
exit /b %trial_result%
