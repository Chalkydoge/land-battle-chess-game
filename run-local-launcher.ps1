$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Find-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{
            Exe = "py"
            Args = @("-3")
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{
            Exe = "python"
            Args = @()
        }
    }

    throw "Python 3 was not found. Please install Python 3.11+ and try again."
}

function Get-FreeLocalPort {
    param(
        [int]$PreferredPort = 5000,
        [int]$Attempts = 20
    )

    for ($port = $PreferredPort; $port -lt ($PreferredPort + $Attempts); $port++) {
        $listener = $null
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $listener.Start()
            return $port
        } catch {
            continue
        } finally {
            if ($listener -ne $null) {
                $listener.Stop()
            }
        }
    }

    throw "No free port was found in the range 5000-5019."
}

$pythonLauncher = Find-PythonLauncher
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$requirementsFile = Join-Path $repoRoot "requirements.txt"
$requirementsStamp = Join-Path $repoRoot ".venv\.requirements.sha256"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating local virtual environment (.venv) ..."
    & $pythonLauncher.Exe @($pythonLauncher.Args + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

if (-not (Test-Path $requirementsFile)) {
    throw "requirements.txt was not found."
}

$currentRequirementsHash = (Get-FileHash $requirementsFile -Algorithm SHA256).Hash
$savedRequirementsHash = if (Test-Path $requirementsStamp) {
    (Get-Content $requirementsStamp -Raw).Trim()
} else {
    ""
}

if ($currentRequirementsHash -ne $savedRequirementsHash) {
    Write-Host "Installing or updating dependencies ..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & $venvPython -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies."
    }

    Set-Content -Path $requirementsStamp -Value $currentRequirementsHash -Encoding ASCII
} else {
    Write-Host "Dependencies are already up to date."
}

$port = Get-FreeLocalPort
$url = "http://127.0.0.1:$port/"

$env:APP_HOST = "127.0.0.1"
$env:APP_PORT = "$port"
$env:APP_DEBUG = "0"

$browserJob = Start-Job -ArgumentList $url -ScriptBlock {
    param($TargetUrl)

    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 1 | Out-Null
            Start-Process $TargetUrl
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
}

Write-Host ""
Write-Host "Starting local server ..."
Write-Host "Game URL: $url"
Write-Host "Press Ctrl+C to stop the server."
Write-Host ""

$appExitCode = 1

try {
    & $venvPython app.py
    $appExitCode = $LASTEXITCODE
} finally {
    if ($browserJob) {
        Receive-Job $browserJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $browserJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

exit $appExitCode
