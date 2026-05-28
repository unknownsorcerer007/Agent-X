<#
.SYNOPSIS
    Agent-X Start Script
.DESCRIPTION
    Starts the Agent-X server using the virtual environment.
#>

if ($PSScriptRoot) {
    Set-Location $PSScriptRoot
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "           Starting Agent-X             " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (!(Test-Path -Path "venv\Scripts\python.exe")) {
    Write-Host "Error: Virtual environment not found. Please run .\install.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Fetching latest updates from GitHub..." -ForegroundColor Yellow
git pull origin main

Write-Host "Ensuring Chromium is installed (Patchright)..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m patchright install chromium

Write-Host "Starting server (with Visible Browser UI)..." -ForegroundColor Green
.\venv\Scripts\python.exe main.py --headed
