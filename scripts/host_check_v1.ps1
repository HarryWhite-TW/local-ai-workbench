param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedRepository,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedBranch,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedHead,
    [Parameter(Mandatory = $true)]
    [string]$ReviewedPythonPath,
    [Parameter(Mandatory = $true)]
    [string]$ReviewedGhPath,
    [Parameter(Mandatory = $true)]
    [string]$ReviewedCodexPath,
    [switch]$Json,
    [switch]$Pretty
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ReviewedPythonPath -PathType Leaf)) {
    [Console]::Error.WriteLine("Reviewed Python path does not exist: $ReviewedPythonPath")
    exit 2
}

$oldPythonPath = $env:PYTHONPATH
$oldDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$srcPath = Join-Path $RepoRoot "src"

try {
    $env:PYTHONPATH = if ($oldPythonPath) { "$srcPath;$oldPythonPath" } else { $srcPath }
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $arguments = @(
        "-B",
        "-m", "local_runner_bridge.host_check",
        "--repo-root", $RepoRoot,
        "--expected-repository", $ExpectedRepository,
        "--expected-branch", $ExpectedBranch,
        "--expected-head", $ExpectedHead,
        "--reviewed-python-path", $ReviewedPythonPath,
        "--reviewed-gh-path", $ReviewedGhPath,
        "--reviewed-codex-path", $ReviewedCodexPath
    )

    if ($Json) {
        $arguments += "--json"
    }
    if ($Pretty) {
        $arguments += "--pretty"
    }

    & $ReviewedPythonPath @arguments
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine("Unexpected host_check_v1 wrapper failure: $($_.Exception.GetType().Name)")
    exit 3
}
finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $oldDontWriteBytecode
}
