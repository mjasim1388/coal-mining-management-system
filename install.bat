@echo off
title Coal Mine System - Master Installer
color 0A

:: Check for Admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [ERROR] Please right-click this file and select "Run as Administrator".
    pause
    exit /b
)

echo ===================================================
echo   COAL MINE SYSTEM - MASTER INSTALLER
echo ===================================================
echo.

:: 1. Read the Database Password
set /p DB_PASS=<db_password.txt
if "%DB_PASS%"=="" (
    echo [ERROR] db_password.txt is missing or empty. Please add your database password.
    pause
    exit /b
)

:: 2. Install Prerequisites using WinGet (Python & PostgreSQL)
echo [1/6] Downloading and installing Python & PostgreSQL (this may take 5-10 mins)...
winget install -e --id Python.Python.3.14 --silent --accept-package-agreements --accept-source-agreements
winget install -e --id PostgreSQL.PostgreSQL.18 --silent --accept-package-agreements --accept-source-agreements
echo.
echo [NOTE] If PostgreSQL was just installed, it might have a different password than your old PC.
echo We will attempt to set the database password to match your .env file.

:: Refresh environment variables so Python is recognized immediately
call :RefreshEnv

:: 3. Install Python Packages
echo.
echo [2/6] Installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

:: 4. Restore the Database
echo.
echo [3/6] Restoring the Database from latest backup...
:: Set the password for the pg_restore command
set PGPASSWORD=%DB_PASS%

:: Find the latest dump file in the backups folder
for /f "delims=" %%i in ('dir /b /o-d backups\coalmining_backup.dump 2^>nul') do set LATEST_DUMP=backups\%%i
if "%LATEST_DUMP%"=="" (
    echo [WARNING] No backup file found. Creating an empty database...
    createdb -U postgres coalmining_db
) else (
    dropdb -U postgres --if-exists coalmining_db
    createdb -U postgres coalmining_db
    pg_restore -U postgres -d coalmining_db -Fc "%LATEST_DUMP%"
    echo Database restored successfully!
)

:: 5. Prepare Static Files
echo.
echo [4/6] Collecting static files (CSS/JS)...
python manage.py collectstatic --no-input

:: 6. Open Windows Firewall
echo.
echo [5/6] Opening Firewall for port 8000...
netsh advfirewall firewall add rule name="Django Waitress 8000" dir=in action=allow protocol=TCP localport=8000 profile=private

:: 7. Install and Start the Windows Service (Servy)
echo.
echo [6/6] Setting up the Windows Service...
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i

:: Assuming the Servy folder is in the project directory
& "Servy\servy-cli.exe" stop --name="CoalMineServer" >nul 2>&1
& "Servy\servy-cli.exe" uninstall --name="CoalMineServer" >nul 2>&1
& "Servy\servy-cli.exe" install --name="CoalMineServer" --display-name="Coal Mine System" --description="Django App" --path="%PYTHON_PATH%" --arguments="-m waitress --listen=0.0.0.0:8000 coalmining.wsgi:application" --startupDir="%CD%" --startupType="Automatic"
& "Servy\servy-cli.exe" start --name="CoalMineServer"

echo.
echo ===================================================
echo   INSTALLATION COMPLETE! 
echo   The software is now running in the background.
echo   Access it at http://localhost:8000
echo ===================================================
pause
exit /b

:: --- Helper function to refresh PATH ---
:RefreshEnv
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path') do set "USR_PATH=%%b"
set "PATH=%SYS_PATH%;%USR_PATH%"
exit /b