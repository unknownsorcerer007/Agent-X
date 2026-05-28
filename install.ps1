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

$addKeys = Read-Host "Do you want to configure an AI Provider API key now? (y/N)"
if ($addKeys -match "^[yY]") {
    Write-Host "Available Providers:" -ForegroundColor Cyan
    Write-Host "  [1] OpenAI"
    Write-Host "  [2] Anthropic"
    Write-Host "  [3] Google"
    Write-Host "  [4] Groq"
    Write-Host "  [5] Skip"
    $choice = Read-Host "Select provider (1-5)"
    
    $keyVar = ""
    $prefix = ""
    
    switch ($choice) {
        "1" { $keyVar = "OPENAI_API_KEY"; $prefix = "sk-" }
        "2" { $keyVar = "ANTHROPIC_API_KEY"; $prefix = "sk-ant-" }
        "3" { $keyVar = "GOOGLE_API_KEY"; $prefix = "" }
        "4" { $keyVar = "GROQ_API_KEY"; $prefix = "gsk_" }
    }
    
    if ($keyVar -ne "") {
        while ($true) {
            $key = Read-Host "Enter your API key for $keyVar (leave blank to skip)"
            if ([string]::IsNullOrWhiteSpace($key)) {
                Write-Host "Skipped." -ForegroundColor Yellow
                break
            }
            if ($prefix -ne "" -and -not $key.StartsWith($prefix)) {
                Write-Host "Invalid format! It should start with '$prefix'. Please try again." -ForegroundColor Red
            } else {
                Add-Content -Path .env -Value "$keyVar=$key"
                Write-Host "Added $keyVar successfully!" -ForegroundColor Green
                break
            }
        }
    }
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green

$startServer = Read-Host "Do you want to start the Agent-X server now? (y/N)"
if ($startServer -match "^[yY]") {
    Write-Host "Starting server in the background..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File .\start.ps1" -WindowStyle Hidden
    Write-Host "Waiting 5 seconds for server to boot..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Write-Host "Launching Interactive CLI..." -ForegroundColor Green
    if (Test-Path -Path "cli.py") {
        .\venv\Scripts\python.exe cli.py
    } else {
        Write-Host "cli.py not found. You can run it manually later." -ForegroundColor Red
    }
} else {
    Write-Host "To start the server manually later, run: .\start.ps1" -ForegroundColor Yellow
}
Write-Host "=========================================" -ForegroundColor Cyan
