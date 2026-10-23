@echo off
REM ============================================================
REM  ONRAMP - stop all services
REM  Stops whatever is listening on ports 8080 (Neuro-SAN),
REM  4173 (nsflow) and 8000 (ONRAMP app), plus launcher windows.
REM ============================================================

setlocal enabledelayedexpansion
echo.
echo  ONRAMP shutdown
echo  ===============

REM --- Kill processes listening on our ports (and their children) --------
for %%P in (8000 8080 4173) do (
    echo  Looking for a process on port %%P ...
    for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
        echo    Stopping PID %%I on port %%P
        taskkill /PID %%I /T /F >nul 2>&1
    )
)

REM --- Close the launcher windows by title (best-effort) -----------------
taskkill /FI "WINDOWTITLE eq ONRAMP-NeuroSAN*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq ONRAMP-App*" /T /F >nul 2>&1

REM --- Mop up any stray neuro-san server process -------------------------
taskkill /IM ns.exe /T /F >nul 2>&1

echo.
echo  Done. Verifying ports are free:
for %%P in (8000 8080 4173) do (
    netstat -ano | findstr /r /c:":%%P .*LISTENING" >nul 2>&1 && (
        echo    [WARN] Port %%P still in use.
    ) || (
        echo    [OK]   Port %%P is free.
    )
)
echo.
endlocal
