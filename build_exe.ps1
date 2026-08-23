[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildVenv = Join-Path $ProjectRoot ".venv-build"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$SpecFile = Join-Path $ProjectRoot "DanmakuStudio.spec"
$OutputDir = Join-Path $ProjectRoot "dist\DanmakuStudio"
$OutputExe = Join-Path $OutputDir "DanmakuStudio.exe"

Set-Location $ProjectRoot

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python command was not found: $Python"
}

if (-not (Test-Path -LiteralPath $BuildPython)) {
    Write-Host "Creating build virtual environment..."
    & $Python -m venv $BuildVenv
}

if (-not $SkipInstall) {
    Write-Host "Installing build dependencies..."
    & $BuildPython -m pip install --upgrade pip
    & $BuildPython -m pip install -e .
    & $BuildPython -m pip install pyinstaller
}

Write-Host "Building DanmakuStudio..."
& $BuildPython -m PyInstaller --noconfirm --clean $SpecFile

$ConfigSource = Join-Path $ProjectRoot "danmakustudio.yaml"
if (Test-Path -LiteralPath $ConfigSource) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    Copy-Item -LiteralPath $ConfigSource -Destination $OutputDir -Force
}

if (-not (Test-Path -LiteralPath $OutputExe)) {
    throw "Build finished, but executable was not found: $OutputExe"
}

Write-Host ""
Write-Host "Done: $OutputExe"
Write-Host "Run it by double-clicking the exe, or from PowerShell:"
Write-Host "  $OutputExe"
