# Windows 版开发服务器启停脚本（scripts/dev_server.sh 的 PowerShell 对应实现）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\dev_server.ps1 <start|stop|restart|status>
#   或通过薄包装：scripts\dev_server.bat start
#
# 端口默认后端 5000 / 前端 5180，与 vite.config.ts 里硬编码指向
# 127.0.0.1:5000 的代理一致——后端端口覆盖只影响直连后端的场景。
#
# 说明：应用通过 python-dotenv 自行加载根目录 .env（config.py），
# 本脚本不代劳。环境变量覆盖与 bash 版同名：
#   DEV_SERVER_BACKEND_PORT / DEV_SERVER_FRONTEND_PORT /
#   DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT / DEV_SERVER_RUN_DIR /
#   DEV_SERVER_BACKEND_DIR / DEV_SERVER_FRONTEND_DIR /
#   DEV_SERVER_BACKEND_CMD / DEV_SERVER_FRONTEND_CMD / DEV_SERVER_SKIP_CHECKS

param(
    [Parameter(Position = 0)]
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RunDir = if ($env:DEV_SERVER_RUN_DIR) { $env:DEV_SERVER_RUN_DIR } else { Join-Path $RootDir ".run" }
$BackendDir = if ($env:DEV_SERVER_BACKEND_DIR) { $env:DEV_SERVER_BACKEND_DIR } else { $RootDir }
$FrontendDir = if ($env:DEV_SERVER_FRONTEND_DIR) { $env:DEV_SERVER_FRONTEND_DIR } else { Join-Path $RootDir "frontend" }

$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"
$BackendLogFile = Join-Path $RunDir "backend.log"
$FrontendLogFile = Join-Path $RunDir "frontend.log"

$BackendPort = if ($env:DEV_SERVER_BACKEND_PORT) { [int]$env:DEV_SERVER_BACKEND_PORT } else { 5000 }
$FrontendPort = if ($env:DEV_SERVER_FRONTEND_PORT) { [int]$env:DEV_SERVER_FRONTEND_PORT } else { 5180 }
$FrontendCleanupMaxPort = if ($env:DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT) { [int]$env:DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT } else { $FrontendPort + 18 }
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

# Vite 占用时级联到下一个空闲端口，启动前清一小段范围
$FrontendCleanupMaxPort = [Math]::Max($FrontendCleanupMaxPort, $FrontendPort)

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$SkipChecks = ($env:DEV_SERVER_SKIP_CHECKS -eq "1")


function Write-Usage {
    Write-Host "Usage: powershell -File scripts\dev_server.ps1 <start|stop|restart|status>"
    Write-Host ""
    Write-Host "Ports default to backend 5000 / frontend 5180. Backend port override only"
    Write-Host "takes effect for direct backend access: the Vite proxy in"
    Write-Host "frontend/vite.config.ts hardcodes 127.0.0.1:5000."
    Write-Host ""
    Write-Host "  DEV_SERVER_BACKEND_PORT             backend port           (default 5000)"
    Write-Host "  DEV_SERVER_FRONTEND_PORT            frontend port          (default 5180)"
    Write-Host "  DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT  kill range end       (default FRONTEND_PORT+18)"
    Write-Host "  DEV_SERVER_RUN_DIR                  pid/log dir            (default .run)"
    Write-Host "  DEV_SERVER_BACKEND_DIR              backend working dir    (default repo root)"
    Write-Host "  DEV_SERVER_FRONTEND_DIR             frontend working dir   (default frontend)"
    Write-Host "  DEV_SERVER_BACKEND_CMD              command override"
    Write-Host "  DEV_SERVER_FRONTEND_CMD             command override"
    Write-Host "  DEV_SERVER_SKIP_CHECKS              1 = skip dependency check"
}


function Ensure-RunDir {
    if (-not (Test-Path $RunDir)) {
        New-Item -ItemType Directory -Path $RunDir | Out-Null
    }
}


function Read-Pid([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $null }
    $text = (Get-Content $PidFile -Raw -ErrorAction SilentlyContinue)
    if ($null -eq $text) { return $null }
    $text = $text.Trim()
    return ($(if ($text -match '^\d+$') { [int]$text } else { $null }))
}


function Test-ProcessAlive([int]$ProcId) {
    return ($null -ne (Get-Process -Id $ProcId -ErrorAction SilentlyContinue))
}


function Test-Running([string]$PidFile) {
    $procId = Read-Pid $PidFile
    if ($null -eq $procId) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        return $false
    }
    if (Test-ProcessAlive $procId) { return $true }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    return $false
}


function Get-ListeningPids([int]$Port) {
    # Get-NetTCPConnection 在老系统可能不存在，回退 netstat 解析
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            return @($conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
        }
        return @()
    } catch {
        $pids = @()
        $lines = netstat -ano | Select-String "LISTENING"
        foreach ($line in $lines) {
            $parts = ($line.ToString() -split '\s+') | Where-Object { $_ -ne "" }
            # 协议 本地地址 远程地址 状态 PID
            if ($parts.Count -ge 5 -and $parts[1] -match "[:.]$Port$") {
                $pids += [int]$parts[4]
            }
        }
        return @($pids | Select-Object -Unique)
    }
}


function Stop-PortListeners([int]$Port) {
    $procIds = Get-ListeningPids $Port
    if ($procIds.Count -eq 0) { return }
    foreach ($procId in $procIds) {
        # /T 连同子进程一起结束（uvicorn --reload、npm 子进程等孤儿）
        taskkill /PID $procId /T /F 2>$null | Out-Null
    }
    for ($i = 0; $i -lt 10; $i++) {
        if ((Get-ListeningPids $Port).Count -eq 0) { return }
        Start-Sleep -Milliseconds 300
    }
    foreach ($procId in (Get-ListeningPids $Port)) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}


function Clear-FrontendPorts {
    for ($port = $FrontendPort; $port -le $FrontendCleanupMaxPort; $port++) {
        Stop-PortListeners $port
    }
}


function Start-Service([string]$Name, [string]$WorkDir, [string]$InnerCommand, [string]$PidFile, [string]$LogFile) {
    if (Test-Running $PidFile) {
        Write-Host "$Name already running (pid $(Read-Pid $PidFile))"
        return
    }

    # 不直接把命令塞进 Start-Process -ArgumentList：路径含空格 + 嵌套引号
    # 在 PS 5.1 的参数拼接下会碎。改为把命令写进临时批处理文件，
    # 引号只存在于文件内容里，cmd /c 只需处理单个（可能带空格的）文件路径。
    $taskFile = Join-Path $RunDir "$Name-task.cmd"
    @"
@echo off
cd /d "$WorkDir"
$InnerCommand >> "$LogFile" 2>&1
"@ | Set-Content -Path $taskFile -Encoding ASCII

    $proc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", $taskFile `
        -WindowStyle Hidden -PassThru
    Set-Content -Path $PidFile -Value $proc.Id

    Start-Sleep -Seconds 1

    if (-not (Test-Running $PidFile)) {
        Write-Host "failed to start $Name; see $LogFile"
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        exit 1
    }
    Write-Host "started $Name (pid $(Read-Pid $PidFile))"
}


function Stop-Service([string]$Name, [string]$PidFile, [int]$Port) {
    $procId = Read-Pid $PidFile
    if ($null -ne $procId -and (Test-ProcessAlive $procId)) {
        taskkill /PID $procId /T 2>$null | Out-Null
        for ($i = 0; $i -lt 20; $i++) {
            if (-not (Test-ProcessAlive $procId)) { break }
            Start-Sleep -Milliseconds 250
        }
        if (Test-ProcessAlive $procId) {
            taskkill /PID $procId /T /F 2>$null | Out-Null
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue

    # 兜底：清掉仍在监听端口的孤儿进程
    Stop-PortListeners $Port
    Write-Host "stopped $Name"
}


function Show-Status([string]$Name, [string]$PidFile, [string]$Url, [int]$Port) {
    if (Test-Running $PidFile) {
        Write-Host "$Name : running (pid $(Read-Pid $PidFile)) $Url"
        return $true
    }
    if ((Get-ListeningPids $Port).Count -gt 0) {
        Write-Host "$Name : running (port $Port) $Url"
        return $true
    }
    Write-Host "$Name : stopped"
    return $false
}


function Require-Dependencies {
    if ($SkipChecks) { return }

    if (-not (Test-Path $VenvPython) -and ($null -eq (Get-Command python -ErrorAction SilentlyContinue))) {
        Write-Host "missing backend runtime: create $RootDir\.venv or install python on PATH"
        exit 1
    }
    if (-not (Test-Path (Join-Path $BackendDir "run.py"))) {
        Write-Host "missing backend entrypoint: $(Join-Path $BackendDir 'run.py')"
        exit 1
    }
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "missing frontend dependencies: $(Join-Path $FrontendDir 'node_modules')"
        exit 1
    }
    if ($null -eq (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        Write-Host "npm not found on PATH (install Node.js)"
        exit 1
    }
}


function Start-All {
    Ensure-RunDir
    Require-Dependencies

    # 默认命令：有 venv 用 venv 的 python，run.py 从 PORT 环境变量读端口
    $backendCmd = $env:DEV_SERVER_BACKEND_CMD
    if (-not $backendCmd) {
        $pythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
        $backendCmd = "set `"PORT=$BackendPort`" && `"$pythonExe`" run.py"
    }
    $frontendCmd = if ($env:DEV_SERVER_FRONTEND_CMD) { $env:DEV_SERVER_FRONTEND_CMD } else { "npm run dev -- --host 127.0.0.1 --port $FrontendPort" }

    # 清掉上次启动残留的日志
    Set-Content -Path $BackendLogFile -Value $null
    Set-Content -Path $FrontendLogFile -Value $null

    Start-Service "backend" $BackendDir $backendCmd $BackendPidFile $BackendLogFile
    Clear-FrontendPorts
    Start-Service "frontend" $FrontendDir $frontendCmd $FrontendPidFile $FrontendLogFile
    Write-Host "backend url: $BackendUrl"
    Write-Host "frontend url: $FrontendUrl"
}


function Stop-All {
    Ensure-RunDir
    Stop-Service "backend" $BackendPidFile $BackendPort
    Stop-Service "frontend" $FrontendPidFile $FrontendPort
    Clear-FrontendPorts
}


function Show-AllStatus {
    Ensure-RunDir
    $anyRunning = $false
    $anyRunning = (Show-Status "backend" $BackendPidFile $BackendUrl $BackendPort) -or $anyRunning
    $anyRunning = (Show-Status "frontend" $FrontendPidFile $FrontendUrl $FrontendPort) -or $anyRunning
    if (-not $anyRunning) { exit 1 }
}


switch ($Command) {
    "start"   { Start-All }
    "stop"    { Stop-All }
    "restart" { Stop-All; Start-All }
    "status"  { Show-AllStatus }
    default   { Write-Usage; exit 1 }
}
