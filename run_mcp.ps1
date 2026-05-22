<#
.SYNOPSIS
    Agent-OS MCP Connector Script
.DESCRIPTION
    Runs the MCP stdio wrapper for Agent-OS, allowing connection to Claude Desktop or similar.
#>

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       Agent-OS MCP Connector            " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (!(Test-Path -Path "venv\Scripts\python.exe")) {
    Write-Host "Error: Virtual environment not found. Please run .\install.ps1 first." -ForegroundColor Red
    exit 1
}

# The connector runs in STDIO mode
.\venv\Scripts\python.exe connectors\mcp_server.py
