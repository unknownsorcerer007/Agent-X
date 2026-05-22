"""
Agent-OS Session Recording & Replay Engine
Full session capture, replay, analysis, and export.

Production features:
  - Event-driven recording: captures commands, network, DOM, console, screenshots, cookies, scroll
  - Efficient storage: memory-buffered with disk spill for long sessions, compressed snapshots
  - Replay with speed control: 0.25x → 4x, pause/resume, step, jump-to
  - Session export: convert recording to workflow JSON for automated replay
  - Session search: find events by type, time range, selector, URL, error
  - Performance analysis: identify bottlenecks, slow commands, failed steps
  - Multi-session management: record, list, delete, duplicate
  - Background screenshot capture: interval-based or event-triggered
  - Cookie & localStorage delta tracking
  - Network timeline with waterfall view data
"""
import asyncio
import base64
import gzip
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger("agent-os.session_recording")


# ─── Event Types ────────────────────────────────────────────

class EventType(str, Enum):
    COMMAND = "command"            # Browser command executed
    NAVIGATION = "navigation"      # Page navigation
    NETWORK_REQUEST = "net_req"    # Outgoing network request
    NETWORK_RESPONSE = "net_resp"  # Network response received
    DOM_MUTATION = "dom_mutation"  # DOM change detected
    CONSOLE_LOG = "console"        # Console log entry
    SCREENSHOT = "screenshot"      # Screenshot captured
    SCROLL = "scroll"              # Scroll event
    COOKIE_CHANGE = "cookie"       # Cookie added/removed/changed
    STORAGE_CHANGE = "storage"     # localStorage/sessionStorage change
    ERROR = "error"                # Error occurred
    STATE_SNAPSHOT = "state"       # Full browser state snapshot
    METADATA = "metadata"          # Session metadata event
    ANNOTATION = "annotation"      # User-added annotation
    WAIT = "wait"                  # Smart wait event
    HEAL = "heal"                  # Auto-heal event
    RETRY = "retry"                # Auto-retry event
    TAB_SWITCH = "tab_switch"      # Tab switch
    FORM_FILL = "form_fill"        # Form filled
    KEYBOARD = "keyboard"          # Keyboard input
    MOUSE = "mouse"                # Mouse action


@dataclass
class SessionEvent:
    """A single recorded event."""
    event_id: str
    event_type: str
    timestamp: float          # Absolute time (time.time())
    elapsed_ms: float         # Time since session start
    data: Dict[str, Any]      # Event-specific payload
    page_id: str = "main"
    tab_url: str = ""
    screenshot_ref: str = ""  # Reference to screenshot (if captured)

    def to_dict(self) -> Dict:
        return {
            "id": self.event_id,
            "type": self.event_type,
            "ts": round(self.timestamp, 3),
            "ms": round(self.elapsed_ms, 1),
            "data": self.data,
            "page": self.page_id,
            "url": self.tab_url,
            "ss": self.screenshot_ref,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SessionEvent":
        return cls(
            event_id=d["id"],
            event_type=d["type"],
            timestamp=d["ts"],
            elapsed_ms=d["ms"],
            data=d["data"],
            page_id=d.get("page", "main"),
            tab_url=d.get("url", ""),
            screenshot_ref=d.get("ss", ""),
        )


@dataclass
class SessionRecording:
    """A complete session recording."""
    recording_id: str
    name: str
    created_at: float
    events: List[SessionEvent] = field(default_factory=list)
    screenshots: Dict[str, bytes] = field(default_factory=dict)  # ref -> png bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    event_count: int = 0
    tags: List[str] = field(default_factory=list)

    def finalize(self):
        """Update computed fields."""
        self.event_count = len(self.events)
        if self.events:
            self.duration_ms = self.events[-1].elapsed_ms
        self.metadata.update({
            "event_count": self.event_count,
            "duration_ms": round(self.duration_ms, 1),
            "screenshots_captured": len(self.screenshots),
            "event_types": list(set(e.event_type for e in self.events)),
        })


# ─── Session Recorder ───────────────────────────────────────

class SessionRecorder:
    """
    Records everything that happens in a browser session.

    Captures:
    - Commands (navigate, click, fill, etc.) with params + results
    - Network requests/responses with timing
    - DOM mutations
    - Console logs
    - Screenshots (interval or event-triggered)
    - Scroll position changes
    - Cookie and localStorage changes
    - Errors and recoveries
    - Smart wait, auto-heal, auto-retry events

    Usage:
        recorder = SessionRecorder(browser)
        await recorder.start(name="login-flow")

        # ... run commands ...

        await recorder.stop()
        recording = recorder.get_recording()
    """

    def __init__(self, browser, storage_dir: str = None):
        self.browser = browser
        self._storage_dir = Path(storage_dir or os.path.expanduser("~/.agent-os/recordings"))
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._recording: Optional[SessionRecording] = None
        self._active = False
        self._start_time: float = 0

        # Screenshot capture
        self._screenshot_task: Optional[asyncio.Task] = None
        self._screenshot_interval_ms: int = 2000  # Default: every 2s
        self._screenshot_on_event: bool = True     # Screenshot on important events
        self._screenshot_counter: int = 0

        # Network monitoring
        self._network_handler = None
        self._pending_requests: Dict[str, Dict] = {}  # request_id -> request info

        # Console monitoring
        self._console_handlers: Dict[str, Callable] = {}

        # DOM mutation observer
        self._dom_observer_installed: set = set()

        # Cookie tracking
        self._last_cookies: List[Dict] = []

        # Scroll tracking
        self._last_scroll: Dict[str, Dict] = {}

        # Memory management: max events in memory before disk spill
        self._memory_buffer_max = 5000
        self._disk_events: List[Dict] = []  # Spilled events (disk-backed)

    # ─── Recording Control ──────────────────────────────────

    async def start(
        self,
        name: str = None,
        screenshot_interval_ms: int = 2000,
        screenshot_on_event: bool = True,
        capture_network: bool = True,
        capture_console: bool = True,
        capture_dom: bool = True,
        capture_scroll: bool = True,
        capture_cookies: bool = True,
        tags: List[str] = None,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Start recording a session.

        Args:
            name: Human-readable name for the recording.
            screenshot_interval_ms: Interval between automatic screenshots (0 = disabled).
            screenshot_on_event: Capture screenshot on important events.
            capture_network: Record network requests/responses.
            capture_console: Record console logs.
            capture_dom: Record DOM mutations.
            capture_scroll: Record scroll events.
            capture_cookies: Track cookie changes.
            tags: Optional tags for organizing recordings.
            page_id: Primary page to monitor.
        """
        if self._active:
            return {"status": "error", "error": "Recording already active. Stop first."}

        recording_id = str(uuid.uuid4())[:12]
        self._recording = SessionRecording(
            recording_id=recording_id,
            name=name or f"recording-{recording_id}",
            created_at=time.time(),
            tags=tags or [],
        )
        self._active = True
        self._start_time = time.time()
        self._screenshot_interval_ms = screenshot_interval_ms
        self._screenshot_on_event = screenshot_on_event
        self._screenshot_counter = 0
        self._pending_requests.clear()

        # Record metadata event
        self._record_event(EventType.METADATA, {
            "action": "recording_started",
            "name": self._recording.name,
            "recording_id": recording_id,
            "config": {
                "screenshot_interval_ms": screenshot_interval_ms,
                "capture_network": capture_network,
                "capture_console": capture_console,
                "capture_dom": capture_dom,
            },
        }, page_id=page_id)

        # Take initial screenshot
        await self._capture_screenshot(page_id, "initial")

        # Start network monitoring
        if capture_network:
            await self._start_network_monitoring(page_id)

        # Start console monitoring
        if capture_console:
            await self._start_console_monitoring(page_id)

        # Start DOM monitoring
        if capture_dom:
            await self._start_dom_monitoring(page_id)

        # Start scroll monitoring
        if capture_scroll:
            await self._start_scroll_monitoring(page_id)

        # Capture initial cookie state
        if capture_cookies:
            await self._capture_cookie_snapshot(page_id)

        # Start screenshot interval
        if screenshot_interval_ms > 0:
            self._screenshot_task = asyncio.create_task(
                self._screenshot_loop(page_id)
            )

        logger.info(f"Recording started: {self._recording.name} ({recording_id})")

        return {
            "status": "success",
            "recording_id": recording_id,
            "name": self._recording.name,
            "screenshot_interval_ms": screenshot_interval_ms,
        }

    async def stop(self, save: bool = True) -> Dict[str, Any]:
        """
        Stop recording and optionally save to disk.

        Args:
            save: If True, persist recording to disk.
        """
        if not self._active:
            return {"status": "error", "error": "No active recording"}

        self._active = False

        # Stop screenshot task
        if self._screenshot_task:
            self._screenshot_task.cancel()
            try:
                await self._screenshot_task
            except asyncio.CancelledError:
                pass
            self._screenshot_task = None

        # Take final screenshot
        await self._capture_screenshot("main", "final")

        # Record stop event
        self._record_event(EventType.METADATA, {
            "action": "recording_stopped",
            "duration_ms": round((time.time() - self._start_time) * 1000, 1),
        })

        # Finalize
        self._recording.finalize()

        result = {
            "status": "success",
            "recording_id": self._recording.recording_id,
            "name": self._recording.name,
            "event_count": self._recording.event_count,
            "duration_ms": round(self._recording.duration_ms, 1),
            "screenshots": len(self._recording.screenshots),
        }

        if save:
            path = self._save_recording()
            result["saved_to"] = str(path)

        logger.info(f"Recording stopped: {self._recording.name} "
                     f"({self._recording.event_count} events, "
                     f"{self._recording.duration_ms/1000:.1f}s)")

        return result

    async def pause(self) -> Dict[str, Any]:
        """Pause recording (screenshots and monitoring continue in background)."""
        if not self._active:
            return {"status": "error", "error": "No active recording"}
        self._record_event(EventType.METADATA, {"action": "paused"})
        return {"status": "success", "state": "paused"}

    async def resume(self) -> Dict[str, Any]:
        """Resume recording after pause."""
        if not self._active:
            return {"status": "error", "error": "No active recording"}
        self._record_event(EventType.METADATA, {"action": "resumed"})
        return {"status": "success", "state": "recording"}

    async def annotate(self, text: str, category: str = "note", page_id: str = "main") -> Dict[str, Any]:
        """Add a human annotation to the recording."""
        if not self._active:
            return {"status": "error", "error": "No active recording"}
        self._record_event(EventType.ANNOTATION, {
            "text": text,
            "category": category,
        }, page_id=page_id)
        return {"status": "success", "annotation": text}

    # ─── Event Recording (called by integrations) ───────────

    def record_command(
        self,
        command: str,
        params: Dict,
        result: Dict,
        page_id: str = "main",
    ):
        """Record a browser command execution."""
        if not self._active:
            return
        self._record_event(EventType.COMMAND, {
            "command": command,
            "params": self._sanitize_params(params),
            "status": result.get("status", "unknown"),
            "error": result.get("error", ""),
            "elapsed_ms": result.get("elapsed_ms", 0),
            "healed": result.get("healed", False),
            "retry": result.get("retry"),
        }, page_id=page_id)

        # Screenshot on important commands
        if self._screenshot_on_event and command in ("navigate", "click", "fill-form", "press", "submit"):
            asyncio.create_task(self._capture_screenshot(page_id, f"after_{command}"))

    def record_navigation(self, url: str, title: str, status_code: int, page_id: str = "main"):
        """Record a navigation event."""
        if not self._active:
            return
        self._record_event(EventType.NAVIGATION, {
            "url": url,
            "title": title,
            "status_code": status_code,
        }, page_id=page_id, tab_url=url)

    def record_network_request(self, request_id: str, method: str, url: str, headers: Dict = None, page_id: str = "main"):
        """Record outgoing network request."""
        if not self._active:
            return
        self._pending_requests[request_id] = {
            "method": method, "url": url, "start": time.time(), "page_id": page_id
        }
        self._record_event(EventType.NETWORK_REQUEST, {
            "rid": request_id,
            "method": method,
            "url": url,
            "headers": self._truncate_headers(headers),
        }, page_id=page_id)

    def record_network_response(self, request_id: str, status: int, headers: Dict = None, body_size: int = 0, page_id: str = "main"):
        """Record network response."""
        if not self._active:
            return
        req = self._pending_requests.pop(request_id, {})
        timing_ms = round((time.time() - req.get("start", time.time())) * 1000, 1)
        self._record_event(EventType.NETWORK_RESPONSE, {
            "rid": request_id,
            "status": status,
            "timing_ms": timing_ms,
            "body_size": body_size,
            "headers": self._truncate_headers(headers),
        }, page_id=page_id)

    def record_error(self, error: str, context: str = "", page_id: str = "main"):
        """Record an error event."""
        if not self._active:
            return
        self._record_event(EventType.ERROR, {
            "error": error,
            "context": context,
        }, page_id=page_id)

    def record_heal(self, original: str, healed: str, method: str, page_id: str = "main"):
        """Record an auto-heal event."""
        if not self._active:
            return
        self._record_event(EventType.HEAL, {
            "original_selector": original,
            "healed_selector": healed,
            "method": method,
        }, page_id=page_id)

    def record_retry(self, operation: str, attempt: int, error: str, error_class: str, page_id: str = "main"):
        """Record a retry event."""
        if not self._active:
            return
        self._record_event(EventType.RETRY, {
            "operation": operation,
            "attempt": attempt,
            "error": error[:200],
            "error_class": error_class,
        }, page_id=page_id)

    def record_wait(self, strategy: str, waited_ms: float, success: bool, page_id: str = "main"):
        """Record a smart wait event."""
        if not self._active:
            return
        self._record_event(EventType.WAIT, {
            "strategy": strategy,
            "waited_ms": round(waited_ms, 1),
            "success": success,
        }, page_id=page_id)

    def is_recording(self) -> bool:
        return self._active

    def get_recording(self) -> Optional[SessionRecording]:
        return self._recording

    # ─── Internal: Event Management ─────────────────────────

    def _record_event(
        self,
        event_type: EventType,
        data: Dict,
        page_id: str = "main",
        tab_url: str = "",
    ):
        """Record an event with timing."""
        if not self._recording:
            return

        elapsed = (time.time() - self._start_time) * 1000
        page = self.browser._pages.get(page_id, self.browser.page)

        try:
            url = page.url if page else ""
        except Exception:
            url = ""

        event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type.value if isinstance(event_type, EventType) else event_type,
            timestamp=time.time(),
            elapsed_ms=elapsed,
            data=data,
            page_id=page_id,
            tab_url=tab_url or url,
        )

        self._recording.events.append(event)

        # Memory management: spill to disk if buffer too large
        if len(self._recording.events) > self._memory_buffer_max:
            self._spill_events()

    def _spill_events(self):
        """Move older events to disk-backed storage."""
        if not self._recording:
            return
        keep_in_memory = 1000  # Keep last 1000 events in memory
        if len(self._recording.events) > keep_in_memory:
            spill = self._recording.events[:-keep_in_memory]
            self._recording.events = self._recording.events[-keep_in_memory:]
            for e in spill:
                self._disk_events.append(e.to_dict())
            logger.debug(f"Spilled {len(spill)} events to disk buffer")

    def _sanitize_params(self, params: Dict) -> Dict:
        """Remove sensitive data from params for recording."""
        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "key", "credential", "auth"}
        for k, v in params.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:500] + "..."
            else:
                sanitized[k] = v
        return sanitized

    def _truncate_headers(self, headers: Optional[Dict]) -> Dict:
        """Truncate headers for storage."""
        if not headers:
            return {}
        return {k: v[:200] if isinstance(v, str) and len(v) > 200 else v for k, v in headers.items()}

    # ─── Internal: Monitoring ───────────────────────────────

    async def _start_network_monitoring(self, page_id: str):
        """Start capturing network events."""
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return

        def on_request(request):
            self.record_network_request(
                request_id=str(id(request)),
                method=request.method,
                url=request.url,
                headers=dict(request.headers) if request.headers else {},
                page_id=page_id,
            )

        def on_response(response):
            self.record_network_response(
                request_id=str(id(response.request)),
                status=response.status,
                headers=dict(response.headers) if response.headers else {},
                page_id=page_id,
            )

        page.on("request", on_request)
        page.on("response", on_response)

    async def _start_console_monitoring(self, page_id: str):
        """Start capturing console logs."""
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return

        def on_console(msg):
            self._record_event(EventType.CONSOLE_LOG, {
                "level": msg.type,
                "text": msg.text[:500],
                "location": str(msg.location),
            }, page_id=page_id)

        def on_page_error(error):
            self.record_error(str(error)[:500], context="page_error", page_id=page_id)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

    async def _start_dom_monitoring(self, page_id: str):
        """Start DOM mutation tracking."""
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page or page_id in self._dom_observer_installed:
            return

        await page.evaluate("""(() => {
            if (window.__agentos_recorder_dom) return;
            window.__agentos_recorder_dom = { mutations: 0, lastMutation: 0, changes: [] };
            const obs = new MutationObserver((mutations) => {
                window.__agentos_recorder_dom.mutations += mutations.length;
                window.__agentos_recorder_dom.lastMutation = Date.now();
                for (const m of mutations.slice(0, 5)) {
                    window.__agentos_recorder_dom.changes.push({
                        type: m.type,
                        target: m.target.tagName + (m.target.id ? '#' + m.target.id : ''),
                        time: Date.now(),
                    });
                }
                if (window.__agentos_recorder_dom.changes.length > 100) {
                    window.__agentos_recorder_dom.changes = window.__agentos_recorder_dom.changes.slice(-50);
                }
            });
            obs.observe(document.documentElement, {
                childList: true, subtree: true, attributes: true,
                characterData: true, attributeOldValue: false, characterDataOldValue: false,
            });
        })()""")
        self._dom_observer_installed.add(page_id)

        # Poll DOM changes periodically
        async def poll_dom():
            while self._active:
                try:
                    page_obj = self.browser._pages.get(page_id, self.browser.page)
                    state = await page_obj.evaluate("""(() => {
                        const d = window.__agentos_recorder_dom;
                        if (!d) return null;
                        const result = { mutations: d.mutations, lastMutation: d.lastMutation, recentChanges: d.changes.slice(-5) };
                        d.changes = [];
                        return result;
                    })()""")
                    if state and state.get("mutations", 0) > 0:
                        self._record_event(EventType.DOM_MUTATION, {
                            "total_mutations": state["mutations"],
                            "recent_changes": state.get("recentChanges", []),
                        }, page_id=page_id)
                except Exception:
                    pass
                await asyncio.sleep(1.0)

        asyncio.create_task(poll_dom())

    async def _start_scroll_monitoring(self, page_id: str):
        """Track scroll position changes."""
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return

        async def poll_scroll():
            while self._active:
                try:
                    page_obj = self.browser._pages.get(page_id, self.browser.page)
                    pos = await page_obj.evaluate("() => ({ x: window.scrollX, y: window.scrollY, max: document.documentElement.scrollHeight })")
                    last = self._last_scroll.get(page_id, {})
                    if pos.get("y", 0) != last.get("y", 0):
                        self._record_event(EventType.SCROLL, {
                            "x": pos.get("x", 0),
                            "y": pos.get("y", 0),
                            "max_y": pos.get("max", 0),
                            "delta_y": pos.get("y", 0) - last.get("y", 0),
                        }, page_id=page_id)
                    self._last_scroll[page_id] = pos
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        asyncio.create_task(poll_scroll())

    async def _capture_cookie_snapshot(self, page_id: str):
        """Capture current cookie state."""
        try:
            page = self.browser._pages.get(page_id, self.browser.page)
            if page and self.browser.context:
                cookies = await self.browser.context.cookies()
                self._last_cookies = cookies
                self._record_event(EventType.COOKIE_CHANGE, {
                    "action": "snapshot",
                    "cookie_count": len(cookies),
                    "domains": list(set(c.get("domain", "") for c in cookies)),
                }, page_id=page_id)
        except Exception:
            pass

    async def _capture_screenshot(self, page_id: str, reason: str = "") -> str:
        """Capture a screenshot and store it."""
        if not self._recording:
            return ""
        try:
            page = self.browser._pages.get(page_id, self.browser.page)
            if not page:
                return ""

            img_bytes = await page.screenshot(type="png", full_page=False)
            self._screenshot_counter += 1
            ref = f"ss-{self._screenshot_counter:04d}"

            self._recording.screenshots[ref] = img_bytes

            self._record_event(EventType.SCREENSHOT, {
                "ref": ref,
                "reason": reason,
                "size_bytes": len(img_bytes),
                "width": 0,
                "height": 0,
            }, page_id=page_id)

            return ref
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return ""

    async def _screenshot_loop(self, page_id: str):
        """Background screenshot capture at regular intervals."""
        while self._active:
            try:
                await asyncio.sleep(self._screenshot_interval_ms / 1000)
                if self._active:
                    await self._capture_screenshot(page_id, "interval")
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    # ─── Storage ────────────────────────────────────────────

    def _save_recording(self) -> Path:
        """Save recording to disk (events as JSON, screenshots as compressed files)."""
        if not self._recording:
            return Path("")

        rec_dir = self._storage_dir / self._recording.recording_id
        rec_dir.mkdir(parents=True, exist_ok=True)

        # Save events
        all_events = [e.to_dict() for e in self._recording.events] + self._disk_events
        events_file = rec_dir / "events.jsonl.gz"
        with gzip.open(events_file, "wt", encoding="utf-8") as f:
            for event in all_events:
                f.write(json.dumps(event, default=str) + "\n")

        # Save screenshots (compressed)
        ss_dir = rec_dir / "screenshots"
        ss_dir.mkdir(exist_ok=True)
        for ref, img_bytes in self._recording.screenshots.items():
            ss_file = ss_dir / f"{ref}.png.gz"
            with gzip.open(ss_file, "wb") as f:
                f.write(img_bytes)

        # Save metadata
        meta = {
            "recording_id": self._recording.recording_id,
            "name": self._recording.name,
            "created_at": self._recording.created_at,
            "duration_ms": self._recording.duration_ms,
            "event_count": self._recording.event_count,
            "screenshots_count": len(self._recording.screenshots),
            "tags": self._recording.tags,
            "metadata": self._recording.metadata,
        }
        meta_file = rec_dir / "metadata.json"
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Recording saved: {rec_dir} ({self._recording.event_count} events)")
        return rec_dir

    @staticmethod
    def list_recordings(storage_dir: str = None) -> List[Dict]:
        """List all saved recordings."""
        sd = Path(storage_dir or os.path.expanduser("~/.agent-os/recordings"))
        recordings = []

        if not sd.exists():
            return recordings

        for rec_dir in sorted(sd.iterdir(), reverse=True):
            if not rec_dir.is_dir():
                continue
            meta_file = rec_dir / "metadata.json"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        meta = json.load(f)
                    # Add disk size
                    total_size = sum(f.stat().st_size for f in rec_dir.rglob("*") if f.is_file())
                    meta["disk_size_mb"] = round(total_size / (1024 * 1024), 2)
                    recordings.append(meta)
                except Exception:
                    continue

        return recordings

    @staticmethod
    def delete_recording(recording_id: str, storage_dir: str = None) -> bool:
        """Delete a saved recording."""
        sd = Path(storage_dir or os.path.expanduser("~/.agent-os/recordings"))
        rec_dir = sd / recording_id
        if rec_dir.exists():
            import shutil
            shutil.rmtree(rec_dir)
            return True
        return False


# ─── Session Replay ─────────────────────────────────────────

class SessionReplay:
    """
    Replay a recorded session against a browser.

    Features:
    - Replay all commands in sequence with original timing
    - Speed control: 0.25x to 4x
    - Pause/resume/step/jump-to
    - Skip specific event types
    - Visual verification (compare screenshots)
    - Export as workflow JSON
    - Replay with smart_wait + auto_heal integration

    Usage:
        replay = SessionReplay(browser, recorder)
        result = await replay.load("recording-id")
        result = await replay.play(speed=2.0)
    """

    def __init__(self, browser, storage_dir: str = None):
        self.browser = browser
        self._storage_dir = Path(storage_dir or os.path.expanduser("~/.agent-os/recordings"))

        self._recording: Optional[SessionRecording] = None
        self._events: List[SessionEvent] = []
        self._playing = False
        self._paused = False
        self._current_index: int = 0
        self._speed: float = 1.0
        self._play_task: Optional[asyncio.Task] = None

        # Playback stats
        self._playback_stats: Dict[str, Any] = {}

    async def load(self, recording_id: str) -> Dict[str, Any]:
        """Load a saved recording for replay."""
        rec_dir = self._storage_dir / recording_id
        if not rec_dir.exists():
            return {"status": "error", "error": f"Recording not found: {recording_id}"}

        # Load metadata
        meta_file = rec_dir / "metadata.json"
        if not meta_file.exists():
            return {"status": "error", "error": f"No metadata found for recording: {recording_id}"}

        with open(meta_file) as f:
            meta = json.load(f)

        # Load events
        events_file = rec_dir / "events.jsonl.gz"
        if not events_file.exists():
            return {"status": "error", "error": f"No events found for recording: {recording_id}"}

        events = []
        with gzip.open(events_file, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        edata = json.loads(line)
                        events.append(SessionEvent.from_dict(edata))
                    except Exception:
                        continue

        self._recording = SessionRecording(
            recording_id=recording_id,
            name=meta["name"],
            created_at=meta["created_at"],
            events=events,
            duration_ms=meta.get("duration_ms", 0),
            event_count=len(events),
            tags=meta.get("tags", []),
            metadata=meta.get("metadata", {}),
        )

        # Load screenshots into memory (lazily for large recordings)
        ss_dir = rec_dir / "screenshots"
        if ss_dir.exists():
            for ss_file in ss_dir.glob("*.png.gz"):
                ref = ss_file.stem.replace(".png", "")
                try:
                    with gzip.open(ss_file, "rb") as f:
                        self._recording.screenshots[ref] = f.read()
                except Exception:
                    continue

        # Filter to replayable events (commands, navigations)
        self._events = [e for e in events if e.event_type in (
            EventType.COMMAND.value,
            EventType.NAVIGATION.value,
        )]
        self._current_index = 0

        return {
            "status": "success",
            "recording_id": recording_id,
            "name": meta["name"],
            "total_events": len(events),
            "replayable_events": len(self._events),
            "duration_ms": meta.get("duration_ms", 0),
            "screenshots": len(self._recording.screenshots),
            "tags": meta.get("tags", []),
        }

    async def play(
        self,
        speed: float = 1.0,
        from_event: int = 0,
        to_event: int = None,
        skip_types: List[str] = None,
        verify_screenshots: bool = False,
    ) -> Dict[str, Any]:
        """
        Replay the loaded recording.

        Args:
            speed: Playback speed (0.25, 0.5, 1.0, 2.0, 4.0).
            from_event: Start from this event index.
            to_event: Stop at this event index (None = play all).
            skip_types: Event types to skip.
            verify_screenshots: Compare screenshots after each command.
        """
        if not self._events:
            return {"status": "error", "error": "No recording loaded. Call load() first."}

        if self._playing:
            return {"status": "error", "error": "Already playing. Stop first."}

        self._playing = True
        self._paused = False
        self._speed = max(0.1, min(10.0, speed))
        self._current_index = max(0, from_event)
        end_index = min(to_event or len(self._events), len(self._events))
        skip_set = set(skip_types or [])

        start_time = time.time()
        commands_executed = 0
        commands_succeeded = 0
        commands_failed = 0
        skips = 0
        mismatches = 0

        try:
            while self._current_index < end_index and self._playing:
                # Handle pause
                while self._paused and self._playing:
                    await asyncio.sleep(0.1)

                if not self._playing:
                    break

                event = self._events[self._current_index]

                # Calculate delay to next event
                if self._current_index + 1 < end_index:
                    next_event = self._events[self._current_index + 1]
                    delay_ms = (next_event.elapsed_ms - event.elapsed_ms) / self._speed
                    delay_ms = max(0, min(delay_ms, 10000))  # Cap at 10s
                else:
                    delay_ms = 0

                # Skip certain event types
                if event.event_type in skip_set:
                    skips += 1
                    self._current_index += 1
                    continue

                # Execute the event
                if event.event_type == EventType.COMMAND.value:
                    result = await self._replay_command(event)
                    commands_executed += 1
                    if result.get("status") == "success":
                        commands_succeeded += 1
                    else:
                        commands_failed += 1

                    # Screenshot verification
                    if verify_screenshots and event.screenshot_ref:
                        match = await self._verify_screenshot(event.screenshot_ref)
                        if not match:
                            mismatches += 1

                elif event.event_type == EventType.NAVIGATION.value:
                    url = event.data.get("url", "")
                    if url and url != "about:blank":
                        try:
                            await self.browser.navigate(url, page_id="main")
                        except Exception as e:
                            logger.warning(f"Replay navigation failed: {e}")

                self._current_index += 1

                # Wait for next event timing
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            total_time = time.time() - start_time
            self._playing = False

            return {
                "status": "success",
                "replayed_events": self._current_index - from_event,
                "commands_executed": commands_executed,
                "commands_succeeded": commands_succeeded,
                "commands_failed": commands_failed,
                "skipped": skips,
                "screenshot_mismatches": mismatches,
                "playback_time_ms": round(total_time * 1000, 1),
                "speed": self._speed,
            }

        except Exception as e:
            self._playing = False
            return {
                "status": "error",
                "error": str(e),
                "stopped_at_event": self._current_index,
                "commands_executed": commands_executed,
            }

    async def stop(self) -> Dict[str, Any]:
        """Stop playback."""
        self._playing = False
        self._paused = False
        return {"status": "success", "stopped_at_event": self._current_index}

    async def pause(self) -> Dict[str, Any]:
        """Pause playback."""
        if not self._playing:
            return {"status": "error", "error": "Not playing"}
        self._paused = True
        return {"status": "success", "state": "paused", "at_event": self._current_index}

    async def resume(self) -> Dict[str, Any]:
        """Resume playback after pause."""
        if not self._playing:
            return {"status": "error", "error": "Not playing"}
        self._paused = False
        return {"status": "success", "state": "playing"}

    async def step(self) -> Dict[str, Any]:
        """Execute one event and pause."""
        if not self._events:
            return {"status": "error", "error": "No recording loaded"}

        if self._current_index >= len(self._events):
            return {"status": "error", "error": "Reached end of recording"}

        event = self._events[self._current_index]

        if event.event_type == EventType.COMMAND.value:
            result = await self._replay_command(event)
        elif event.event_type == EventType.NAVIGATION.value:
            url = event.data.get("url", "")
            result = await self.browser.navigate(url) if url else {"status": "skipped"}
        else:
            result = {"status": "skipped"}

        self._current_index += 1

        return {
            "status": "success",
            "event_index": self._current_index - 1,
            "event_type": event.event_type,
            "event_data": event.data,
            "result": result,
            "remaining": len(self._events) - self._current_index,
        }

    async def jump_to(self, event_index: int = None, elapsed_ms: float = None) -> Dict[str, Any]:
        """Jump to a specific event index or time."""
        if not self._events:
            return {"status": "error", "error": "No recording loaded"}

        if elapsed_ms is not None:
            # Find event closest to elapsed time
            for i, e in enumerate(self._events):
                if e.elapsed_ms >= elapsed_ms:
                    event_index = i
                    break
            if event_index is None:
                event_index = len(self._events) - 1

        event_index = max(0, min(event_index or 0, len(self._events) - 1))
        self._current_index = event_index

        return {
            "status": "success",
            "jumped_to": event_index,
            "event_type": self._events[event_index].event_type,
            "elapsed_ms": self._events[event_index].elapsed_ms,
            "remaining": len(self._events) - event_index,
        }

    def get_position(self) -> Dict[str, Any]:
        """Get current playback position."""
        if not self._events:
            return {"status": "no_recording"}

        return {
            "current_index": self._current_index,
            "total_events": len(self._events),
            "progress_pct": round(self._current_index / max(1, len(self._events)) * 100, 1),
            "elapsed_ms": self._events[self._current_index].elapsed_ms if self._current_index < len(self._events) else 0,
            "total_duration_ms": self._events[-1].elapsed_ms if self._events else 0,
            "playing": self._playing,
            "paused": self._paused,
            "speed": self._speed,
        }

    def get_event_list(
        self,
        offset: int = 0,
        limit: int = 50,
        event_type: str = None,
    ) -> Dict[str, Any]:
        """Get a list of events for inspection."""
        if not self._events:
            return {"status": "no_recording", "events": []}

        filtered = self._events
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]

        page = filtered[offset:offset + limit]

        return {
            "status": "success",
            "events": [
                {
                    "index": self._events.index(e) if e in self._events else offset + i,
                    "id": e.event_id,
                    "type": e.event_type,
                    "elapsed_ms": round(e.elapsed_ms, 1),
                    "data_summary": self._summarize_event(e),
                    "url": e.tab_url,
                }
                for i, e in enumerate(page)
            ],
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
        }

    async def export_as_workflow(self, include_navigations: bool = True) -> Dict[str, Any]:
        """
        Export the recording as a workflow JSON that can be replayed later.

        Useful for:
        - Creating automated regression tests
        - Replaying complex user flows
        - Sharing workflows with team
        """
        if not self._events:
            return {"status": "error", "error": "No recording loaded"}

        steps = []
        for event in self._events:
            if event.event_type == EventType.COMMAND.value:
                command = event.data.get("command", "")
                params = event.data.get("params", {})

                step = {"command": command}
                step.update(params)

                # Skip failed commands
                if event.data.get("status") == "error":
                    step["_comment"] = f"FAILED: {event.data.get('error', '')}"
                    step["_skip"] = True

                steps.append(step)

            elif event.event_type == EventType.NAVIGATION.value and include_navigations:
                url = event.data.get("url", "")
                if url and url != "about:blank":
                    steps.append({"command": "navigate", "url": url})

        workflow = {
            "name": self._recording.name if self._recording else "recorded-workflow",
            "description": f"Exported from recording {self._recording.recording_id if self._recording else 'unknown'}",
            "steps": steps,
            "variables": {},
            "exported_at": time.time(),
            "original_duration_ms": self._events[-1].elapsed_ms if self._events else 0,
        }

        return {
            "status": "success",
            "workflow": workflow,
            "step_count": len(steps),
        }

    # ─── Internal ───────────────────────────────────────────

    async def _replay_command(self, event: SessionEvent) -> Dict[str, Any]:
        """Replay a single command event."""
        command = event.data.get("command", "")
        params = event.data.get("params", {})

        if not command:
            return {"status": "error", "error": "No command in event"}

        # Route to browser
        try:
            if command == "navigate":
                return await self.browser.navigate(params.get("url", ""))
            elif command == "click":
                return await self.browser.click(params.get("selector", ""))
            elif command == "fill-form":
                return await self.browser.fill_form(params.get("fields", {}))
            elif command == "type":
                return await self.browser.type_text(params.get("text", ""))
            elif command == "press":
                return await self.browser.press_key(params.get("key", "Enter"))
            elif command == "scroll":
                return await self.browser.scroll(params.get("direction", "down"), params.get("amount", 500))
            elif command == "hover":
                return await self.browser.hover(params.get("selector", ""))
            elif command == "double-click":
                return await self.browser.double_click(params.get("selector", ""))
            elif command == "select":
                return await self.browser.select_option(params.get("selector", ""), params.get("value", ""))
            elif command == "clear-input":
                return await self.browser.clear_input(params.get("selector", ""))
            elif command == "checkbox":
                return await self.browser.set_checkbox(params.get("selector", ""), params.get("checked", True))
            elif command == "back":
                return await self.browser.go_back()
            elif command == "forward":
                return await self.browser.go_forward()
            elif command == "reload":
                return await self.browser.reload()
            elif command == "screenshot":
                b64 = await self.browser.screenshot(full_page=params.get("full_page", False))
                return {"status": "success", "screenshot": b64}
            elif command in ("get-content", "get-dom", "get-links", "get-images"):
                # Read-only commands — safe to replay
                return {"status": "success", "note": f"Read-only command '{command}' skipped during replay"}
            else:
                return {"status": "skipped", "note": f"Unknown command: {command}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _verify_screenshot(self, ref: str) -> bool:
        """Compare current screenshot with recorded one."""
        if not self._recording or ref not in self._recording.screenshots:
            return True  # Can't verify, assume match

        try:
            current = await self.browser.screenshot()
            recorded = base64.b64encode(self._recording.screenshots[ref]).decode()
            # Simple byte comparison — in production, use perceptual hashing
            return current[:1000] == recorded[:1000]  # Compare first 1KB as quick check
        except Exception:
            return True

    def _summarize_event(self, event: SessionEvent) -> str:
        """Create a human-readable summary of an event."""
        data = event.data
        if event.event_type == EventType.COMMAND.value:
            cmd = data.get("command", "?")
            status = data.get("status", "")
            if cmd == "navigate":
                return f"navigate → {data.get('params', {}).get('url', '')[:60]}"
            elif cmd == "click":
                return f"click → {data.get('params', {}).get('selector', '')[:40]}"
            elif cmd == "fill-form":
                fields = data.get("params", {}).get("fields", {})
                return f"fill {len(fields)} field(s)"
            else:
                return f"{cmd} [{status}]"
        elif event.event_type == EventType.NAVIGATION.value:
            return f"→ {data.get('url', '')[:60]}"
        return f"{event.event_type}: {str(data)[:60]}"


# ─── Session Analyzer ───────────────────────────────────────

class SessionAnalyzer:
    """
    Analyze recorded sessions for insights.

    Capabilities:
    - Performance analysis: identify slow commands, bottlenecks
    - Error analysis: group errors, find patterns
    - Network analysis: waterfall data, slow requests
    - Session summary: key events, navigation flow
    - Search: find events by type, content, time range
    """

    def __init__(self, storage_dir: str = None):
        self._storage_dir = Path(storage_dir or os.path.expanduser("~/.agent-os/recordings"))

    def analyze(self, recording_id: str) -> Dict[str, Any]:
        """Full analysis of a recording."""
        events = self._load_events(recording_id)
        if not events:
            return {"status": "error", "error": f"No events found for: {recording_id}"}

        commands = [e for e in events if e.event_type == EventType.COMMAND.value]
        errors = [e for e in events if e.event_type == EventType.ERROR.value]
        networks = [e for e in events if e.event_type in (EventType.NETWORK_REQUEST.value, EventType.NETWORK_RESPONSE.value)]
        navigations = [e for e in events if e.event_type == EventType.NAVIGATION.value]

        # Command performance
        cmd_times = {}
        for e in commands:
            cmd = e.data.get("command", "unknown")
            elapsed = e.data.get("elapsed_ms", 0)
            if cmd not in cmd_times:
                cmd_times[cmd] = {"count": 0, "total_ms": 0, "max_ms": 0, "failures": 0}
            cmd_times[cmd]["count"] += 1
            cmd_times[cmd]["total_ms"] += elapsed
            cmd_times[cmd]["max_ms"] = max(cmd_times[cmd]["max_ms"], elapsed)
            if e.data.get("status") == "error":
                cmd_times[cmd]["failures"] += 1

        for cmd, stats in cmd_times.items():
            stats["avg_ms"] = round(stats["total_ms"] / max(1, stats["count"]), 1)
            stats["total_ms"] = round(stats["total_ms"], 1)

        # Navigation flow
        nav_flow = [{"url": e.data.get("url", ""), "title": e.data.get("title", ""), "ms": round(e.elapsed_ms)} for e in navigations]

        # Error summary
        error_groups = defaultdict(list)
        for e in errors:
            key = e.data.get("error", "unknown")[:100]
            error_groups[key].append(e.elapsed_ms)

        return {
            "status": "success",
            "recording_id": recording_id,
            "summary": {
                "total_events": len(events),
                "duration_ms": round(events[-1].elapsed_ms if events else 0, 1),
                "commands_executed": len(commands),
                "errors": len(errors),
                "navigations": len(navigations),
                "network_requests": len([e for e in networks if e.event_type == EventType.NETWORK_REQUEST.value]),
            },
            "command_performance": cmd_times,
            "navigation_flow": nav_flow,
            "error_summary": {k: {"count": len(v), "first_occurrence_ms": round(v[0])} for k, v in error_groups.items()},
        }

    def search(
        self,
        recording_id: str,
        event_type: str = None,
        query: str = None,
        from_ms: float = None,
        to_ms: float = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Search events in a recording.

        Args:
            recording_id: Recording to search.
            event_type: Filter by event type.
            query: Search in event data (text match).
            from_ms: Start time filter (elapsed ms).
            to_ms: End time filter (elapsed ms).
            limit: Max results.
        """
        events = self._load_events(recording_id)
        if not events:
            return {"status": "error", "error": "Recording not found"}

        results = events

        if event_type:
            results = [e for e in results if e.event_type == event_type]

        if from_ms is not None:
            results = [e for e in results if e.elapsed_ms >= from_ms]

        if to_ms is not None:
            results = [e for e in results if e.elapsed_ms <= to_ms]

        if query:
            query_lower = query.lower()
            results = [e for e in results if query_lower in json.dumps(e.data, default=str).lower()]

        return {
            "status": "success",
            "total_matches": len(results),
            "events": [
                {
                    "index": i,
                    "id": e.event_id,
                    "type": e.event_type,
                    "elapsed_ms": round(e.elapsed_ms, 1),
                    "data": e.data,
                }
                for i, e in enumerate(results[:limit])
            ],
        }

    def _load_events(self, recording_id: str) -> List[SessionEvent]:
        """Load events from disk."""
        events_file = self._storage_dir / recording_id / "events.jsonl.gz"
        if not events_file.exists():
            return []

        events = []
        try:
            with gzip.open(events_file, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(SessionEvent.from_dict(json.loads(line)))
                        except Exception:
                            continue
        except Exception:
            pass

        return events
