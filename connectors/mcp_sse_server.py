#!/usr/bin/env python3
"""
Agent-X MCP SSE Server
=======================
Exposes the Model Context Protocol (MCP) over HTTP/SSE.
Allows Claude Web version (Claude.ai) to connect directly using a public URL.

Usage:
    python connectors/mcp_sse_server.py
"""
import os
import sys
import logging
import json
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import Tool, TextContent
import mcp.types as types
from uuid import uuid4

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from connectors._tool_registry import get_command_map, get_mcp_tools

# Resolve token and url
def resolve_agent_token() -> str:
    token = os.environ.get("AGENT_X_TOKEN") or os.environ.get("AGENT_TOKEN")
    if token:
        return token
    # Check ~/.agent-x/config.yaml
    yaml_path = os.path.expanduser("~/.agent-x/config.yaml")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                t = cfg.get("server", {}).get("agent_token")
                if t:
                    return t
        except Exception:
            pass
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_dir, ".env")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k in ("AGENT_TOKEN", "AGENT_X_TOKEN") and v:
                            return v
        except Exception:
            pass
    return "claude-web-token"

AGENT_X_URL = os.environ.get("AGENT_X_URL", "http://localhost:8001")
AGENT_X_TOKEN = resolve_agent_token()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("agent-x-mcp-sse")

# Create MCP server
server = Server("agent-x")

# Build Tool Definitions
TOOLS_LIST: List[Tool] = []
_mcp_tools = get_mcp_tools()
for tool_def in _mcp_tools:
    TOOLS_LIST.append(Tool(
        name=tool_def["name"],
        description=tool_def["description"],
        inputSchema=tool_def["inputSchema"],
    ))

command_map = get_command_map()
logger.info(f"Loaded {len(TOOLS_LIST)} MCP tools")

_client: Optional[httpx.AsyncClient] = None

async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        )
    return _client

async def agent_os_command(command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    payload = {"token": AGENT_X_TOKEN, "command": command}
    if params:
        payload.update(params)
    client = await _get_client()
    try:
        response = await client.post(f"{AGENT_X_URL}/command", json=payload)
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def agent_os_status() -> Dict[str, Any]:
    client = await _get_client()
    try:
        response = await client.get(f"{AGENT_X_URL}/health")
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

@server.list_tools()
async def list_tools() -> List[Tool]:
    return TOOLS_LIST

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    logger.info(f"Tool call: {name}")
    if name == "browser_status":
        result = await agent_os_status()
    elif name in command_map:
        cmd_name, param_keys = command_map[name]
        params = {k: arguments[k] for k in param_keys if k in arguments}
        result = await agent_os_command(cmd_name, params)
    else:
        result = {"status": "error", "error": f"Unknown tool: {name}"}

    output = json.dumps(result, indent=2)
    if len(output) > 10000:
        if "screenshot" in result:
            output = f"[Screenshot captured: {len(result.get('screenshot', ''))} bytes base64]"
        elif "html" in result:
            preview = result.get('text', '')[:2000]
            output = f"[HTML content: {len(result.get('html', ''))} chars]\n\nText preview:\n{preview}"
        else:
            output = output[:10000] + "\n... [truncated]"

    return [TextContent(type="text", text=output)]

# ─── FastAPI app & Streamable HTTP Session Manager ───────────
from contextlib import asynccontextmanager
from starlette.types import Receive, Scope, Send
import anyio
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=False,
    stateless=False
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with session_manager.run():
        yield

app = FastAPI(title="Agent-X MCP SSE Server", lifespan=lifespan)

# Add CORS middleware to allow the browser to connect
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mock OAuth 2.1 Provider Endpoints ────────────────────────

@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/sse")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource(request: Request):
    headers = request.headers
    host = headers.get("x-forwarded-host") or headers.get("host") or "localhost:8002"
    proto = headers.get("x-forwarded-proto") or request.url.scheme or "http"
    base_url = f"{proto}://{host}"
    
    path = request.url.path
    resource_path = "/sse" if "sse" in path else "/mcp"
    
    return JSONResponse({
        "resource": f"{base_url}{resource_path}",
        "authorization_servers": [base_url],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"]
    })

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server(request: Request):
    headers = request.headers
    host = headers.get("x-forwarded-host") or headers.get("host") or "localhost:8002"
    proto = headers.get("x-forwarded-proto") or request.url.scheme or "http"
    base_url = f"{proto}://{host}"
    
    return JSONResponse({
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "scopes_supported": ["mcp"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"]
    })

@app.post("/oauth/register")
@app.post("/register")
async def oauth_register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    redirect_uris = body.get("redirect_uris", ["https://claude.ai/oauth/callback"])
    
    return JSONResponse({
        "client_id": "mock-client-id",
        "client_secret": "mock-client-secret",
        "client_id_issued_at": 1600000000,
        "client_secret_expires_at": 0,
        "redirect_uris": redirect_uris
    })

@app.get("/oauth/authorize")
@app.get("/authorize")
async def oauth_authorize(
    request: Request,
    redirect_uri: str = "https://claude.ai/oauth/callback",
    state: str = "mock-state",
    code_challenge: str = None,
    code_challenge_method: str = None
):
    redirect_url = f"{redirect_uri}?code=mock-authorization-code&state={state}"
    logger.info(f"OAuth Authorize rendering consent page for: {redirect_url}")
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorize Agent-X Connection</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0c10;
            --card-bg: rgba(22, 24, 30, 0.7);
            --border-color: rgba(138, 43, 226, 0.2);
            --glow-color: rgba(138, 43, 226, 0.6);
            --primary-color: #8a2be2;
            --primary-hover: #9d4edd;
            --text-color: #f8f9fa;
            --muted-color: #a0aec0;
            --success-color: #10b981;
            --error-color: #ef4444;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }}

        /* Ambient Glowing Background Elements */
        body::before, body::after {{
            content: '';
            position: absolute;
            width: 300px;
            height: 300px;
            border-radius: 50%;
            filter: blur(120px);
            z-index: -1;
            opacity: 0.4;
        }}

        body::before {{
            background: var(--glow-color);
            top: 15%;
            left: 20%;
            animation: float-slow 12s infinite alternate;
        }}

        body::after {{
            background: #4facfe;
            bottom: 15%;
            right: 20%;
            animation: float-slow-reverse 15s infinite alternate;
        }}

        @keyframes float-slow {{
            0% {{ transform: translate(0, 0) scale(1); }}
            100% {{ transform: translate(50px, 30px) scale(1.1); }}
        }}

        @keyframes float-slow-reverse {{
            0% {{ transform: translate(0, 0) scale(1); }}
            100% {{ transform: translate(-40px, -50px) scale(0.9); }}
        }}

        /* Glassmorphic Card */
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 480px;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4), 
                        0 0 40px rgba(138, 43, 226, 0.1);
            text-align: center;
            animation: slide-up 0.6s cubic-bezier(0.16, 1, 0.3, 1);
            margin: 20px;
        }}

        @keyframes slide-up {{
            0% {{ transform: translateY(30px); opacity: 0; }}
            100% {{ transform: translateY(0); opacity: 1; }}
        }}

        .logo-container {{
            display: flex;
            justify-content: center;
            margin-bottom: 24px;
        }}

        .logo {{
            width: 72px;
            height: 72px;
            border-radius: 18px;
            background: linear-gradient(135deg, var(--primary-color), #4facfe);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 24px rgba(138, 43, 226, 0.4);
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 800;
            color: white;
            letter-spacing: -1px;
            animation: pulse-glow 2.5s infinite alternate;
        }}

        @keyframes pulse-glow {{
            0% {{ box-shadow: 0 8px 24px rgba(138, 43, 226, 0.4); }}
            100% {{ box-shadow: 0 8px 32px rgba(138, 43, 226, 0.7), 0 0 15px rgba(79, 172, 254, 0.4); }}
        }}

        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 26px;
            font-weight: 700;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #ffffff, #dcdcdc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .subtitle {{
            color: var(--muted-color);
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 30px;
        }}

        .info-box {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 32px;
            text-align: left;
        }}

        .info-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 13px;
        }}

        .info-row:last-child {{
            margin-bottom: 0;
        }}

        .info-label {{
            color: var(--muted-color);
            font-weight: 500;
        }}

        .info-value {{
            color: var(--text-color);
            font-weight: 600;
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .info-value.scopes {{
            background: rgba(138, 43, 226, 0.15);
            color: #d8b4fe;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 12px;
            border: 1px solid rgba(138, 43, 226, 0.3);
        }}

        .button-group {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .btn {{
            width: 100%;
            padding: 14px 28px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .btn-primary {{
            background: linear-gradient(135deg, var(--primary-color), #6366f1);
            color: white;
            border: none;
            box-shadow: 0 4px 15px rgba(138, 43, 226, 0.3);
        }}

        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(138, 43, 226, 0.5);
            background: linear-gradient(135deg, var(--primary-hover), #4f46e5);
        }}

        .btn-primary:active {{
            transform: translateY(0);
        }}

        .btn-secondary {{
            background: transparent;
            color: var(--muted-color);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-color);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .footer {{
            margin-top: 24px;
            font-size: 11px;
            color: rgba(255, 255, 255, 0.2);
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="logo-container">
            <div class="logo">OS</div>
        </div>
        <h1>Authorize Access</h1>
        <p class="subtitle">An external AI application is requesting secure connection to control your local browser automation instance.</p>
        
        <div class="info-box">
            <div class="info-row">
                <span class="info-label">Application</span>
                <span class="info-value" title="Claude.ai">Claude Web Interface</span>
            </div>
            <div class="info-row">
                <span class="info-label">Redirect URI</span>
                <span class="info-value" title="{redirect_uri}">{redirect_uri}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Permissions</span>
                <span class="info-value scopes">mcp (Browser Automation)</span>
            </div>
        </div>

        <div class="button-group">
            <button class="btn btn-primary" onclick="authorize()">Authorize Connection</button>
            <button class="btn btn-secondary" onclick="cancel()">Cancel</button>
        </div>

        <div class="footer">
            Agent-X v3.2.0 • Secure End-to-End Tunneling
        </div>
    </div>

    <script>
        function authorize() {{
            window.location.href = "{redirect_url}";
        }}

        function cancel() {{
            document.body.innerHTML = `
                <div class="card" style="max-width: 400px;">
                    <div class="logo-container">
                        <div class="logo" style="background: linear-gradient(135deg, var(--error-color), #f43f5e);">✕</div>
                    </div>
                    <h1>Connection Denied</h1>
                    <p class="subtitle" style="margin-bottom: 0;">Authorization was cancelled by the user. You can close this window now.</p>
                </div>
            `;
        }}
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.post("/oauth/token")
@app.post("/token")
async def oauth_token(request: Request):
    return JSONResponse({
        "access_token": "mock-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "mcp"
    })

# ─── ASGI middleware to intercept transport requests ─────────

class _McpTransportMiddleware:
    """ASGI middleware that intercepts GET/POST to /sse and /mcp and delegates to session_manager."""
    def __init__(self, app_inner, manager: StreamableHTTPSessionManager):
        self._app = app_inner
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            
            if path in ("/sse", "/sse/", "/mcp", "/mcp/"):
                # 1. Perform Authentication check
                headers_list = scope.get("headers", [])
                auth_val = b""
                host_val = b"localhost:8002"
                proto_val = b"http"
                
                for hdr_name, hdr_value in headers_list:
                    if hdr_name == b"authorization":
                        auth_val = hdr_value
                    elif hdr_name == b"x-forwarded-host":
                        host_val = hdr_value
                    elif hdr_name == b"host" and not host_val:
                        host_val = hdr_value
                    elif hdr_name == b"x-forwarded-proto":
                        proto_val = hdr_value

                # If Authorization is missing or doesn't start with Bearer, return 401 challenge
                if not auth_val.startswith(b"Bearer "):
                    host = host_val.decode("utf-8")
                    proto = proto_val.decode("utf-8")
                    base_url = f"{proto}://{host}"
                    
                    metadata_suffix = "sse" if "sse" in path else "mcp"
                    metadata_url = f"{base_url}/.well-known/oauth-protected-resource/{metadata_suffix}"
                    logger.info(f"Unauthenticated request to {path}. Challenging via middleware.")
                    
                    # Return 401
                    headers = [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", f'Bearer resource_metadata="{metadata_url}"'.encode("utf-8"))
                    ]
                    
                    # Add session ID to headers if present in request (to clean up properly if client sends it)
                    session_id_val = b""
                    for hdr_name, hdr_value in headers_list:
                        if hdr_name == b"mcp-session-id":
                            session_id_val = hdr_value
                            break
                    if session_id_val:
                        headers.append((b"mcp-session-id", session_id_val))

                    error_body = json.dumps({"error": "unauthorized", "message": "Authentication required"}).encode("utf-8")
                    
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": headers
                    })
                    await send({
                        "type": "http.response.body",
                        "body": error_body,
                        "more_body": False
                    })
                    return

                # 2. Delegate to StreamableHTTPSessionManager
                logger.info(f"Delegating {method} {path} to StreamableHTTPSessionManager")
                await self._manager.handle_request(scope, receive, send)
                return

        # Fall through to FastAPI
        await self._app(scope, receive, send)

class WrappedApp:
    """Wraps the FastAPI ASGI app with the MCP transport middleware."""
    def __init__(self, fastapi_app, manager: StreamableHTTPSessionManager):
        self._fastapi_app = fastapi_app
        self._middleware = None
        self._manager = manager
    
    async def __call__(self, scope, receive, send):
        if self._middleware is None:
            self._middleware = _McpTransportMiddleware(self._fastapi_app, self._manager)
        await self._middleware(scope, receive, send)

_wrapped = WrappedApp(app, session_manager)

if __name__ == "__main__":
    import uvicorn
    # Start on custom port if configured — use the wrapped app for middleware support
    port = int(os.environ.get("MCP_SERVER_PORT", "8002"))
    uvicorn.run(_wrapped, host="0.0.0.0", port=port)
