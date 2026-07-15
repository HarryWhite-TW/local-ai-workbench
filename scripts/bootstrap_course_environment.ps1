param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [switch]$Apply,
    [switch]$PersistUserPath,
    [switch]$Json,
    [string]$ArtifactCacheDir
)

$ErrorActionPreference = "Stop"

$Protocol = "lawb.bootstrap_course_environment.v1"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestPath = Join-Path $ScriptRoot "bootstrap_manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

function New-Result {
    [ordered]@{
        protocol = $Protocol
        mode = $(if ($Apply) { "APPLY" } else { "AUDIT" })
        overall_status = "READY"
        actions_planned = [System.Collections.ArrayList]::new()
        actions_performed = [System.Collections.ArrayList]::new()
        actions_skipped_reused = [System.Collections.ArrayList]::new()
        manual_actions_required = [System.Collections.ArrayList]::new()
        blockers = [System.Collections.ArrayList]::new()
        attention = [System.Collections.ArrayList]::new()
        detected = [ordered]@{}
        venv = [ordered]@{}
        dependencies = [ordered]@{}
        path = [ordered]@{
            current_process_added = [System.Collections.ArrayList]::new()
            persisted_user_added = [System.Collections.ArrayList]::new()
            required_entries_present = @{}
        }
        diagnostics = [ordered]@{
            invoked = $false
            status = $null
            reasons = @()
            raw = $null
            failure = [ordered]@{
                failed_action = $null
                failed_stage = $null
                safe_error = $null
                next_manual_action = $null
            }
        }
        safety = [ordered]@{
            admin_elevation_used = $false
            credentials_written = $false
            gh_login_invoked = $false
            interactive_codex_invoked = $false
            bridge_operator_invoked = $false
            dispatcher_invoked = $false
            runner_invoked = $false
            github_write_performed = $false
            machine_path_modified = $false
        }
    }
}

function Add-Unique([System.Collections.IList]$List, [string]$Value) {
    if ($Value -and -not $List.Contains($Value)) {
        [void]$List.Add($Value)
    }
}

function ConvertTo-SafeBootstrapError([string]$Message) {
    if (-not $Message) { return $null }
    $singleLine = (($Message -split "\r?\n") | Where-Object { $_ } | Select-Object -First 1)
    if (-not $singleLine) { return $null }
    $redacted = $singleLine `
        -replace "(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", "Bearer [redacted]" `
        -replace "(?i)\b(token|Authorization)\s*:\s*[A-Za-z0-9._~+/=-]{8,}", '$1: [redacted]' `
        -replace "(?i)\b(?:gho|ghp|ghs|ghu|ghr)_[A-Za-z0-9_]{8,}\b", "[redacted]" `
        -replace "(?i)\bgithub_pat_[A-Za-z0-9_]{8,}\b", "[redacted]" `
        -replace "(?i)\bsk-proj-[A-Za-z0-9_-]{8,}\b", "[redacted]" `
        -replace "(?i)\bsk-[A-Za-z0-9_-]{8,}\b", "[redacted]" `
        -replace "(?i)(authorization|bearer|token|secret|password|credential)[^ \t;]*", "[redacted]" `
        -replace "(?i)(gho|ghp|github_pat|sk-proj|sk)-[A-Za-z0-9_\-]+", "[redacted]"
    if ($redacted.Length -gt 300) {
        return $redacted.Substring(0, 300) + "..."
    }
    return $redacted
}

function Set-FailureDiagnostic($Summary, [string]$FailedAction, [string]$FailedStage, [string]$SafeError, [string]$NextManualAction) {
    if ($Summary.diagnostics.failure.failed_action) { return }
    $Summary.diagnostics.failure.failed_action = $FailedAction
    $Summary.diagnostics.failure.failed_stage = $FailedStage
    $Summary.diagnostics.failure.safe_error = ConvertTo-SafeBootstrapError $SafeError
    $Summary.diagnostics.failure.next_manual_action = $NextManualAction
}

function Set-FinalStatus($Summary) {
    if ($Summary.blockers.Count -gt 0) {
        $Summary.overall_status = "BLOCKED"
    }
    elseif ($Summary.attention.Count -gt 0 -or $Summary.manual_actions_required.Count -gt 0) {
        $Summary.overall_status = "ATTENTION"
    }
    else {
        $Summary.overall_status = "READY"
    }
}

function Get-Sha256FileHash([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "SHA-256 input file was not found: $Path"
    }
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    try {
        $hashBytes = $sha256.ComputeHash($stream)
        return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $stream.Dispose()
        $sha256.Dispose()
    }
}

function Resolve-LocalAppDataRoot {
    if ($env:LAWB_BOOTSTRAP_LOCALAPPDATA) {
        return $env:LAWB_BOOTSTRAP_LOCALAPPDATA
    }
    return $env:LOCALAPPDATA
}

function Resolve-CommandPath([string[]]$Names, [string[]]$ExtraDirectories = @()) {
    foreach ($name in $Names) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source) {
            return $found.Source
        }
    }
    foreach ($directory in $ExtraDirectories) {
        foreach ($name in $Names) {
            $candidate = Join-Path $directory $name
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }
    return $null
}

function Resolve-ExistingFileCaseInsensitive([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-Item -LiteralPath $Path).FullName
    }
    $directory = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        return $null
    }
    $match = Get-ChildItem -LiteralPath $directory -File -Force |
        Where-Object { [string]::Equals($_.Name, $leaf, [System.StringComparison]::OrdinalIgnoreCase) } |
        Select-Object -First 1
    if ($match) {
        return $match.FullName
    }
    return $null
}

function Invoke-SafeCommand([string]$CommandPath, [string[]]$Arguments, [string]$WorkingDirectory) {
    $extension = [System.IO.Path]::GetExtension($CommandPath).ToLowerInvariant()
    if ($extension -in @(".cmd", ".bat")) {
        $cmd = if ($env:COMSPEC) { $env:COMSPEC } else { "cmd.exe" }
        return & $cmd "/d" "/c" $CommandPath @Arguments 2>&1
    }
    return & $CommandPath @Arguments 2>&1
}

function Invoke-CapturedCommand([string]$CommandPath, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        $output = Invoke-SafeCommand -CommandPath $CommandPath -Arguments $Arguments -WorkingDirectory $WorkingDirectory
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        return [ordered]@{
            exit_code = $exitCode
            output = @($output)
            text = (@($output) -join "`n")
        }
    }
    catch {
        return [ordered]@{
            exit_code = 1
            output = @($_.Exception.Message)
            text = $_.Exception.Message
        }
    }
    finally {
        Pop-Location
    }
}

function Get-VersionLine([string]$CommandPath, [string]$WorkingDirectory) {
    if (-not $CommandPath) { return $null }
    $result = Invoke-CapturedCommand -CommandPath $CommandPath -Arguments @("--version") -WorkingDirectory $WorkingDirectory
    if ($result.exit_code -ne 0) { return $null }
    return (@($result.output) | Select-Object -First 1)
}

function Get-CodexPackageVersion([string]$NpmPrefix) {
    $packageJson = Join-Path $NpmPrefix "node_modules\@openai\codex\package.json"
    if (-not (Test-Path -LiteralPath $packageJson -PathType Leaf)) {
        return [ordered]@{ version = $null; source = "none" }
    }
    try {
        $package = Get-Content -LiteralPath $packageJson -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($package.version) {
            return [ordered]@{ version = [string]$package.version; source = "package_json" }
        }
    }
    catch {
        return [ordered]@{ version = $null; source = "unreadable" }
    }
    return [ordered]@{ version = $null; source = "unreadable" }
}

function Get-CodexFacts([string]$CommandPath, [string]$WorkingDirectory, [string]$NpmPrefix, [string]$ExpectedVersion) {
    $resolvedCommandPath = if ($CommandPath) { $CommandPath } else { $null }
    $commandVersion = $null
    $commandUsable = $false
    if ($resolvedCommandPath) {
        $result = Invoke-CapturedCommand -CommandPath $resolvedCommandPath -Arguments @("--version") -WorkingDirectory $WorkingDirectory
        if ($result.exit_code -eq 0) {
            $commandVersion = (@($result.output) | Select-Object -First 1)
            $commandUsable = [bool]$commandVersion
        }
    }
    $package = Get-CodexPackageVersion -NpmPrefix $NpmPrefix
    $source = if ($commandUsable) { "command" } else { $package.source }
    return [ordered]@{
        expected_path = $null
        path = $resolvedCommandPath
        command_usable = $commandUsable
        command_version = $commandVersion
        installed_version = $package.version
        installed_version_source = $source
        ready = ($commandUsable -and (Test-ExactVersion -Text $commandVersion -Expected $ExpectedVersion))
        auth_status = "UNKNOWN"
    }
}

function Add-CodexReadinessAttention($Summary, $CodexFacts) {
    if ($CodexFacts.path -and -not $CodexFacts.command_usable) {
        Add-Unique $Summary.attention "codex_command_unusable"
    }
    else {
        Add-Unique $Summary.attention "codex_missing_or_wrong_version"
    }
}

function Parse-VersionTuple([string]$Text) {
    if (-not $Text) { return $null }
    if ($Text -match "(\d+)\.(\d+)\.(\d+)") {
        return [version]::new([int]$Matches[1], [int]$Matches[2], [int]$Matches[3])
    }
    if ($Text -match "(\d+)\.(\d+)") {
        return [version]::new([int]$Matches[1], [int]$Matches[2])
    }
    return $null
}

function Test-MinVersion([string]$Text, [string]$Minimum) {
    $parsed = Parse-VersionTuple $Text
    if (-not $parsed) { return $false }
    return $parsed -ge ([version]$Minimum)
}

function Test-ExactVersion([string]$Text, [string]$Expected) {
    $parsed = Parse-VersionTuple $Text
    return $parsed -and ($parsed -eq ([version]$Expected))
}

function Resolve-VenvPython([string]$VenvRoot) {
    foreach ($name in @("python.exe", "python.cmd", "python.bat")) {
        $candidate = Join-Path $VenvRoot "Scripts\$name"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Test-PipReady([string]$PythonPath, [string]$RepoRootPath) {
    if (-not $PythonPath) {
        return [ordered]@{ ready = $false; output = "venv_python_missing" }
    }
    $result = Invoke-CapturedCommand -CommandPath $PythonPath -Arguments @("-m", "pip", "--version") -WorkingDirectory $RepoRootPath
    return [ordered]@{ ready = ($result.exit_code -eq 0); output = $result.text }
}

function Test-ImportsReady([string]$PythonPath, [string]$RepoRootPath) {
    if (-not $PythonPath) {
        return [ordered]@{ ready = $false; output = "venv_python_missing" }
    }
    $code = "import fastapi,pydantic,httpx,pytest,pypdf,docx; import local_runner_bridge.bridge_diagnostics"
    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = (Join-Path $RepoRootPath "src")
    try {
        $result = Invoke-CapturedCommand -CommandPath $PythonPath -Arguments @("-c", $code) -WorkingDirectory $RepoRootPath
        return [ordered]@{ ready = ($result.exit_code -eq 0); output = $result.text }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Ensure-PathEntry([string]$Entry, [bool]$Persist, $Summary) {
    if (-not $Entry) { return }
    $entries = @($env:PATH -split ";" | Where-Object { $_ })
    $exists = $false
    foreach ($existing in $entries) {
        if ([string]::Equals($existing.TrimEnd("\"), $Entry.TrimEnd("\"), [System.StringComparison]::OrdinalIgnoreCase)) {
            $exists = $true
            break
        }
    }
    if (-not $exists) {
        $env:PATH = $Entry + ";" + $env:PATH
        Add-Unique $Summary.path.current_process_added $Entry
    }
    if ($Persist) {
        $currentUserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        $userEntries = @($currentUserPath -split ";" | Where-Object { $_ })
        $userExists = $false
        foreach ($existing in $userEntries) {
            if ([string]::Equals($existing.TrimEnd("\"), $Entry.TrimEnd("\"), [System.StringComparison]::OrdinalIgnoreCase)) {
                $userExists = $true
                break
            }
        }
        if (-not $userExists) {
            $newUserPath = if ($currentUserPath) { $Entry + ";" + $currentUserPath } else { $Entry }
            [Environment]::SetEnvironmentVariable("PATH", $newUserPath, "User")
            Add-Unique $Summary.path.persisted_user_added $Entry
        }
    }
}

function Install-GhPortable($ExpectedExe, $InstallRoot, $CurrentDir, $Summary) {
    $version = $Manifest.github_cli.version
    $failedAction = "install_gh_$version"
    $zipName = $Manifest.github_cli.zip_name
    $checksumsName = $Manifest.github_cli.checksums_name
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lawb-gh-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    $stage = "download_zip"
    try {
        $zipPath = Join-Path $tempRoot $zipName
        $checksumsPath = Join-Path $tempRoot $checksumsName
        if ($ArtifactCacheDir) {
            Copy-Item -LiteralPath (Join-Path $ArtifactCacheDir $zipName) -Destination $zipPath
            $stage = "download_checksums"
            Copy-Item -LiteralPath (Join-Path $ArtifactCacheDir $checksumsName) -Destination $checksumsPath
        }
        else {
            Invoke-WebRequest -Uri $Manifest.github_cli.zip_url -OutFile $zipPath
            $stage = "download_checksums"
            Invoke-WebRequest -Uri $Manifest.github_cli.checksums_url -OutFile $checksumsPath
        }
        $stage = "checksum_verify"
        $hash = Get-Sha256FileHash -Path $zipPath
        $checksumLine = Get-Content -LiteralPath $checksumsPath -Encoding UTF8 |
            Where-Object {
                $parts = $_ -split "\s+"
                $parts | Where-Object { $_ -eq $zipName }
            } |
            Select-Object -First 1
        $checksumToken = $null
        if ($checksumLine -and ($checksumLine -match "(?i)\b[0-9a-f]{64}\b")) {
            $checksumToken = $Matches[0].ToLowerInvariant()
        }
        if (-not $checksumToken -or $checksumToken -ne $hash) {
            Add-Unique $Summary.blockers "gh_checksum_mismatch"
            Set-FailureDiagnostic -Summary $Summary -FailedAction $failedAction -FailedStage $stage -SafeError "GitHub CLI archive checksum did not match the manifest checksum." -NextManualAction "inspect artifact cache or run focused restore"
            return $false
        }
        $stage = "expand_archive"
        $extractRoot = Join-Path $tempRoot "extract"
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
        $newGh = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter "gh.exe" | Select-Object -First 1
        if (-not $newGh) {
            Add-Unique $Summary.blockers "gh_archive_missing_exe"
            Set-FailureDiagnostic -Summary $Summary -FailedAction $failedAction -FailedStage $stage -SafeError "GitHub CLI archive did not contain gh.exe." -NextManualAction "inspect artifact cache or run focused restore"
            return $false
        }
        $staging = Join-Path $tempRoot "stage"
        New-Item -ItemType Directory -Force -Path $staging | Out-Null
        $stage = "copy_exe"
        Copy-Item -LiteralPath $newGh.FullName -Destination (Join-Path $staging "gh.exe") -Force
        $stage = "version_probe"
        $versionLine = Get-VersionLine -CommandPath (Join-Path $staging "gh.exe") -WorkingDirectory $tempRoot
        if (-not (Test-ExactVersion -Text $versionLine -Expected $version)) {
            Add-Unique $Summary.blockers "gh_staged_version_invalid"
            Set-FailureDiagnostic -Summary $Summary -FailedAction $failedAction -FailedStage $stage -SafeError "Staged GitHub CLI version probe did not match the manifest version." -NextManualAction "inspect artifact cache or run focused restore"
            return $false
        }
        $stage = "copy_exe"
        New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
        New-Item -ItemType Directory -Force -Path $CurrentDir | Out-Null
        Copy-Item -LiteralPath (Join-Path $staging "gh.exe") -Destination (Join-Path $InstallRoot "gh.exe") -Force
        Copy-Item -LiteralPath (Join-Path $staging "gh.exe") -Destination $ExpectedExe -Force
        Add-Unique $Summary.actions_performed "installed_gh_2.95.0"
        return $true
    }
    catch {
        Add-Unique $Summary.blockers "gh_install_failed"
        Set-FailureDiagnostic -Summary $Summary -FailedAction $failedAction -FailedStage $stage -SafeError $_.Exception.Message -NextManualAction "inspect artifact cache or run focused restore"
        return $false
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }
}

function Invoke-Diagnostics($Summary, [string]$VenvPython, [string]$RepoRootPath) {
    if (-not $VenvPython) { return }
    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = (Join-Path $RepoRootPath "src")
    try {
        $result = Invoke-CapturedCommand -CommandPath $VenvPython -Arguments @("-m", "local_runner_bridge.bridge_diagnostics", "--repo-root", $RepoRootPath, "--pretty") -WorkingDirectory $RepoRootPath
        $Summary.diagnostics.invoked = $true
        if ($result.exit_code -eq 0) {
            try {
                $payload = $result.text | ConvertFrom-Json
                $Summary.diagnostics.status = $payload.status
                $Summary.diagnostics.reasons = @($payload.status_reasons)
                $Summary.diagnostics.raw = $payload
            }
            catch {
                Add-Unique $Summary.attention "diagnostics_json_unreadable"
            }
        }
        else {
            Add-Unique $Summary.attention "diagnostics_failed"
        }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

$Summary = New-Result

try {
    $ResolvedRepoRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RepoRoot).Path)
    $Summary.detected.repo_root = $ResolvedRepoRoot
    if (-not (Test-Path -LiteralPath (Join-Path $ResolvedRepoRoot ".git"))) {
        Add-Unique $Summary.blockers "repo_root_invalid"
    }

    $localAppData = Resolve-LocalAppDataRoot
    $ghRoot = Join-Path $localAppData "LocalAIWorkbench\gh"
    $ghInstallRoot = Join-Path $ghRoot $Manifest.github_cli.version
    $ghCurrentDir = Join-Path $ghRoot "current"
    $expectedGh = Join-Path $ghCurrentDir "gh.exe"
    $npmPrefix = Join-Path $localAppData "LocalAIWorkbench\npm"
    $expectedCodex = Join-Path $npmPrefix "codex.cmd"
    $venvRoot = Join-Path $ResolvedRepoRoot $Manifest.paths.venv
    $requirementsPath = Join-Path $ResolvedRepoRoot $Manifest.requirements

    $gitPath = Resolve-CommandPath @("git.exe", "git.cmd", "git.bat", "git")
    $pythonPath = Resolve-CommandPath @("python.exe", "python.cmd", "python.bat", "python")
    $nodeFallback = if ($env:LAWB_BOOTSTRAP_NODE_FALLBACK) { $env:LAWB_BOOTSTRAP_NODE_FALLBACK } else { $Manifest.paths.node_fallback }
    $nodePath = Resolve-CommandPath @("node.exe", "node.cmd", "node.bat", "node") @($nodeFallback)
    $npmPath = Resolve-CommandPath @("npm.cmd", "npm.exe", "npm.bat", "npm") @($nodeFallback)

    $Summary.detected.git = [ordered]@{ path = $gitPath; version = $null }
    if ($gitPath) {
        $Summary.detected.git.version = Get-VersionLine -CommandPath $gitPath -WorkingDirectory $ResolvedRepoRoot
    }
    else {
        Add-Unique $Summary.blockers "git_missing"
    }

    $Summary.detected.python = [ordered]@{ path = $pythonPath; version = $null; minimum_supported = $Manifest.python.minimum_version }
    if ($pythonPath) {
        $pythonVersion = Get-VersionLine -CommandPath $pythonPath -WorkingDirectory $ResolvedRepoRoot
        $Summary.detected.python.version = $pythonVersion
        if (-not (Test-MinVersion -Text $pythonVersion -Minimum $Manifest.python.minimum_version)) {
            Add-Unique $Summary.blockers "python_unsupported"
        }
    }
    else {
        Add-Unique $Summary.blockers "python_missing"
    }

    $Summary.detected.node = [ordered]@{ path = $nodePath; version = $null }
    if ($nodePath) {
        $nodeVersion = Get-VersionLine -CommandPath $nodePath -WorkingDirectory $ResolvedRepoRoot
        $Summary.detected.node.version = $nodeVersion
        $nodeParsed = Parse-VersionTuple $nodeVersion
        if (-not $nodeParsed -or $nodeParsed.Major -lt [int]$Manifest.codex.minimum_node_major) {
            Add-Unique $Summary.attention "node_unsupported_for_codex"
        }
    }
    else {
        Add-Unique $Summary.attention "node_missing"
    }

    $Summary.detected.npm = [ordered]@{ path = $npmPath; version = $null }
    if ($npmPath) {
        $Summary.detected.npm.version = Get-VersionLine -CommandPath $npmPath -WorkingDirectory $ResolvedRepoRoot
    }
    else {
        Add-Unique $Summary.attention "npm_missing"
    }

    $venvPython = Resolve-VenvPython $venvRoot
    $Summary.venv = [ordered]@{
        path = $venvRoot
        exists = (Test-Path -LiteralPath $venvRoot)
        python = $venvPython
        pip_ready = $false
        pip_output = $null
        status = "missing"
    }
    if (-not $venvPython -and $Apply -and $pythonPath -and $Summary.blockers.Count -eq 0) {
        Add-Unique $Summary.actions_planned "create_venv"
        $result = Invoke-CapturedCommand -CommandPath $pythonPath -Arguments @("-m", "venv", $venvRoot) -WorkingDirectory $ResolvedRepoRoot
        if ($result.exit_code -eq 0) {
            Add-Unique $Summary.actions_performed "created_venv"
            $venvPython = Resolve-VenvPython $venvRoot
            $Summary.venv.python = $venvPython
            $Summary.venv.exists = $true
            $Summary.venv.status = if ($venvPython) { "usable" } else { "missing_python_after_create" }
        }
        else {
            Add-Unique $Summary.blockers "venv_create_failed"
        }
    }
    elseif (-not $venvPython) {
        Add-Unique $Summary.attention "venv_missing"
    }

    $pipReady = Test-PipReady -PythonPath $venvPython -RepoRootPath $ResolvedRepoRoot
    $Summary.venv.pip_ready = $pipReady.ready
    $Summary.venv.pip_output = $pipReady.output
    if ($venvPython -and $pipReady.ready) {
        $Summary.venv.status = "usable"
        if (-not $Summary.actions_performed.Contains("created_venv")) {
            Add-Unique $Summary.actions_skipped_reused "reused_venv"
        }
    }
    elseif ($venvPython -and $Apply -and $Summary.blockers.Count -eq 0) {
        $Summary.venv.status = "pip_unusable"
        Add-Unique $Summary.actions_planned "repair_venv_pip"
        $repairResult = Invoke-CapturedCommand -CommandPath $venvPython -Arguments @("-m", "ensurepip", "--upgrade", "--default-pip") -WorkingDirectory $ResolvedRepoRoot
        if ($repairResult.exit_code -eq 0) {
            $pipReady = Test-PipReady -PythonPath $venvPython -RepoRootPath $ResolvedRepoRoot
            $Summary.venv.pip_ready = $pipReady.ready
            $Summary.venv.pip_output = $pipReady.output
            if ($pipReady.ready) {
                $Summary.venv.status = "usable"
                Add-Unique $Summary.actions_performed "repaired_venv_pip"
            }
            else {
                $Summary.venv.status = "pip_unusable_after_repair"
                Add-Unique $Summary.blockers "venv_pip_unusable_after_repair"
            }
        }
        else {
            $Summary.venv.status = "pip_repair_failed"
            Add-Unique $Summary.blockers "venv_pip_repair_failed"
            Set-FailureDiagnostic -Summary $Summary -FailedAction "repair_venv_pip" -FailedStage "dependency_install" -SafeError $repairResult.text -NextManualAction "inspect venv pip or recreate the reviewed course venv"
        }
    }
    elseif ($venvPython) {
        $Summary.venv.status = "pip_unusable"
        Add-Unique $Summary.attention "venv_pip_unusable"
    }

    $depsReady = if ($Summary.venv.pip_ready) {
        Test-ImportsReady -PythonPath $venvPython -RepoRootPath $ResolvedRepoRoot
    }
    else {
        [ordered]@{ ready = $false; output = "venv_pip_unusable" }
    }
    $Summary.dependencies = [ordered]@{
        requirements = $requirementsPath
        ready = $depsReady.ready
        status = $(if ($depsReady.ready) { "ready" } else { "missing_or_unverified" })
        rationale = "Derived from api/requirements.txt and top-level imports used by API routes, document extractors, FastAPI TestClient tests, pytest, pypdf, and python-docx."
    }
    if ($depsReady.ready) {
        Add-Unique $Summary.actions_skipped_reused "reused_python_dependencies"
    }
    elseif ($Apply -and $venvPython -and $Summary.venv.pip_ready -and (Test-Path -LiteralPath $requirementsPath)) {
        Add-Unique $Summary.actions_planned "install_requirements_course"
        $installResult = Invoke-CapturedCommand -CommandPath $venvPython -Arguments @("-m", "pip", "install", "-r", $requirementsPath) -WorkingDirectory $ResolvedRepoRoot
        if ($installResult.exit_code -eq 0) {
            Add-Unique $Summary.actions_performed "installed_requirements_course"
            $depsReady = Test-ImportsReady -PythonPath $venvPython -RepoRootPath $ResolvedRepoRoot
            $Summary.dependencies.ready = $depsReady.ready
            $Summary.dependencies.status = if ($depsReady.ready) { "ready" } else { "missing_or_unverified" }
        }
        else {
            Add-Unique $Summary.blockers "dependency_install_failed"
            Set-FailureDiagnostic -Summary $Summary -FailedAction "install_requirements_course" -FailedStage "dependency_install" -SafeError $installResult.text -NextManualAction "inspect requirements install output or run focused restore"
        }
    }
    else {
        Add-Unique $Summary.attention "dependencies_missing_or_unverified"
    }

    $existingGh = Resolve-ExistingFileCaseInsensitive $expectedGh
    $ghPath = if ($existingGh) { $existingGh } else { Resolve-CommandPath @("gh.exe", "gh.cmd", "gh.bat", "gh") }
    $ghVersion = Get-VersionLine -CommandPath $ghPath -WorkingDirectory $ResolvedRepoRoot
    $ghReady = $ghPath -and (Test-ExactVersion -Text $ghVersion -Expected $Manifest.github_cli.version)
    $Summary.detected.gh = [ordered]@{ expected_path = $expectedGh; path = $ghPath; version = $ghVersion; ready = [bool]$ghReady; authenticated = $false }
    if ($ghReady) {
        Add-Unique $Summary.actions_skipped_reused "reused_gh"
    }
    elseif ($Apply -and $Summary.blockers.Count -eq 0) {
        Add-Unique $Summary.actions_planned "install_gh_2.95.0"
        [void](Install-GhPortable -ExpectedExe $expectedGh -InstallRoot $ghInstallRoot -CurrentDir $ghCurrentDir -Summary $Summary)
        $existingGh = Resolve-ExistingFileCaseInsensitive $expectedGh
        $ghPath = if ($existingGh) { $existingGh } else { $ghPath }
        $ghVersion = Get-VersionLine -CommandPath $ghPath -WorkingDirectory $ResolvedRepoRoot
        $ghReady = $ghPath -and (Test-ExactVersion -Text $ghVersion -Expected $Manifest.github_cli.version)
        $Summary.detected.gh.path = $ghPath
        $Summary.detected.gh.version = $ghVersion
        $Summary.detected.gh.ready = [bool]$ghReady
    }
    else {
        Add-Unique $Summary.attention "gh_missing_or_wrong_version"
    }
    if ($ghReady) {
        $auth = Invoke-CapturedCommand -CommandPath $ghPath -Arguments @("auth", "status") -WorkingDirectory $ResolvedRepoRoot
        $Summary.detected.gh.authenticated = ($auth.exit_code -eq 0)
        if ($auth.exit_code -ne 0) {
            Add-Unique $Summary.manual_actions_required "gh_auth_login_required"
        }
    }

    $existingCodex = Resolve-ExistingFileCaseInsensitive $expectedCodex
    $codexPath = if ($existingCodex) { $existingCodex } else { Resolve-CommandPath @("codex.exe", "codex.cmd", "codex.bat", "codex") }
    $codexFacts = Get-CodexFacts -CommandPath $codexPath -WorkingDirectory $ResolvedRepoRoot -NpmPrefix $npmPrefix -ExpectedVersion $Manifest.codex.version
    $codexFacts.expected_path = $expectedCodex
    $codexReady = $codexPath -and $codexFacts.ready
    $Summary.detected.codex = $codexFacts
    if ($codexReady) {
        Add-Unique $Summary.actions_skipped_reused "reused_codex"
    }
    elseif ($Apply -and $npmPath -and $nodePath -and $Summary.blockers.Count -eq 0) {
        Add-Unique $Summary.actions_planned "install_codex_0.141.0"
        New-Item -ItemType Directory -Force -Path $npmPrefix | Out-Null
        $installCodex = Invoke-CapturedCommand -CommandPath $npmPath -Arguments @("install", "--global", "--prefix", $npmPrefix, "$($Manifest.codex.package)@$($Manifest.codex.version)") -WorkingDirectory $ResolvedRepoRoot
        if ($installCodex.exit_code -eq 0) {
            Add-Unique $Summary.actions_performed "installed_codex_0.141.0"
            $existingCodex = Resolve-ExistingFileCaseInsensitive $expectedCodex
            $codexPath = $existingCodex
            $codexFacts = Get-CodexFacts -CommandPath $codexPath -WorkingDirectory $ResolvedRepoRoot -NpmPrefix $npmPrefix -ExpectedVersion $Manifest.codex.version
            $codexFacts.expected_path = $expectedCodex
            $codexReady = $codexPath -and $codexFacts.ready
            $Summary.detected.codex = $codexFacts
            if (-not $codexReady) {
                Add-CodexReadinessAttention -Summary $Summary -CodexFacts $codexFacts
            }
        }
        else {
            Add-Unique $Summary.attention "codex_install_failed"
            Set-FailureDiagnostic -Summary $Summary -FailedAction "install_codex_0.141.0" -FailedStage "npm_install" -SafeError $installCodex.text -NextManualAction "inspect npm/node setup or run focused restore"
        }
    }
    else {
        Add-CodexReadinessAttention -Summary $Summary -CodexFacts $codexFacts
    }
    if (-not $codexReady -and (-not $nodePath -or -not $npmPath)) {
        Add-Unique $Summary.manual_actions_required "node_npm_required_for_codex"
    }

    $ghDir = Split-Path -Parent $expectedGh
    $codexDir = $npmPrefix
    $Summary.path.required_entries_present = [ordered]@{
        gh = ($env:PATH -split ";" | Where-Object { [string]::Equals($_.TrimEnd("\"), $ghDir.TrimEnd("\"), [System.StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
        codex = ($env:PATH -split ";" | Where-Object { [string]::Equals($_.TrimEnd("\"), $codexDir.TrimEnd("\"), [System.StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    }
    if ($Apply) {
        if ($ghReady) { Ensure-PathEntry -Entry $ghDir -Persist:$PersistUserPath -Summary $Summary }
        if ($codexReady) { Ensure-PathEntry -Entry $codexDir -Persist:$PersistUserPath -Summary $Summary }
    }

    if ($venvPython -and $Summary.venv.pip_ready -and $Summary.dependencies.ready) {
        Invoke-Diagnostics -Summary $Summary -VenvPython $venvPython -RepoRootPath $ResolvedRepoRoot
    }

    Set-FinalStatus $Summary
}
catch {
    Add-Unique $Summary.blockers "unexpected_bootstrap_failure"
    Set-FailureDiagnostic -Summary $Summary -FailedAction "bootstrap_course_environment" -FailedStage "unexpected_failure" -SafeError $_.Exception.Message -NextManualAction "inspect bootstrap JSON diagnostics and run focused restore"
    Set-FinalStatus $Summary
    if ($Json) {
        $Summary | ConvertTo-Json -Depth 20
    }
    else {
        $Summary | ConvertTo-Json -Depth 20
    }
    exit 3
}

if ($Json) {
    $Summary | ConvertTo-Json -Depth 20
}
else {
    Write-Host "Local AI Workbench course environment bootstrap"
    Write-Host "Mode: $($Summary.mode)"
    Write-Host "Status: $($Summary.overall_status)"
    Write-Host ""
    $Summary | ConvertTo-Json -Depth 20
}

if ($Summary.overall_status -eq "BLOCKED") {
    exit 2
}
exit 0
