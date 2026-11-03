@echo off
echo ===================================================
echo   COAL MINE SYSTEM - AUTOMATED SETUP
echo ===================================================
echo.

echo [1/4] Installing required Python packages...
pip install -r requirements.txt
if %errorlevel% neq 0 goto error

echo.
echo [2/4] Setting up the Database...
python manage.py migrate
if %errorlevel% neq 0 goto error

echo.
echo [3/4] Gathering static files (CSS/JS)...
python manage.py collectstatic --no-input
if %errorlevel% neq 0 goto error

echo.
echo [4/4] Creating the Windows Backup Task...
:: This will create the auto-backup task we built earlier automatically
schtasks /create /tn "CoalMine Auto Backup" /tr "cmd.exe /c cd /d E:\CoalMiningProject && python manage.py auto_backup" /sc minute /mo 10 /f

echo.
echo ===================================================
echo   SUCCESS! The system is ready.
echo   Double-click start_server.bat to run the app.
echo ===================================================
pause
exit

:error
echo.
echo ===================================================
echo   ERROR! Setup failed. Please check the error above.
echo ===================================================
pause