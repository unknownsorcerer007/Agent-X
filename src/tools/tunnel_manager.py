"""
Cloudflare Tunnel Manager — Secure Public URL for MCP Web Connect
==================================================================
Manages Cloudflare tunnels to expose the local Agent-X MCP SSE server
via a secure public URL, enabling Claude Web (Claude.ai) to connect
directly without any desktop setup.

FEATURES:
- Automatic Cloudflare tunnel creation
- Tunnel status monitoring and health checks
- Automatic reconnection on failure
- Public URL management
- Tunnel lifecycle management (start, stop, restart)

USAGE:
    tunnel = TunnelManager()
    public_url = await tunnel.start()
    # public_url is now something like: https://agent-x-abc123.trycloudflare.com
    # This URL can be pasted into Claude.ai MCP settings
    
    # Get connection info for the user
    info = tunnel.get_connection_info()
    # Returns the public URL and setup instructions
    
    await tunnel.stop()  # Clean shutdown

SECURITY NOTES:
- Cloudflare tunnels use TLS encryption end-to-end
- No inbound ports need to be opened on the firewall
- Tunnel authenticates to Cloudflare's edge using secure tokens
- The local server still validates the Agent-X token
"""
import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

logger = logging.getLogger("agent-x.tunnel")


@dataclass
class TunnelStatus:
    """Tunnel connection status."""
    running: bool
    public_url: Optional[str] = None
    local_port: int = 8002
    error: Optional[str] = None
    uptime_seconds: float = 0.0
    reconnect_count: int = 0


class TunnelManager:
    """Manages Cloudflare tunnel for exposing Agent-X MCP server publicly.
    
    This enables Claude Web (Claude.ai) and other cloud AI services to
    connect to Agent-X via a secure public URL without requiring any
    local network configuration.
    """

    CLOUDFLARED_BINARIES = [
        "cloudflared",
        "/usr/local/bin/cloudflared",
        "/usr/bin/cloudflared",
        os.path.expanduser("~/.local/bin/cloudflared"),
        os.path.expanduser("~/bin/cloudflared"),
    ]

    def __init__(self, local_port: int = 8002, max_retries: int = 3):
        """Initialize tunnel manager.
        
        Args:
            local_port: Local port where Agent-X MCP SSE server runs
            max_retries: Maximum reconnection attempts
        """
        self.local_port = local_port
        self.max_retries = max_retries
        
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._running = False
        self._start_time: float = 0.0
        self._reconnect_count = 0
        self._tunnel_task: Optional[asyncio.Task] = None
        self._cloudflared_path: Optional[str] = None

    def _find_cloudflared(self) -> Optional[str]:
        """Find the cloudflared binary."""
        if self._cloudflared_path:
            return self._cloudflared_path
        
        # Check common locations
        for path in self.CLOUDFLARED_BINARIES:
            if shutil.which(path):
                self._cloudflared_path = shutil.which(path)
                return self._cloudflared_path
        
        # Try to find in PATH
        self._cloudflared_path = shutil.which("cloudflared")
        return self._cloudflared_path

    def is_available(self) -> bool:
        """Check if cloudflared is available."""
        return self._find_cloudflared() is not None

    async def install_cloudflared(self) -> bool:
        """Attempt to install cloudflared automatically.
        
        Returns:
            True if installation succeeded or already available
        """
        if self.is_available():
            return True
        
        logger.info("Attempting to install cloudflared...")
        
        try:
            # Detect platform and install
            import platform
            system = platform.system().lower()
            machine = platform.machine().lower()
            
            if system == "linux":
                # Linux install
                arch = "amd64" if machine in ("x86_64", "amd64") else "arm64"
                install_cmd = f"""
                curl -L --output /tmp/cloudflared.deb \
                    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}.deb && \
                dpkg -x /tmp/cloudflared.deb /tmp/cloudflared && \
                cp /tmp/cloudflared/usr/bin/cloudflared ~/.local/bin/cloudflared 2>/dev/null || \
                cp /tmp/cloudflared/usr/bin/cloudflared /usr/local/bin/cloudflared 2>/dev/null ||
                sudo cp /tmp/cloudflared/usr/bin/cloudflared /usr/local/bin/cloudflared
                """
                proc = await asyncio.create_subprocess_shell(
                    install_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                
            elif system == "darwin":
                # macOS install via Homebrew
                proc = await asyncio.create_subprocess_shell(
                    "brew install cloudflare/cloudflare/cloudflared 2>/dev/null || brew install cloudflared",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            
            # Check again
            return self.is_available()
            
        except Exception as e:
            logger.error(f"Failed to install cloudflared: {e}")
            return False

    async def start(self) -> Optional[str]:
        """Start the Cloudflare tunnel.
        
        Returns:
            Public URL if successful, None otherwise
        """
        if self._running:
            return self._public_url
        
        # Check/install cloudflared
        if not self.is_available():
            installed = await self.install_cloudflared()
            if not installed:
                logger.error(
                    "cloudflared not found. Install it:\n"
                    "  Linux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb | sudo dpkg -i\n"
                    "  macOS: brew install cloudflare/cloudflare/cloudflared\n"
                    "  Or visit: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
                )
                return None
        
        self._cloudflared_path = self._find_cloudflared()
        self._running = True
        self._start_time = time.time()
        
        # Start tunnel in background
        self._tunnel_task = asyncio.create_task(self._run_tunnel())
        
        # Wait for URL (up to 30 seconds)
        for _ in range(60):
            if self._public_url:
                logger.info(f"Tunnel ready: {self._public_url}")
                return self._public_url
            if not self._running:
                break
            await asyncio.sleep(0.5)
        
        if not self._public_url:
            logger.error("Tunnel failed to provide public URL within timeout")
            await self.stop()
            return None
        
        return self._public_url

    async def _run_tunnel(self):
        """Run the tunnel process with auto-reconnect."""
        while self._running and self._reconnect_count < self.max_retries:
            try:
                await self._start_tunnel_process()
                
                # Monitor process
                while self._running and self._process:
                    retcode = self._process.poll()
                    if retcode is not None:
                        logger.warning(f"Tunnel process exited with code {retcode}")
                        break
                    await asyncio.sleep(1)
                
                if not self._running:
                    break
                
                # Reconnect
                self._reconnect_count += 1
                if self._reconnect_count < self.max_retries:
                    logger.info(f"Reconnecting... (attempt {self._reconnect_count}/{self.max_retries})")
                    await asyncio.sleep(2 ** self._reconnect_count)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Tunnel error: {e}")
                await asyncio.sleep(5)
        
        self._running = False
        self._public_url = None

    async def _start_tunnel_process(self):
        """Start the cloudflared tunnel process."""
        cmd = [
            self._cloudflared_path,
            "tunnel",
            "--url", f"http://localhost:{self.local_port}",
            "--metrics", "localhost:45678",  # Metrics port to avoid conflicts
        ]
        
        logger.info(f"Starting tunnel: {' '.join(cmd)}")
        
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Read output to extract URL
        asyncio.create_task(self._read_tunnel_output(self._process.stdout, False))
        asyncio.create_task(self._read_tunnel_output(self._process.stderr, True))

    async def _read_tunnel_output(self, stream, is_stderr: bool):
        """Read tunnel output to extract the public URL."""
        try:
            while self._running and self._process:
                line = await stream.readline()
                if not line:
                    break
                
                text = line.decode("utf-8", errors="replace").strip()
                
                # Extract URL from cloudflared output
                if "trycloudflare.com" in text or "https://" in text:
                    # Parse URL from output
                    import re
                    urls = re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', text)
                    if urls:
                        self._public_url = urls[0]
                        logger.info(f"Tunnel URL detected: {self._public_url}")
                
                if is_stderr:
                    logger.debug(f"[tunnel] {text}")
                else:
                    logger.debug(f"[tunnel] {text}")
                    
        except Exception as e:
            logger.debug(f"Tunnel output reader exited: {e}")

    async def stop(self):
        """Stop the tunnel."""
        self._running = False
        
        if self._tunnel_task:
            self._tunnel_task.cancel()
            try:
                await self._tunnel_task
            except asyncio.CancelledError:
                pass
            self._tunnel_task = None
        
        if self._process:
            try:
                self._process.terminate()
                await asyncio.sleep(1)
                if self._process.poll() is None:
                    self._process.kill()
            except Exception as e:
                logger.debug(f"Error stopping tunnel: {e}")
            self._process = None
        
        self._public_url = None
        logger.info("Tunnel stopped")

    def get_status(self) -> TunnelStatus:
        """Get current tunnel status."""
        uptime = time.time() - self._start_time if self._start_time else 0
        return TunnelStatus(
            running=self._running and self._public_url is not None,
            public_url=self._public_url,
            local_port=self.local_port,
            uptime_seconds=uptime,
            reconnect_count=self._reconnect_count,
        )

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information for setting up Claude Web.
        
        Returns a dict with the public URL and instructions for
        connecting Claude Web to Agent-X.
        """
        status = self.get_status()
        
        if not status.public_url:
            return {
                "ready": False,
                "error": "Tunnel not running. Start with: await tunnel_manager.start()",
                "setup_steps": [
                    "1. Start Agent-X with MCP SSE server: python main.py",
                    "2. Start tunnel: await tunnel_manager.start()",
                    "3. Use the provided public URL in Claude.ai settings",
                ],
            }
        
        # Build MCP server URL
        mcp_url = f"{status.public_url}/sse"
        
        return {
            "ready": True,
            "public_url": status.public_url,
            "mcp_sse_url": mcp_url,
            "local_port": status.local_port,
            "uptime_seconds": round(status.uptime_seconds, 1),
            "reconnects": status.reconnect_count,
            "claude_web_setup": {
                "method": "Custom MCP Server",
                "url": mcp_url,
                "auth_type": "Bearer",
                "instructions": [
                    f"1. Open Claude.ai → Settings → MCP Servers",
                    f"2. Click 'Add Custom MCP Server'",
                    f"3. Paste this URL: {mcp_url}",
                    f"4. Authentication: Leave as default (Bearer)",
                    f"5. Save and Claude will connect to your Agent-X",
                ],
            },
            "cursor_setup": {
                "method": "MCP Server",
                "instructions": [
                    "1. Open Cursor → Settings → MCP",
                    f"2. Add server URL: {mcp_url}",
                    "3. Save configuration",
                ],
            },
            "other_clients": {
                "generic_sse": mcp_url,
                "description": "Any MCP client supporting SSE transport can connect using the above URL",
            },
        }

    def get_claude_desktop_config(self) -> Dict[str, Any]:
        """Get the configuration block for Claude Desktop."""
        status = self.get_status()
        if not status.public_url:
            return {"error": "Tunnel not running"}
        
        return {
            "mcpServers": {
                "agent-x-web": {
                    "url": f"{status.public_url}/sse",
                    "env": {
                        "AGENT_X_TOKEN": "${AGENT_X_TOKEN}"
                    }
                }
            }
        }
