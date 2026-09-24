[CmdletBinding()]
param()

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @()
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        $displayArgs = $ArgumentList -join " "
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $displayArgs"
    }
}

function Resolve-ProjectPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Path))
}

function Resolve-PythonCommand {
    param(
        [string]$Python
    )

    if ($Python) {
        return $Python
    }

    $candidates = @()
    $pythonInstallRoots = @(
        (Join-Path (
            [Environment]::GetFolderPath("LocalApplicationData")
        ) "Programs\Python"),
        [Environment]::GetFolderPath("ProgramFiles")
    )
    foreach ($pythonInstallRoot in $pythonInstallRoots) {
        if (Test-Path -LiteralPath $pythonInstallRoot) {
            $candidates += Get-ChildItem -LiteralPath $pythonInstallRoot -Directory |
                Where-Object { $_.Name -match '^Python3\d+$' } |
                Sort-Object { [int]($_.Name -replace '^Python', '') } -Descending |
                ForEach-Object { Join-Path $_.FullName "python.exe" }
        }
    }

    $pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        $candidateVersionText = & $candidate -c (
            "import sys; print('.'.join(map(str, sys.version_info[:3])))"
        ) 2>$null
        if ($LASTEXITCODE -ne 0) {
            continue
        }

        try {
            $candidateVersion = [Version]$candidateVersionText
        }
        catch {
            continue
        }

        if ($candidateVersion -ge [Version]"3.13") {
            return $candidate
        }
    }

    throw "Python 3.13 or newer was not found. Install it from python.org or pass -Python with the full path to python.exe."
}

function Assert-SupportedPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python
    )

    if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
        throw "Python command was not found: $Python"
    }

    $versionText = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query Python version: $Python"
    }

    try {
        $version = [Version]$versionText
    }
    catch {
        throw "Unable to parse Python version: $versionText"
    }

    if ($version -lt [Version]"3.13") {
        throw "DanmakuStudio requires Python 3.13 or newer; found $versionText"
    }

    Write-Host "Using Python $versionText"
}

function Get-VenvPythonPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VenvPath
    )

    return Join-Path $VenvPath "Scripts\python.exe"
}

function Sync-LockedEnvironment {
    param(
        [string]$ProjectRoot,
        [string]$VenvPath,
        [string]$Python = "",
        [switch]$CheckOnly
    )

    $uvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw "uv 0.12.17+ is required. Install with: python -m pip install uv==0.12.17"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "uv.lock"))) {
        throw "uv.lock is required. Restore the committed lockfile before continuing."
    }
    $previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
    try {
        $env:UV_PROJECT_ENVIRONMENT = $VenvPath
        $syncArgs = @("sync", "--project", $ProjectRoot, "--locked", "--all-groups", "--no-python-downloads")
        if ($Python) { $syncArgs += @("--python", $Python) }
        if ($CheckOnly) {
            if (-not (Test-Path -LiteralPath (Get-VenvPythonPath -VenvPath $VenvPath))) {
                throw "Environment is missing: $VenvPath. Run setup.ps1 first."
            }
            Invoke-CheckedCommand -FilePath $uvCommand.Source -ArgumentList ($syncArgs + @("--check", "--no-build-isolation"))
        }
        else {
            # Install the locked build backend before building the editable project.
            Invoke-CheckedCommand -FilePath $uvCommand.Source -ArgumentList ($syncArgs + @("--no-install-project"))
            Invoke-CheckedCommand -FilePath $uvCommand.Source -ArgumentList ($syncArgs + @("--no-build-isolation"))
        }
    }
    finally {
        $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    }
}
