@echo off
REM Helper launched by startup.bat in its own window. Runs the ONRAMP app server.
title ONRAMP-App
cd /d "%~dp0"
echo ONRAMP app starting on http://127.0.0.1:8000 (this window stays open)...
".venv\Scripts\python.exe" -m uvicorn onramp_neuro_san.server.app:app --host 127.0.0.1 --port 8000
echo.
echo ONRAMP app has stopped. Press any key to close this window.
pause >nul
