<#
.SYNOPSIS
    Agent-OS Installation Script
.DESCRIPTION
    Sets up the Python virtual environment, installs dependencies,
    and initializes patchright browsers.
#>

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       Agent-OS Setup & Installer        " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Check for Python
Write-Host "[1/4] Checking Python installation..." -ForegroundColor Yellow
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from python.org and try again." -ForegroundColor Red
    exit 1
}

$pythonVersion = (python --version)
Write-Host "Found $pythonVersion" -ForegroundColor Green

# 2. Setup Virtual Environment
Write-Host "[2/4] Setting up Virtual Environment (venv)..." -ForegroundColor Yellow
if (!(Test-Path -Path "venv")) {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Virtual environment is ready." -ForegroundColor Green

# 3. Install Requirements
Write-Host "[3/4] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install Python dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed successfully." -ForegroundColor Green

# 4. Install Patchright Browsers
Write-Host "[4/4] Installing Patchright / Playwright browsers..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m patchright install --with-deps chromium
if ($LASTEXITCODE -ne 0) {
    # Fallback to playwright if patchright CLI not directly available
    .\venv\Scripts\python.exe -m playwright install --with-deps chromium
}
Write-Host "Browsers installed successfully." -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Installation Complete! You are ready." -ForegroundColor Green
Write-Host "To start the server, run: .\start.ps1" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Cyan
