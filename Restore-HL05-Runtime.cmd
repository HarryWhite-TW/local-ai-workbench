@echo off
setlocal
set "hl05_python=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if defined NEXUS_PYTHON_314 set "hl05_python=%NEXUS_PYTHON_314%"
if not exist "%hl05_python%" (
  echo Python 3.14.6 x64 is required. Set NEXUS_PYTHON_314 to its installed executable.
  exit /b 1
)
"%hl05_python%" -I -B -X utf8 "%~dp0scripts\restore_hl05_runtime.py"
exit /b %errorlevel%
