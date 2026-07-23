param([Parameter(Mandatory=$true)][ValidateSet("setup","verify","start")][string]$Action,[Parameter(Mandatory=$true)][string]$StateRoot,[Parameter(Mandatory=$true)][string]$HgwRoot)
$ErrorActionPreference="Stop"
$root=(Resolve-Path (Join-Path $PSScriptRoot ".."))
& (Join-Path $root ".venv-course\Scripts\python.exe") -m local_runner_bridge.display_pilot_operator_cli $Action --state-root $StateRoot --hgw-root $HgwRoot
exit $LASTEXITCODE
