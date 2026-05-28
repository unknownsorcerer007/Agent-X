<#
.SYNOPSIS
    Agent-X Installation Script
.DESCRIPTION
    Sets up the Python virtual environment, installs dependencies,
    and initializes patchright browsers.
#>

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       Agent-X Setup & Installer        " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Setup Installation Directory & Clone Repo
$installDir = "$env:USERPROFILE\Agent-X"
Write-Host "[1/5] Setting up Agent-X in $installDir..." -ForegroundColor Yellow

if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Git is not installed. Please install git from git-scm.com." -ForegroundColor Red
    exit 1
}

if (!(Test-Path -Path $installDir)) {
    git clone -q https://github.com/unknownsorcerer007/Agent-X.git $installDir
    Write-Host "Cloned Agent-X repository." -ForegroundColor Green
} else {
    Write-Host "Directory already exists, updating..." -ForegroundColor Yellow
    Set-Location -Path $installDir
    git pull -q
}

Set-Location -Path $installDir

# 2. Check for Python
Write-Host "[2/5] Checking Python installation..." -ForegroundColor Yellow
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from python.org and try again." -ForegroundColor Red
    exit 1
}

$pythonVersion = (python --version)
Write-Host "Found $pythonVersion" -ForegroundColor Green

# 3. Setup Virtual Environment
Write-Host "[3/5] Setting up Virtual Environment (venv)..." -ForegroundColor Yellow
if (!(Test-Path -Path "venv")) {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Virtual environment is ready." -ForegroundColor Green

# 4. Install Requirements
Write-Host "[4/5] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m pip install --upgrade pip

# Set environment variables to install pure-Python fallbacks if binary wheels are not available
$env:AIOHTTP_NO_EXTENSIONS = "1"
$env:YARL_NO_EXTENSIONS = "1"
$env:MULTIDICT_NO_EXTENSIONS = "1"
$env:FROZENLIST_NO_EXTENSIONS = "1"

.\venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install Python dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed successfully." -ForegroundColor Green

# Optional CAPTCHA solver ddddocr
Write-Host "Installing optional CAPTCHA solver ddddocr..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m pip install ddddocr
if ($LASTEXITCODE -ne 0) {
    Write-Host "ddddocr installation skipped or failed (common on Python 3.13+ or systems without C++ compilers). Core browser automation is fully functional." -ForegroundColor Yellow
} else {
    Write-Host "ddddocr installed successfully." -ForegroundColor Green
}


# 5. Install Patchright Browsers
Write-Host "[5/5] Installing Patchright / Playwright browsers..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m patchright install --with-deps chromium
if ($LASTEXITCODE -ne 0) {
    # Fallback to playwright if patchright CLI not directly available
    .\venv\Scripts\python.exe -m playwright install --with-deps chromium
}
Write-Host "Browsers installed successfully." -ForegroundColor Green

# 6. Configure Environment and API Keys
Write-Host "[6/6] Configuring Environment & API Keys..." -ForegroundColor Yellow
if (!(Test-Path -Path ".env")) {
    if (Test-Path -Path ".env.example") {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example." -ForegroundColor Green
    } else {
        New-Item -ItemType File -Path .env | Out-Null
        Write-Host "Created new .env file." -ForegroundColor Green
    }
}

$addKeys = Read-Host "Do you want to add API keys now? (y/N)"
if ($addKeys -match "^[yY]") {
    $openAiKey = Read-Host "Enter OpenAI API Key (leave blank to skip)"
    $anthropicKey = Read-Host "Enter Anthropic API Key (leave blank to skip)"
    
    if ($openAiKey) {
        Add-Content -Path .env -Value "OPENAI_API_KEY=$openAiKey"
        Write-Host "Added OpenAI API Key." -ForegroundColor Green
    }
    if ($anthropicKey) {
        Add-Content -Path .env -Value "ANTHROPIC_API_KEY=$anthropicKey"
        Write-Host "Added Anthropic API Key." -ForegroundColor Green
    }
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Installation Complete! You are ready." -ForegroundColor Green
Write-Host "To start the server, run: .\start.ps1" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Cyan
