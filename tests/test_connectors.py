#!/usr/bin/env python3
"""
Agent-OS Connector Tests — Updated for 199 tools
Tests MCP, OpenAI, Claude, OpenClaw, and CLI connectors.
All connectors must expose the same tools from the registry.

Run:
    python -m pytest tests/test_connectors.py -v
"""
import json
import sys
import os
import subprocess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors._tool_registry import TOOLS, get_all_server_commands, get_command_map

# Check if MCP package is available
try:
    import mcp
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# ─── Registry Tests ──────────────────────────────────────────

class TestRegistry:
    """Test the tool registry."""

    def test_registry_has_tools(self):
        """Registry should have tools defined."""
        assert len(TOOLS) >= 198, f"Expected >=198 tools, got {len(TOOLS)}"

    def test_registry_unique_commands(self):
        """All server commands should be unique."""
        cmds = [t.server_cmd for t in TOOLS]
        assert len(cmds) == len(set(cmds)), "Duplicate server commands found"

    def test_registry_unique_mcp_names(self):
        """All MCP names should be unique."""
        names = [t.mcp_name for t in TOOLS]
        assert len(names) == len(set(names)), "Duplicate MCP names found"

    def test_registry_unique_openai_names(self):
        """All OpenAI names should be unique."""
        names = [t.openai_name for t in TOOLS]
        assert len(names) == len(set(names)), "Duplicate OpenAI names found"

    def test_all_server_commands_covered(self):
        """All server commands should be in the registry."""
        import re
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src/agents/server.py')) as f:
            server_cmds = set(re.findall(r'"([\w-]+)":\s*self\._cmd_', f.read()))
        reg_cmds = set(get_all_server_commands())
        missing = server_cmds - reg_cmds
        assert not missing, f"Server commands missing from registry: {missing}"


# ─── MCP Connector ───────────────────────────────────────────

class TestMCPConnector:
    """Test MCP connector."""

    @pytest.mark.skipif(not HAS_MCP, reason="mcp package not installed")
    def test_mcp_imports(self):
        """MCP connector should import without errors."""
        from connectors.mcp_server import TOOLS_LIST, command_map
        assert len(TOOLS_LIST) > 0

    @pytest.mark.skipif(not HAS_MCP, reason="mcp package not installed")
    def test_mcp_tool_count(self):
        """MCP should have all registry tools."""
        from connectors.mcp_server import TOOLS_LIST
        assert len(TOOLS_LIST) == len(TOOLS), f"MCP has {len(TOOLS_LIST)} tools, registry has {len(TOOLS)}"

    @pytest.mark.skipif(not HAS_MCP, reason="mcp package not installed")
    def test_mcp_command_map(self):
        """MCP command map should cover all tools."""
        from connectors.mcp_server import command_map
        assert len(command_map) == len(TOOLS)

    def test_mcp_registry_tools_match(self):
        """MCP should use the same registry as everyone else."""
        # Test without importing mcp_server (which needs mcp package)
        from connectors._tool_registry import get_mcp_tools
        mcp_tools = get_mcp_tools()
        assert len(mcp_tools) == len(TOOLS)


# ─── OpenAI Connector ────────────────────────────────────────

class TestOpenAIConnector:
    """Test OpenAI connector."""

    def test_openai_imports(self):
        """OpenAI connector should import without errors."""
        from connectors.openai_connector import get_tools
        tools = get_tools("openai")
        assert len(tools) > 0

    def test_openai_tool_count(self):
        """OpenAI should have all registry tools."""
        from connectors.openai_connector import get_tools
        tools = get_tools("openai")
        assert len(tools) == len(TOOLS), f"OpenAI has {len(tools)} tools, registry has {len(TOOLS)}"

    def test_openai_tool_format(self):
        """OpenAI tools should have correct format."""
        from connectors.openai_connector import get_tools
        tools = get_tools("openai")
        for tool in tools[:5]:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_claude_tool_format(self):
        """Claude tools should have correct format."""
        from connectors.openai_connector import get_tools
        tools = get_tools("claude")
        for tool in tools[:5]:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool


# ─── OpenClaw Connector ──────────────────────────────────────

class TestOpenClawConnector:
    """Test OpenClaw connector."""

    def test_openclaw_imports(self):
        """OpenClaw connector should import without errors."""
        from connectors.openclaw_connector import get_manifest
        manifest = get_manifest()
        assert len(manifest["tools"]) > 0

    def test_openclaw_tool_count(self):
        """OpenClaw should have all registry tools."""
        from connectors.openclaw_connector import get_manifest
        manifest = get_manifest()
        assert len(manifest["tools"]) == len(TOOLS), f"OpenClaw has {len(manifest['tools'])} tools, registry has {len(TOOLS)}"

    def test_openclaw_manifest_format(self):
        """OpenClaw manifest should have correct format."""
        from connectors.openclaw_connector import get_manifest
        manifest = get_manifest()
        assert "name" in manifest
        assert "version" in manifest
        assert "tools" in manifest


# ─── Cross-Connector Consistency ─────────────────────────────

class TestCrossConnectorConsistency:
    """Test that all connectors expose the same tools."""

    def test_all_connectors_same_tool_count(self):
        """All connectors should have the same number of tools."""
        from connectors.openai_connector import get_tools
        from connectors.openclaw_connector import get_manifest

        openai_tools = get_tools("openai")
        oc_manifest = get_manifest()

        counts = {
            "registry": len(TOOLS),
            "openai": len(openai_tools),
            "openclaw": len(oc_manifest["tools"]),
        }

        assert len(set(counts.values())) == 1, f"Tool counts differ: {counts}"

    def test_all_connectors_same_tool_names(self):
        """All connectors should expose the same tool names."""
        from connectors.openai_connector import get_tools
        from connectors.openclaw_connector import get_manifest

        openai_names = set(t["function"]["name"] for t in get_tools("openai"))
        oc_names = set(t["name"] for t in get_manifest()["tools"])

        assert openai_names == oc_names, f"OpenAI/OpenClaw name mismatch: {openai_names - oc_names} vs {oc_names - openai_names}"
