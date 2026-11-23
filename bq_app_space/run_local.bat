@echo off
title Space Portal (BQ) - Local Dev Server
echo ========================================================
echo   Iniciando Space Portal (BQ) em Modo Local...
echo ========================================================
cd /d "%~dp0src\app"
python app.py
pause
