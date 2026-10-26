@echo off
title Coal Mine - Server
cd /d "%~dp0"

echo.
echo   Starting Coal Mine server...
echo   Browser will open in 3 seconds.
echo   Press Ctrl+C to stop the server.
echo.

REM Launch Chrome after 3s (in background, hidden window)
start "" powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; try { Start-Process chrome 'http://127.0.0.1:8000' -ErrorAction Stop } catch { Start-Process 'http://127.0.0.1:8000' }"

REM Start Django (this blocks — server runs here)
python manage.py runserver 0.0.0.0:8000

pause