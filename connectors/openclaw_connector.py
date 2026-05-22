#!/usr/bin/env python3
"""
Agent-OS OpenClaw Integration — Complete (199 tools)
Adds Agent-OS browser tools to OpenClaw sessions.

Usage:
    from connectors.openclaw_connector import get_manifest, execute_tool
    manifest = get_manifest()
    result = await execute_tool("browser_navigate", {"url": "https://example.com"})
"""
import os
import json
import sys
import httpx
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from connectors._tool_registry import TOOLS, get_command_map

AGENT_OS_URL = os.environ.get("AGENT_OS_URL", "http://localhost:8001")
AGENT_TOKEN = os.environ.get("AGENT_OS_TOKEN", "openclaw-agent")

command_map = get_command_map()

# ─── Persistent HTTP Client ──────────────────────────────────

_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    """Get or create a persistent httpx.AsyncClient with connection pooling."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


def get_manifest() -> Dict[str, Any]:
    """Get the tool manifest for OpenClaw registration."""
    tools = []
    for t in TOOLS:
        params = {}
        required = []
        for p in t.params:
            params[p.name] = {
                "type": p.type,
                "required": p.required,
                "description": p.description,
            }
            if p.required:
                required.append(p.name)
        tools.append({
            "name": t.mcp_name,
            "description": t.description,
            "parameters": params,
        })

    return {
        "name": "agent-os-browser",
        "version": "3.2.0",
        "description": "AI Agent Browser — 199 tools for anti-detection browser automation",
        "tools": tools,
    }


async def execute_tool(tool_name: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute an Agent-OS tool.

    Args:
        tool_name: MCP-style tool name (e.g., "browser_navigate").
        params: Tool parameters.

    Returns:
        Tool execution result.
    """
    if params is None:
        params = {}

    if tool_name == "browser_status":
        return await _check_status()

    if tool_name in command_map:
        cmd_name, param_keys = command_map[tool_name]
        cmd_params = {k: params[k] for k in param_keys if k in params}
        return await _execute_command(cmd_name, cmd_params)

    return {"status": "error", "error": f"Unknown tool: {tool_name}"}


async def _execute_command(command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Send a command to Agent-OS server."""
    payload = {"token": AGENT_TOKEN, "command": command}
    if params:
        payload.update(params)

    client = await _get_client()
    try:
        response = await client.post(
            f"{AGENT_OS_URL}/command",
            json=payload,
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_status() -> Dict[str, Any]:
    """Check Agent-OS server status."""
    client = await _get_client()
    try:
        response = await client.get(f"{AGENT_OS_URL}/health")
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_tool_count() -> int:
    """Get total number of available tools."""
    return len(TOOLS)


if __name__ == "__main__":
    manifest = get_manifest()
    print(f"Agent-OS OpenClaw Connector")
    print(f"Tools: {len(manifest['tools'])}")
    print(f"Version: {manifest['version']}")
