<#
.SYNOPSIS
    Agent-X MCP Connector Script
.DESCRIPTION
    Runs the MCP stdio wrapper for Agent-X, allowing connection to Claude Desktop or similar.
#>

if ($PSScriptRoot) {
    Set-Location $PSScriptRoot
}

[Console]::Error.WriteLine("=========================================")
[Console]::Error.WriteLine("       Agent-X MCP Connector            ")
[Console]::Error.WriteLine("=========================================")

if (!(Test-Path -Path "venv\Scripts\python.exe")) {
    [Console]::Error.WriteLine("Error: Virtual environment not found. Please run .\install.ps1 first.")
    exit 1
}

# The connector runs in STDIO mode
.\venv\Scripts\python.exe connectors\mcp_passthrough.py
