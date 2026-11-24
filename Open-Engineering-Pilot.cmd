@echo off
setlocal
set "NEXUS_ENGINEERING_PILOT=1"
if not defined NEXUS_PORT set "NEXUS_PORT=56145"
call "%~dp0Open-Companion.cmd"
