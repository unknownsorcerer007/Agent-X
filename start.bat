@echo off
setlocal
cd /d "%~dp0"

echo =========================================
echo            Starting Agent-X             
echo =========================================

echo [1/3] Fetching latest updates from GitHub...
git pull origin main

if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found. Please run install.ps1 first.
    exit /b 1
)

echo [2/3] Ensuring Chromium is installed (Patchright)...
venv\Scripts\python.exe -m patchright install chromium

echo [3/3] Starting server (with Visible Browser UI)...
venv\Scripts\python.exe main.py --headed
