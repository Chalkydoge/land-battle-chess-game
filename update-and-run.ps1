$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. Please install $Name and try again."
    }
}

Require-Command -Name "git"

if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
    throw "This folder is not a Git repository. Clone the repository first, then run this script."
}

$localChanges = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read Git status."
}
if (-not [string]::IsNullOrWhiteSpace(($localChanges -join "`n"))) {
    Write-Host ""
    Write-Host "Local changes detected. Auto-update aborted to avoid overwriting your work." -ForegroundColor Yellow
    Write-Host "Please commit or stash changes, then run update-and-run again." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$branch = (git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) {
    throw "Could not determine the current branch."
}

Write-Host ""
Write-Host "Updating from remote..." -ForegroundColor Cyan
Write-Host "Current branch: $branch"

$upstream = ((git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null) | Out-String).Trim()

if ([string]::IsNullOrWhiteSpace($upstream)) {
    Write-Host "No upstream configured. Trying origin/$branch ..."
    git fetch origin $branch
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch origin/$branch."
    }

    git branch --set-upstream-to "origin/$branch" $branch
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set upstream branch origin/$branch."
    }
}

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    throw "Git pull failed. Resolve repository state manually, then run update-and-run again."
}

Write-Host "Update completed. Starting local launcher..." -ForegroundColor Green
Write-Host ""

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "run-local-launcher.ps1")
exit $LASTEXITCODE
