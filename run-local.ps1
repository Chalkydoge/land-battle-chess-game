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

    throw "未检测到 Python 3。请先安装 Python 3.11+，并确保命令行可用。"
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

    throw "未找到可用端口。请关闭占用 5000-5019 端口的程序后重试。"
}

$pythonLauncher = Find-PythonLauncher
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$requirementsFile = Join-Path $repoRoot "requirements.txt"
$requirementsStamp = Join-Path $repoRoot ".venv\.requirements.sha256"

if (-not (Test-Path $venvPython)) {
    Write-Host "正在创建本地虚拟环境 .venv ..."
    & $pythonLauncher.Exe @($pythonLauncher.Args + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) {
        throw "创建虚拟环境失败。"
    }
}

if (-not (Test-Path $requirementsFile)) {
    throw "未找到 requirements.txt。"
}

$currentRequirementsHash = (Get-FileHash $requirementsFile -Algorithm SHA256).Hash
$savedRequirementsHash = if (Test-Path $requirementsStamp) {
    (Get-Content $requirementsStamp -Raw).Trim()
} else {
    ""
}

if ($currentRequirementsHash -ne $savedRequirementsHash) {
    Write-Host "正在安装或更新依赖 ..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "升级 pip 失败。"
    }

    & $venvPython -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "安装依赖失败。"
    }

    Set-Content -Path $requirementsStamp -Value $currentRequirementsHash -Encoding ASCII
} else {
    Write-Host "依赖已就绪，跳过重复安装。"
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
Write-Host "本地服务准备启动 ..."
Write-Host "访问地址: $url"
Write-Host "关闭窗口或按 Ctrl+C 即可停止服务。"
Write-Host ""

try {
    $appExitCode = 1
    & $venvPython app.py
    $appExitCode = $LASTEXITCODE
} finally {
    if ($browserJob) {
        Receive-Job $browserJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $browserJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

exit $appExitCode
