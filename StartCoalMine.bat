@echo off
title Coal Mining System Server
cd /d E:\CoalMiningProject
echo ============================================
echo   COAL MINE MANAGEMENT SYSTEM
echo ============================================
echo.
echo Starting server...
echo.
echo Open your browser at: http://127.0.0.1:8000/
echo.
echo To STOP the server, close this window.
echo ============================================
echo.
python manage.py runserver
pause