#!/usr/bin/env python3
"""
Agent-OS OpenAI / Claude Function-Calling Connector — Complete (199 tools)
Provides tool definitions for OpenAI function-calling and Claude tool-use APIs.

Usage:
    from connectors.openai_connector import get_tools, call_tool

    # Get tools for OpenAI
    tools = get_tools("openai")

    # Get tools for Claude
    tools = get_tools("claude")

    # Execute a tool
    result = await call_tool("browser_navigate", {"url": "https://example.com"})
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

# Add parent dir to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from connectors._tool_registry import TOOLS as TOOL_REGISTRY, get_command_map

logger = logging.getLogger("agent-os-openai")

# Configuration
AGENT_OS_URL = os.environ.get("AGENT_OS_URL", "http://localhost:8001")
AGENT_TOKEN = os.environ.get("AGENT_OS_TOKEN", "openai-agent-default")

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


def get_tools(format: str = "openai") -> List[Dict[str, Any]]:
    """Get tool definitions in the specified format.

    Args:
        format: "openai" for OpenAI function-calling format,
                "claude" for Claude tool-use format.

    Returns:
        List of tool definitions.
    """
    if format == "claude":
        return _get_claude_tools()
    return _get_openai_tools()


def _get_openai_tools() -> List[Dict[str, Any]]:
    """Get tools in OpenAI function-calling format."""
    tools = []
    for t in TOOL_REGISTRY:
        props = {}
        required = []
        for p in t.params:
            prop = {"type": p.type, "description": p.description}
            if p.type == "array":
                prop["items"] = {"type": "object"}
            props[p.name] = prop
            if p.required:
                required.append(p.name)
        tools.append({
            "type": "function",
            "function": {
                "name": t.openai_name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                }
            }
        })
    return tools


def _get_claude_tools() -> List[Dict[str, Any]]:
    """Get tools in Claude tool-use format."""
    tools = []
    for t in TOOL_REGISTRY:
        props = {}
        required = []
        for p in t.params:
            prop = {"type": p.type, "description": p.description}
            if p.type == "array":
                prop["items"] = {"type": "object"}
            props[p.name] = prop
            if p.required:
                required.append(p.name)
        tools.append({
            "name": t.openai_name,
            "description": t.description,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            }
        })
    return tools


async def call_tool(name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute an Agent-OS tool.

    Args:
        name: Tool name (e.g., "browser_navigate").
        arguments: Tool arguments.

    Returns:
        Tool execution result.
    """
    if arguments is None:
        arguments = {}

    if name == "browser_status" or name == "status":
        return await _check_status()

    if name in command_map:
        cmd_name, param_keys = command_map[name]
        params = {k: arguments[k] for k in param_keys if k in arguments}
        return await _execute_command(cmd_name, params)

    return {"status": "error", "error": f"Unknown tool: {name}"}


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


# ─── Convenience: Sync Wrapper ───────────────────────────────

def call_tool_sync(name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
    """Synchronous wrapper for call_tool."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                lambda: asyncio.run(call_tool(name, arguments))
            ).result()
    else:
        return asyncio.run(call_tool(name, arguments))


# ─── Stats ───────────────────────────────────────────────────

def get_tool_count() -> int:
    """Get total number of available tools."""
    return len(TOOL_REGISTRY)


def get_categories() -> Dict[str, int]:
    """Get tool categories with counts."""
    cats = {}
    for t in TOOL_REGISTRY:
        cats[t.category] = cats.get(t.category, 0) + 1
    return cats


if __name__ == "__main__":
    print(f"Agent-OS OpenAI Connector — {len(TOOL_REGISTRY)} tools available")
    print(f"\nCategories:")
    for cat, count in sorted(get_categories().items()):
        print(f"  {cat}: {count} tools")
    print(f"\nFirst 10 tools:")
    for t in TOOL_REGISTRY[:10]:
        print(f"  - {t.openai_name}: {t.description[:60]}...")
