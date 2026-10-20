@echo off
REM Helper launched by startup.bat in its own window. Runs the Neuro-SAN server.
title ONRAMP-NeuroSAN
cd /d "%~dp0"
set "AGENT_MANIFEST_FILE=%~dp0registries\manifest.hocon"
set "AGENT_TOOL_PATH=%~dp0src"
echo Neuro-SAN server starting on http://127.0.0.1:8080 (this window stays open)...
".venv\Scripts\ns.exe" run --server-only --server-host 127.0.0.1 --server-http-port 8080
echo.
echo Neuro-SAN server has stopped. Press any key to close this window.
pause >nul
