@echo off
REM Helper launched by startup.bat in its own window.
REM Runs the Neuro-SAN server (port 8080) AND the nsflow visual agent inspector (port 4173).
title ONRAMP-NeuroSAN
cd /d "%~dp0"
set "AGENT_MANIFEST_FILE=%~dp0registries\manifest.hocon"
set "AGENT_TOOL_PATH=%~dp0src"
echo Neuro-SAN server starting on http://127.0.0.1:8080
echo nsflow visual inspector starting on http://localhost:4173 (may take ~30s to build)
".venv\Scripts\ns.exe" run --server-host 127.0.0.1 --server-http-port 8080 --nsflow-port 4173
echo.
echo Neuro-SAN / nsflow has stopped. Press any key to close this window.
pause >nul
