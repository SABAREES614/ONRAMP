@echo off
REM ============================================================
REM  ONRAMP - start all services
REM    1) Neuro-SAN server (port 8080)  -> window "ONRAMP-NeuroSAN"
REM    2) ONRAMP app server (port 8000) -> window "ONRAMP-App"
REM  Then opens the app in your default browser.
REM  Run shutdown.bat to stop everything.
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo  ONRAMP startup
echo  ==============
echo  Project: %cd%

if not exist ".venv\Scripts\ns.exe" (
    echo  [ERROR] .venv not found. Run this first in PowerShell:
    echo          uv sync --extra dev --link-mode copy
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [WARN] No .env file found. The Concierge review needs an LLM API key.
    echo         Set one on the Settings page, or create .env from .env.example.
)

echo  Starting Neuro-SAN server (window: ONRAMP-NeuroSAN) ...
start "ONRAMP-NeuroSAN" "%~dp0_run_neurosan.bat"

echo  Waiting for the agent network to load ...
timeout /t 12 /nobreak >nul

echo  Starting ONRAMP app server (window: ONRAMP-App) ...
start "ONRAMP-App" "%~dp0_run_app.bat"

timeout /t 6 /nobreak >nul

echo  Opening http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"

echo.
echo  Launched. Two server windows are now open:
echo    - ONRAMP-NeuroSAN  (agent network, port 8080)
echo    - ONRAMP-App       (web app + API, port 8000)
echo.
echo  Health check: http://127.0.0.1:8000/api/health
echo  To stop everything, run: shutdown.bat
echo.
endlocal
