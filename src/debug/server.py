"""
Agent-OS Visual Debug Server
Serves the debug UI dashboard and provides real-time WebSocket streams
for browser screenshots, console logs, network traffic, and command history.
"""
import asyncio
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Dict, Set, Optional

from aiohttp import web

logger = logging.getLogger("agent-os.debug")

STATIC_DIR = Path(__file__).parent / "static"
MAX_LOG_ENTRIES = 500
MAX_COMMAND_HISTORY = 200
SCREENSHOT_INTERVAL = 1.0  # seconds between live screenshots


class DebugServer:
    """
    Visual Debug UI server.

    Serves a real-time web dashboard on a configurable port (default 8002)
    with live browser view, session monitoring, command history, network
    capture, console logs, and system health.
    """

    def __init__(self, config, browser, session_manager, agent_server, persistent_manager=None):
        self.config = config
        self.browser = browser
        self.session_manager = session_manager
        self.agent_server = agent_server
        self.persistent_manager = persistent_manager

        # Real-time data stores
        self._command_history: deque = deque(maxlen=MAX_COMMAND_HISTORY)
        self._console_logs: deque = deque(maxlen=MAX_LOG_ENTRIES)
        self._network_requests: deque = deque(maxlen=MAX_LOG_ENTRIES)
        self._ws_clients: Set[web.WebSocketResponse] = set()

        # Server state
        self._http_app: Optional[web.Application] = None
        self._http_runner: Optional[web.AppRunner] = None
        self._screenshot_task: Optional[asyncio.Task] = None
        self._running = False
        self._start_time = time.time()

    async def start(self):
        """Start the debug UI server."""
        host = self.config.get("server.host", "127.0.0.1")
        port = self.config.get("server.debug_port", 8002)

        self._running = True
        self._http_app = web.Application()
        self._setup_routes()
        self._http_runner = web.AppRunner(self._http_app)
        await self._http_runner.setup()
        site = web.TCPSite(self._http_runner, host, port)
        await site.start()

        # Start live screenshot broadcaster
        self._screenshot_task = asyncio.create_task(self._broadcast_loop())

        logger.info(f"🖥️  Debug UI running at http://{host}:{port}")

    async def stop(self):
        """Stop the debug server."""
        self._running = False
        if self._screenshot_task:
            self._screenshot_task.cancel()
        # Close all WebSocket connections
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()
        if self._http_runner:
            await self._http_runner.cleanup()
        logger.info("Debug server stopped")

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        """Authenticate all debug UI requests via token."""
        # Allow static assets without auth (CSS, JS)
        path = request.path
        if path in ("/style.css", "/app.js"):
            return await handler(request)

        # Require token validation for handoff API endpoints too (security fix)
        # Previously handoff paths were allowed without auth — now they require
        # at least a simple token check to prevent unauthenticated access.

        # Extract token from header, query param, or cookie
        token = (
            request.headers.get("Authorization", "").removeprefix("Bearer ")
            or request.query.get("token")
            or request.cookies.get("agent_token")
        )

        # Validate against agent server's token
        if not token or not self.agent_server._validate_token(token):
            if path == "/" or not path.startswith("/api/"):
                return web.Response(
                    text="Unauthorized — pass ?token=YOUR_TOKEN or Authorization: Bearer YOUR_TOKEN",
                    status=401,
                )
            return web.json_response(
                {"status": "error", "error": "Unauthorized — provide valid token"},
                status=401,
            )

        return await handler(request)

    def _setup_routes(self):
        """Setup HTTP and WebSocket routes."""
        # Static UI (protected by auth middleware)
        self._http_app.router.add_get("/", self._handle_index)
        self._http_app.router.add_get("/style.css", self._handle_css)
        self._http_app.router.add_get("/app.js", self._handle_js)

        # API endpoints
        self._http_app.router.add_get("/api/status", self._handle_api_status)
        self._http_app.router.add_get("/api/sessions", self._handle_api_sessions)
        self._http_app.router.add_get("/api/tabs", self._handle_api_tabs)
        self._http_app.router.add_get("/api/commands", self._handle_api_commands)
        self._http_app.router.add_get("/api/console", self._handle_api_console)
        self._http_app.router.add_get("/api/network", self._handle_api_network)
        self._http_app.router.add_get("/api/dom", self._handle_api_dom)
        self._http_app.router.add_get("/api/cookies", self._handle_api_cookies)
        self._http_app.router.add_get("/api/health", self._handle_api_health)
        self._http_app.router.add_get("/api/screenshot", self._handle_api_screenshot)
        self._http_app.router.add_get("/api/commands-list", self._handle_api_commands_list)
        self._http_app.router.add_get("/api/page-info", self._handle_api_page_info)

        # Action endpoints
        self._http_app.router.add_post("/api/command", self._handle_api_run_command)
        self._http_app.router.add_post("/api/session/destroy", self._handle_api_destroy_session)
        self._http_app.router.add_get("/api/cookies/export", self._handle_api_cookies_export)
        self._http_app.router.add_post("/api/cookies/import", self._handle_api_cookies_import)

        # Login Handoff proxy endpoints (proxy to agent server)
        self._http_app.router.add_get("/api/handoff/list", self._handle_api_handoff_list)
        self._http_app.router.add_get("/api/handoff/history", self._handle_api_handoff_history)
        self._http_app.router.add_get("/api/handoff/stats", self._handle_api_handoff_stats)
        self._http_app.router.add_post("/api/handoff/detect", self._handle_api_handoff_detect)
        self._http_app.router.add_post("/api/handoff/start", self._handle_api_handoff_start)
        self._http_app.router.add_post("/api/handoff/{handoff_id}/complete", self._handle_api_handoff_complete)
        self._http_app.router.add_post("/api/handoff/{handoff_id}/cancel", self._handle_api_handoff_cancel)

        # WebSocket for real-time updates
        self._http_app.router.add_get("/ws", self._handle_ws)

        # Add auth middleware (protects all debug endpoints)
        self._http_app.middlewares.append(self._auth_middleware)

    # ─── Static File Handlers ──────────────────────────────

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the debug UI HTML."""
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return web.Response(text="Debug UI not built yet", status=500)
        return web.FileResponse(index_path)

    async def _handle_css(self, request: web.Request) -> web.Response:
        """Serve CSS."""
        css_path = STATIC_DIR / "style.css"
        if not css_path.exists():
            return web.Response(text="", content_type="text/css")
        return web.FileResponse(css_path)

    async def _handle_js(self, request: web.Request) -> web.Response:
        """Serve JavaScript."""
        js_path = STATIC_DIR / "app.js"
        if not js_path.exists():
            return web.Response(text="", content_type="application/javascript")
        return web.FileResponse(js_path)

    # ─── API Handlers ──────────────────────────────────────

    async def _handle_api_status(self, request: web.Request) -> web.Response:
        """Get overall system status."""
        import psutil
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / 1024 / 1024

        status = {
            "status": "running",
            "version": "3.2.0",
            "uptime_seconds": int(time.time() - self._start_time),
            "ram_usage_mb": round(ram_mb, 1),
            "ram_limit_mb": self.config.get("browser.max_ram_mb", 500),
            "active_sessions": len(self.session_manager.list_active_sessions()),
            "active_ws_clients": len(self.agent_server._ws_clients),
            "browser_active": self.browser.browser is not None,
            "headless": self.config.get("browser.headless", True),
            "persistent_enabled": self.persistent_manager is not None,
            "server_host": self.config.get("server.host", "127.0.0.1"),
            "ws_port": self.config.get("server.ws_port", 8000),
            "http_port": self.config.get("server.http_port", 8001),
            "debug_port": self.config.get("server.debug_port", 8002),
        }
        return web.json_response(status)

    async def _handle_api_sessions(self, request: web.Request) -> web.Response:
        """Get all active sessions."""
        sessions = self.session_manager.list_active_sessions()
        return web.json_response({"sessions": sessions})

    async def _handle_api_tabs(self, request: web.Request) -> web.Response:
        """Get all browser tabs."""
        tabs = []
        for tab_id, page in self.browser._pages.items():
            try:
                url = page.url if page else "about:blank"
                title = await page.title() if page else ""
            except Exception:
                url = "unknown"
                title = ""
            tabs.append({"tab_id": tab_id, "url": url, "title": title})
        return web.json_response({"tabs": tabs})

    async def _handle_api_commands(self, request: web.Request) -> web.Response:
        """Get command execution history."""
        return web.json_response({"commands": list(self._command_history)})

    async def _handle_api_console(self, request: web.Request) -> web.Response:
        """Get browser console logs."""
        return web.json_response({"logs": list(self._console_logs)})

    async def _handle_api_network(self, request: web.Request) -> web.Response:
        """Get captured network requests."""
        return web.json_response({"requests": list(self._network_requests)})

    async def _handle_api_dom(self, request: web.Request) -> web.Response:
        """Get DOM snapshot."""
        try:
            dom = await self.browser.get_dom_snapshot()
            return web.json_response({"status": "success", "dom": dom})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)})

    async def _handle_api_cookies(self, request: web.Request) -> web.Response:
        """Get all cookies."""
        try:
            result = await self.browser.get_cookies()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)})

    async def _handle_api_health(self, request: web.Request) -> web.Response:
        """Get persistent browser health."""
        if self.persistent_manager:
            return web.json_response(self.persistent_manager.get_health())
        return web.json_response({"enabled": False})

    async def _handle_api_screenshot(self, request: web.Request) -> web.Response:
        """Get current screenshot."""
        try:
            b64 = await self.browser.screenshot()
            return web.json_response({"status": "success", "screenshot": b64})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)})

    async def _handle_api_commands_list(self, request: web.Request) -> web.Response:
        """Get list of all available commands."""
        return await self.agent_server._handle_commands_list(request)

    async def _handle_api_page_info(self, request: web.Request) -> web.Response:
        """Get current page info (URL, title, DOM stats)."""
        try:
            pages = []
            for tab_id, page in self.browser._pages.items():
                try:
                    info = await page.evaluate("""() => {
                        return {
                            url: window.location.href,
                            title: document.title,
                            elementCount: document.querySelectorAll('*').length,
                            formCount: document.querySelectorAll('form').length,
                            linkCount: document.querySelectorAll('a').length,
                            imageCount: document.querySelectorAll('img').length,
                            scriptCount: document.querySelectorAll('script').length,
                        }
                    }""")
                    info["tab_id"] = tab_id
                    pages.append(info)
                except Exception:
                    pages.append({"tab_id": tab_id, "url": "unknown", "error": "page not available"})
            return web.json_response({"pages": pages})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)})

    # ─── Action Handlers ───────────────────────────────────

    async def _handle_api_run_command(self, request: web.Request) -> web.Response:
        """Run a command from the debug UI."""
        try:
            data = await request.json()
            token = data.pop("token", None)
            if not token:
                return web.json_response({"status": "error", "error": "Missing token"})

            # Add token back for command processing
            data["token"] = token

            # Record command start
            cmd_entry = {
                "command": data.get("command", "unknown"),
                "params": {k: v for k, v in data.items() if k not in ("token",)},
                "timestamp": time.time(),
                "status": "running",
            }
            self._command_history.append(cmd_entry)

            # Execute via agent server
            result = await self.agent_server._process_command(data)

            # Update command record
            cmd_entry["status"] = result.get("status", "unknown")
            cmd_entry["result"] = result

            # Broadcast to all WS clients
            await self._broadcast({
                "type": "command",
                "data": cmd_entry,
            })

            return web.json_response(result)
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=400)

    async def _handle_api_destroy_session(self, request: web.Request) -> web.Response:
        """Destroy a session."""
        try:
            data = await request.json()
            session_id = data.get("session_id")
            if not session_id:
                return web.json_response({"status": "error", "error": "Missing session_id"})
            await self.session_manager.destroy_session(session_id)
            return web.json_response({"status": "success", "destroyed": session_id})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=400)

    async def _handle_api_cookies_export(self, request: web.Request) -> web.Response:
        """Export all cookies as a downloadable JSON file."""
        try:
            result = await self.browser.get_cookies()
            cookies = result.get("cookies", [])
            export_data = {
                "version": "1.0",
                "agent_os_version": "3.2.0",
                "exported_at": time.time(),
                "cookie_count": len(cookies),
                "cookies": cookies,
            }
            # Pretty-print for readability
            body = json.dumps(export_data, indent=2, ensure_ascii=False)
            filename = f"agent-os-cookies-{int(time.time())}.json"
            return web.Response(
                body=body,
                content_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Cookie-Count": str(len(cookies)),
                },
            )
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def _handle_api_cookies_import(self, request: web.Request) -> web.Response:
        """Import cookies from a JSON file upload."""
        try:
            # Support both multipart file upload and raw JSON body
            content_type = request.content_type or ""

            if "multipart" in content_type:
                reader = await request.multipart()
                field = await reader.next()
                if not field or field.name != "file":
                    return web.json_response({"status": "error", "error": "Expected file field named 'file'"}, status=400)
                file_data = await field.read()
                import_data = json.loads(file_data.decode("utf-8"))
            else:
                import_data = await request.json()

            # Support multiple formats:
            # 1. Our export format: {"cookies": [...]}
            # 2. Plain array: [...]
            # 3. Chrome-style: {"cookies": [{"name":..., "value":..., ...}]}
            # 4. Netscape/wget format lines
            if isinstance(import_data, list):
                cookies = import_data
            elif isinstance(import_data, dict):
                cookies = import_data.get("cookies", [])
                # Also support key-value dict format: {"name": "value", ...}
                if not cookies and not import_data.get("version"):
                    # Try treating as key-value pairs
                    cookies = [{"name": k, "value": v} for k, v in import_data.items() if isinstance(v, str)]
            else:
                return web.json_response({"status": "error", "error": "Invalid cookie format"}, status=400)

            if not cookies:
                return web.json_response({"status": "error", "error": "No cookies found in import data"}, status=400)

            # Import each cookie via browser
            imported = 0
            skipped = 0
            errors = []

            for cookie in cookies:
                try:
                    name = cookie.get("name")
                    value = cookie.get("value")
                    if not name or value is None:
                        skipped += 1
                        continue

                    # Build cookie params, supporting multiple formats
                    params = {
                        "name": name,
                        "value": str(value),
                        "domain": cookie.get("domain"),
                        "path": cookie.get("path", "/"),
                        "secure": cookie.get("secure", False),
                        "http_only": cookie.get("httpOnly", cookie.get("http_only", False)),
                        "same_site": cookie.get("sameSite", cookie.get("same_site")),
                    }

                    # Handle expires field (can be number or string)
                    expires = cookie.get("expires")
                    if expires is not None:
                        params["expires"] = expires

                    result = await self.browser.set_cookie(**params)
                    if result.get("status") == "success":
                        imported += 1
                    else:
                        skipped += 1
                        errors.append(f"{name}: {result.get('error', 'unknown error')}")
                except Exception as e:
                    skipped += 1
                    errors.append(f"{cookie.get('name', '?')}: {str(e)}")

            return web.json_response({
                "status": "success",
                "imported": imported,
                "skipped": skipped,
                "total": len(cookies),
                "errors": errors[:10] if errors else [],
            })
        except json.JSONDecodeError as e:
            return web.json_response({"status": "error", "error": f"Invalid JSON: {e}"}, status=400)
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    # ─── WebSocket Handler ─────────────────────────────────

    async def _handle_ws(self, request: web.Request):
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.info(f"Debug client connected (total: {len(self._ws_clients)})")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            self._ws_clients.discard(ws)
            logger.info(f"Debug client disconnected (total: {len(self._ws_clients)})")

        return ws

    async def _handle_ws_message(self, ws: web.WebSocketResponse, data: Dict):
        """Handle incoming WebSocket messages from the debug client."""
        action = data.get("action")

        if action == "screenshot":
            try:
                b64 = await self.browser.screenshot()
                await ws.send_json({"type": "screenshot", "data": b64})
            except Exception as e:
                await ws.send_json({"type": "error", "error": str(e)})

        elif action == "ping":
            await ws.send_json({"type": "pong", "timestamp": time.time()})

    # ─── Login Handoff Proxy Handlers ────────────────────────

    async def _get_handoff_manager(self):
        """Get the LoginHandoffManager from the agent server."""
        try:
            return await self.agent_server._get_login_handoff()
        except Exception:
            return None

    async def _handle_api_handoff_list(self, request: web.Request) -> web.Response:
        """GET /api/handoff/list — List all handoff sessions."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        state_filter = request.query.get("state")
        user_id = request.query.get("user_id")
        result = await handoff.list_handoffs(state_filter=state_filter, user_id=user_id)
        return web.json_response(result)

    async def _handle_api_handoff_history(self, request: web.Request) -> web.Response:
        """GET /api/handoff/history — Get completed handoff history."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        limit = int(request.query.get("limit", "50"))
        result = await handoff.get_handoff_history(limit=limit)
        return web.json_response(result)

    async def _handle_api_handoff_stats(self, request: web.Request) -> web.Response:
        """GET /api/handoff/stats — Get handoff statistics."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        result = {"status": "success", **handoff.get_stats()}
        return web.json_response(result)

    async def _handle_api_handoff_detect(self, request: web.Request) -> web.Response:
        """POST /api/handoff/detect — Detect if current page is a login page."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        try:
            data = await request.json()
        except Exception:
            data = {}
        result = await handoff.detect_login_page(page_id=data.get("page_id", "main"))
        return web.json_response(result)

    async def _handle_api_handoff_start(self, request: web.Request) -> web.Response:
        """POST /api/handoff/start — Start a login handoff session."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        try:
            data = await request.json()
        except Exception:
            data = {}
        result = await handoff.start_handoff(
            url=data.get("url", ""),
            page_id=data.get("page_id", "main"),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            timeout_seconds=data.get("timeout_seconds", 300),
            auto_detected=data.get("auto_detected", False),
        )
        return web.json_response(result)

    async def _handle_api_handoff_complete(self, request: web.Request) -> web.Response:
        """POST /api/handoff/{handoff_id}/complete — Mark handoff as completed."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        handoff_id = request.match_info.get("handoff_id", "")
        if not handoff_id:
            return web.json_response({"status": "error", "error": "Missing handoff_id"}, status=400)
        try:
            data = await request.json()
        except Exception:
            data = {}
        result = await handoff.complete_handoff(handoff_id, user_id=data.get("user_id", ""))

        # Broadcast completion to all WS clients
        await self._broadcast({
            "type": "login_handoff",
            "event": "login_handoff_completed",
            "data": result,
        })

        return web.json_response(result)

    async def _handle_api_handoff_cancel(self, request: web.Request) -> web.Response:
        """POST /api/handoff/{handoff_id}/cancel — Cancel a handoff session."""
        handoff = await self._get_handoff_manager()
        if not handoff:
            return web.json_response({"status": "error", "error": "Handoff not available"}, status=503)
        handoff_id = request.match_info.get("handoff_id", "")
        if not handoff_id:
            return web.json_response({"status": "error", "error": "Missing handoff_id"}, status=400)
        try:
            data = await request.json()
        except Exception:
            data = {}
        result = await handoff.cancel_handoff(handoff_id, reason=data.get("reason", ""))

        # Broadcast cancellation to all WS clients
        await self._broadcast({
            "type": "login_handoff",
            "event": "login_handoff_cancelled",
            "data": result,
        })

        return web.json_response(result)

    # ─── Real-time Broadcast Loop ──────────────────────────

    async def _broadcast_loop(self):
        """Background task that broadcasts live screenshots and updates."""
        while self._running:
            try:
                if self._ws_clients and self.browser.browser:
                    try:
                        b64 = await self.browser.screenshot()
                        await self._broadcast({
                            "type": "screenshot",
                            "data": b64,
                        })
                    except Exception:
                        pass

                # Also broadcast system status periodically
                import psutil
                process = psutil.Process(os.getpid())
                ram_mb = process.memory_info().rss / 1024 / 1024
                await self._broadcast({
                    "type": "status",
                    "data": {
                        "ram_mb": round(ram_mb, 1),
                        "uptime": int(time.time() - self._start_time),
                        "sessions": len(self.session_manager.list_active_sessions()),
                        "ws_clients": len(self.agent_server._ws_clients),
                        "tabs": len(self.browser._pages),
                    },
                })

                await asyncio.sleep(SCREENSHOT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(SCREENSHOT_INTERVAL)

    async def _broadcast(self, message: Dict):
        """Broadcast a message to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # ─── Command Recording (called by agent server) ────────

    def record_command(self, command: str, params: Dict, result: Dict):
        """Record a command execution for the debug UI."""
        entry = {
            "command": command,
            "params": params,
            "result": result,
            "status": result.get("status", "unknown"),
            "timestamp": time.time(),
        }
        self._command_history.append(entry)

    def record_console_log(self, level: str, message: str, source: str = ""):
        """Record a console log entry."""
        entry = {
            "level": level,
            "message": message,
            "source": source,
            "timestamp": time.time(),
        }
        self._console_logs.append(entry)

    def record_network_request(self, request_data: Dict):
        """Record a network request."""
        request_data["timestamp"] = time.time()
        self._network_requests.append(request_data)
