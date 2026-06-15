param(
    [switch]$AssumeYes
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "== $Message =="
}

function Confirm-Step($Prompt) {
    if ($AssumeYes) {
        return $true
    }
    $answer = Read-Host "$Prompt Type YES to continue"
    return $answer -eq "YES"
}

function Require-Command($Name, $InstallHint) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Name was not found. $InstallHint"
    }
    return $command.Source
}

function Invoke-Version($Command, $Arguments) {
    try {
        $output = & $Command @Arguments 2>&1 | Select-Object -First 1
        if ($LASTEXITCODE -ne 0) {
            return "version check failed: exit_code=$LASTEXITCODE"
        }
        return $output
    }
    catch {
        "version check failed: $($_.Exception.Message)"
    }
}

function Test-VersionReady($VersionText) {
    return ($VersionText -and ($VersionText -notlike "version check failed:*"))
}

function Get-PortableGhPath {
    Join-Path $env:USERPROFILE "tools\gh-portable\bin\gh.exe"
}

function Install-PortableGitHubCli($TargetPath) {
    if (-not (Confirm-Step "Portable GitHub CLI is missing at $TargetPath. Download official GitHub CLI release and install it there?")) {
        throw "GitHub CLI is required. Install skipped by user."
    }

    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/cli/cli/releases/latest" -Headers @{ "User-Agent" = "local-ai-workbench-course-computer-recovery" }
    $asset = $release.assets |
        Where-Object { $_.name -match "^gh_.*_windows_amd64\.zip$" } |
        Select-Object -First 1
    if (-not $asset) {
        throw "Could not find a Windows amd64 GitHub CLI zip in the official latest release."
    }

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lawb-gh-" + [System.Guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempRoot $asset.name
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot -Force
    $ghExe = Get-ChildItem -Path $tempRoot -Recurse -Filter "gh.exe" | Select-Object -First 1
    if (-not $ghExe) {
        throw "Downloaded GitHub CLI archive did not contain gh.exe."
    }

    $targetDir = Split-Path -Parent $TargetPath
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $ghExe.FullName -Destination $TargetPath -Force
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

function Assert-RepositoryRoot($GitPath) {
    $current = (Get-Location).Path
    $topLevel = (& $GitPath rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $topLevel) {
        throw "Current directory is not inside a Git repository. Rerun from the local-ai-workbench repository root."
    }

    $resolvedCurrent = [System.IO.Path]::GetFullPath($current).TrimEnd('\')
    $resolvedTopLevel = [System.IO.Path]::GetFullPath($topLevel).TrimEnd('\')
    if ($resolvedCurrent -ne $resolvedTopLevel) {
        throw "Current directory is a repository subdirectory. Rerun from the local-ai-workbench repository root: $resolvedTopLevel"
    }
    if ((Split-Path -Leaf $resolvedTopLevel) -ne "local-ai-workbench") {
        throw "This is not the local-ai-workbench repository root."
    }

    $origin = (& $GitPath config --get remote.origin.url 2>$null)
    if ($LASTEXITCODE -ne 0 -or ($origin -notmatch "HarryWhite-TW[\\/]+local-ai-workbench(\.git)?$")) {
        throw "This repository is not HarryWhite-TW/local-ai-workbench."
    }
    return $resolvedTopLevel
}

function Resolve-CodexLauncher {
    $candidates = @()
    foreach ($name in @("codex.exe", "codex.cmd", "codex.bat", "codex")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) {
            $candidates += $found
        }
    }

    $ranked = $candidates |
        Where-Object {
            $extension = [System.IO.Path]::GetExtension($_.Source).ToLowerInvariant()
            $_.Source -and (
                $extension -in @(".exe", ".cmd", ".bat") -or
                ($extension -ne ".ps1" -and $_.CommandType -eq "Application")
            )
        } |
        Sort-Object @{
            Expression = {
                switch ([System.IO.Path]::GetExtension($_.Source).ToLowerInvariant()) {
                    ".exe" { 0 }
                    ".cmd" { 1 }
                    ".bat" { 2 }
                    default {
                        if ($_.CommandType -eq "Application") { 3 } else { 4 }
                    }
                }
            }
        }
    if ($ranked) {
        return $ranked[0].Source
    }
    return $null
}

function Test-GhAuth($GhPath) {
    & $GhPath auth status *> $null
    return $LASTEXITCODE -eq 0
}

Write-Host "Local AI Workbench course-computer environment recovery"
Write-Host "This script verifies local tooling and may install portable GitHub CLI or @openai/codex only after visible confirmation."

Write-Step "Prerequisites"
$gitPath = Require-Command "git" "Install Git for Windows, then rerun from the repository root."
$nodePath = Require-Command "node" "Install Node.js LTS, then rerun from the repository root."
$npmPath = Require-Command "npm" "Install npm with Node.js LTS, then rerun from the repository root."
$gitVersion = Invoke-Version $gitPath @("--version")
$nodeVersion = Invoke-Version $nodePath @("--version")
$npmVersion = Invoke-Version $npmPath @("--version")
Write-Host "Git:  $gitVersion"
Write-Host "Node: $nodeVersion"
Write-Host "npm:  $npmVersion"

Write-Step "Repository state"
$repoRoot = Assert-RepositoryRoot -GitPath $gitPath
$branch = (& $gitPath rev-parse --abbrev-ref HEAD 2>$null)
$head = (& $gitPath rev-parse HEAD 2>$null)
$status = (& $gitPath status --porcelain 2>$null)
Write-Host "Root:   $repoRoot"
Write-Host "Branch: $branch"
Write-Host "HEAD:   $head"
if ($status) {
    Write-Host "Working tree: dirty"
}
else {
    Write-Host "Working tree: clean"
}

Write-Step "GitHub CLI"
$ghPath = Get-PortableGhPath
if (-not (Test-Path -LiteralPath $ghPath)) {
    Install-PortableGitHubCli -TargetPath $ghPath
}
Write-Host "GitHub CLI: $ghPath"
$ghVersion = Invoke-Version $ghPath @("--version")
Write-Host "Version: $ghVersion"

$ghAuthenticated = Test-GhAuth -GhPath $ghPath
if (-not $ghAuthenticated) {
    Write-Host "GitHub CLI is not authenticated. The normal browser login flow can be started now."
    if (Confirm-Step "Run 'gh auth login --web' for interactive browser authentication?") {
        & $ghPath auth login --web
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub CLI authentication failed during interactive login."
        }
        $ghAuthenticated = Test-GhAuth -GhPath $ghPath
    }
    else {
        throw "GitHub CLI authentication is required. Login skipped by user."
    }
}
if (-not $ghAuthenticated) {
    throw "GitHub CLI authentication is required. 'gh auth status' still fails after login."
}
& $ghPath auth status | Out-Host

Write-Step "Codex launcher"
$codexPath = Resolve-CodexLauncher
if (-not $codexPath) {
    Write-Host "Codex launcher was not found."
    if (Confirm-Step "Install the official npm package @openai/codex globally?") {
        & $npmPath install -g @openai/codex
    }
    else {
        throw "Codex launcher is required. Install skipped by user."
    }
    $codexPath = Resolve-CodexLauncher
}
if (-not $codexPath) {
    throw "Codex launcher still was not found after install attempt."
}
Write-Host "Codex: $codexPath"
$codexVersion = Invoke-Version $codexPath @("--version")
Write-Host "Version: $codexVersion"
Write-Host "First-time users should launch Codex once manually for interactive ChatGPT sign-in before running bridge workflows."

$gitReady = Test-VersionReady $gitVersion
$nodeReady = Test-VersionReady $nodeVersion
$npmReady = Test-VersionReady $npmVersion
$ghReady = (Test-VersionReady $ghVersion) -and $ghAuthenticated
$codexReady = (Test-VersionReady $codexVersion) -and ([System.IO.Path]::GetExtension($codexPath).ToLowerInvariant() -ne ".ps1")

Write-Step "Readiness summary"
Write-Host "branch=$branch"
Write-Host "head=$head"
Write-Host "working_tree_clean=$(-not [bool]$status)"
Write-Host "git=$(if ($gitReady) { 'ready' } else { 'blocked' })"
Write-Host "node=$(if ($nodeReady) { 'ready' } else { 'blocked' })"
Write-Host "npm=$(if ($npmReady) { 'ready' } else { 'blocked' })"
Write-Host "gh=$(if ($ghReady) { 'ready' } else { 'blocked' })"
Write-Host "codex=$(if ($codexReady) { 'ready' } else { 'blocked' })"
if (-not ($gitReady -and $nodeReady -and $npmReady -and $ghReady -and $codexReady)) {
    throw "One or more readiness checks failed."
}
Write-Host "No Dispatcher, Runner, Codex task, commit, push, Issue close, label, PR, merge, or approval action was invoked."
