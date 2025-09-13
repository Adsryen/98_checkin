@echo off
chcp 65001 >nul
title 98 Checkin Launcher

echo 98 Checkin Launcher
echo ================================

echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not installed or not in PATH
    echo Please install Python 3.8+ and add to PATH
    pause
    exit /b 1
)
echo Python ready

echo Checking port 9898...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9898') do (
    echo Terminating process %%a...
    taskkill /pid %%a /f >nul 2>&1
)

echo Starting service...
echo Access URL: http://127.0.0.1:9898
echo Press Ctrl+C to stop service
echo ================================

python -m sehuatang_bot serve --host 127.0.0.1 --port 9898

echo.
echo Service stopped
pause
