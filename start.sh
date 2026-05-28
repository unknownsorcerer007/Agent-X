#!/bin/bash
cd "$(dirname "$0")"

echo "========================================="
echo "           Starting Agent-X             "
echo "========================================="

echo "[1/3] Fetching latest updates from GitHub..."
git pull origin main

if [ ! -f "venv/bin/python" ]; then
    echo "Error: Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

echo "[2/3] Ensuring Chromium is installed (Patchright)..."
venv/bin/python -m patchright install chromium

echo "[3/3] Starting server (with Visible Browser UI)..."
venv/bin/python main.py --headed
