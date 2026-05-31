@echo off
setlocal
cd /d "%~dp0"

echo Starting Agent-X Server in a new window...
start "Agent-X Server" cmd /k ".\venv\Scripts\python.exe main.py --headed"

echo Waiting 5 seconds for the server to boot...
timeout /t 5 /nobreak >nul

echo Starting Agent-X Interactive CLI in a new window...
start "Agent-X Smart CLI" cmd /k ".\venv\Scripts\python.exe cli.py"
