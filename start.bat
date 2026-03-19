@echo off
title Easy AIGC

echo ========================================
echo     Easy AIGC
echo ========================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found. Install: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

cd /d "%~dp0"

if not exist ".venv\" (
    echo [INFO] First run, installing deps...
    uv sync
    echo.
)

if not exist "output\" mkdir "output"

:: Free port 8000 if occupied
echo [INFO] Checking port 8000...
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [INFO] Killing PID %%p on port 8000...
    taskkill /F /PID %%p >nul 2>&1
)
:: Wait for port release
timeout /t 2 /nobreak >nul

echo [INFO] Frontend: http://localhost:8000
echo [INFO] Swagger:  http://localhost:8000/docs
echo.

start "" "http://localhost:8000"

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

pause
