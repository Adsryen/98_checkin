#!/usr/bin/env pwsh
# 98 Checkin Quick Start Script

param(
    [int]$Port = 9898,
    [string]$BindHost = "127.0.0.1",
    [string]$ConfigPath = "",
    [switch]$Public,
    [switch]$Help
)

# Set UTF-8 encoding
try {
    if ($IsWindows) { cmd /c "chcp 65001 >nul 2>&1" }
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

# Show help
if ($Help) {
    Write-Host "98 Checkin Quick Start Script" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\start.ps1                      # Default start"
    Write-Host "  .\start.ps1 -Port 8080           # Custom port"
    Write-Host "  .\start.ps1 -Public              # Public access"
    Write-Host "  .\start.ps1 -ConfigPath config.yaml  # Custom config"
    Write-Host "  .\start.ps1 -Help                # Show help"
    Write-Host ""
    Write-Host "Access URLs:"
    Write-Host "  Tasks: http://127.0.0.1:9898/tasks"
    Write-Host "  Accounts: http://127.0.0.1:9898/accounts"
    Write-Host "  Settings: http://127.0.0.1:9898/settings"
    exit 0
}

# Set host for public access
if ($Public) {
    $BindHost = "0.0.0.0"
    Write-Warning "Public mode enabled, make sure ADMIN_PASSWORD is set"
}

Write-Host "98 Checkin Startup Script" -ForegroundColor Magenta
Write-Host "=========================" -ForegroundColor Gray

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "Python ready: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Error "Python check failed: $_"
    Write-Host "Please install Python 3.8+ and add to PATH" -ForegroundColor Red
    exit 1
}

# Check dependencies
if (!(Test-Path "requirements.txt")) {
    Write-Error "requirements.txt not found, run from project root"
    exit 1
}

# Check port
Write-Host "Checking port $Port..." -ForegroundColor Yellow
try {
    $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        $pid = $existing.OwningProcess
        Write-Host "Terminating process $pid on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Write-Host "Port $Port cleared" -ForegroundColor Green
    } else {
        Write-Host "Port $Port available" -ForegroundColor Green
    }
} catch {
    Write-Host "Port check failed, continuing..." -ForegroundColor Yellow
}

# Build command
$serveArgs = @("serve", "--host", $BindHost, "--port", $Port)
if ($ConfigPath) {
    if (!(Test-Path $ConfigPath)) {
        Write-Error "Config file not found: $ConfigPath"
        exit 1
    }
    $serveArgs += @("--config", $ConfigPath)
}

# Show config
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Address: http://$($BindHost):$($Port)" -ForegroundColor White
Write-Host "  Config: $(if($ConfigPath){$ConfigPath}else{'Auto search'})" -ForegroundColor White
if ($env:ADMIN_PASSWORD) {
    Write-Host "  Admin Password: Set" -ForegroundColor Green
} else {
    Write-Host "  Admin Password: Not set" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting 98 Checkin Service..." -ForegroundColor Magenta
Write-Host "=========================" -ForegroundColor Gray

# Start service
try {
    python -m sehuatang_bot @serveArgs
} catch {
    Write-Error "Startup failed: $_"
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Install dependencies: pip install -r requirements.txt"
    Write-Host "2. Check config file format"
    Write-Host "3. Check if port $Port is occupied"
    Write-Host "4. Run .\start.ps1 -Help for options"
    exit 1
} finally {
    Write-Host ""
    Write-Host "Service stopped" -ForegroundColor Gray
}