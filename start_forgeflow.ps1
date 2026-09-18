$ErrorActionPreference = 'Stop'

# 1. Set working directory to the directory where this script resides
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $ScriptDir) {
    $ScriptDir = $PWD.Path
}
Set-Location -Path $ScriptDir

# 2. Verify the ForgeFlow virtual environment exists
$PythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: ForgeFlow virtual environment not found at $($PythonExe)" -ForegroundColor Red
    Write-Host "Please ensure you have created the virtual environment and installed dependencies." -ForegroundColor Yellow
    exit 1
}

# 3. Terminate any existing instance on port 8000
Write-Host "Checking for existing ForgeFlow instance on port 8000..." -ForegroundColor Cyan
$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        $pidToKill = $conn.OwningProcess
        if ($pidToKill) {
            Write-Host "Found existing process (PID: $pidToKill). Terminating..." -ForegroundColor Yellow
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

# 4. Set the required ForgeFlow runtime environment for the current process
$env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "agy"
$env:ABACUS_REVIEWER_ENABLED = "true"
$env:ABACUS_REVIEWER_FALLBACK_ENABLED = "false"
$env:FORGEFLOW_AGY_TIMEOUT = "600"

# 5. Print a small startup summary
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " ForgeFlow" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Provider:    Agy"
Write-Host "Reviewer:    Abacus"
Write-Host "Agy timeout: 600s"
Write-Host "URL:         http://127.0.0.1:8000"
Write-Host "Mode:        no auto-reload"
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Press CTRL+C to safely shut down." -ForegroundColor Yellow
Write-Host ""

# Optional convenience: open browser shortly after server start
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8000"
} | Out-Null

# 6. Start ForgeFlow in a loop so we can restart it from the UI
while ($true) {
    & $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop none
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 42) {
        Write-Host ""
        Write-Host "Restart triggered from UI. Restarting ForgeFlow..." -ForegroundColor Magenta
        Write-Host ""
        Start-Sleep -Seconds 1
    } else {
        Write-Host "ForgeFlow shut down."
        break
    }
}
