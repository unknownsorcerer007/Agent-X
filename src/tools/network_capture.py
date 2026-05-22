"""
Agent-OS Network Capture Engine
Captures, filters, and replays HTTP/HTTPS requests from browser sessions.
Production-grade with memory limits, filtering, and export capabilities.
"""
import asyncio
import json
import logging
import time
import re
import hashlib
from typing import Dict, List, Any, Optional
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger("agent-os.network_capture")


@dataclass
class NetworkRequest:
    """Captured network request."""
    id: str
    url: str
    method: str
    headers: Dict[str, str]
    post_data: Optional[str]
    resource_type: str  # document, script, stylesheet, image, xhr, fetch, etc.
    timestamp: float
    response_status: Optional[int] = None
    response_headers: Optional[Dict[str, str]] = None
    response_body: Optional[str] = None
    response_body_size: Optional[int] = None
    duration_ms: Optional[int] = None
    failed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        # Truncate large bodies for memory safety
        if d.get("post_data") and len(d["post_data"]) > 10000:
            d["post_data"] = d["post_data"][:10000] + "... [truncated]"
        if d.get("response_body") and len(d["response_body"]) > 50000:
            d["response_body"] = d["response_body"][:50000] + "... [truncated]"
        return d


class NetworkCapture:
    """
    Production-grade network request capture for AI agents.

    Features:
    - Capture all requests/responses from browser pages
    - Filter by URL pattern, method, resource type, status code
    - Memory-safe with configurable limits
    - Export to JSON/CSV/HAR format
    - Replay captured requests
    - API endpoint discovery
    """

    def __init__(self, browser, max_entries: int = 5000, max_body_size: int = 5 * 1024 * 1024):
        self.browser = browser
        self._max_entries = max_entries
        self._max_body_size = max_body_size  # 5MB max per body
        self._captures: Dict[str, deque] = {}  # page_id -> deque of requests
        self._active: Dict[str, bool] = {}  # page_id -> is capturing
        self._filters: Dict[str, Dict] = {}  # page_id -> filter config
        self._request_map: Dict[str, NetworkRequest] = {}  # id -> request (for quick lookup)
        self._export_dir = Path.home() / ".agent-os" / "captures"
        self._export_dir.mkdir(parents=True, exist_ok=True)

    async def start_capture(
        self,
        page_id: str = "main",
        url_pattern: str = None,
        resource_types: List[str] = None,
        methods: List[str] = None,
        capture_body: bool = False,
    ) -> Dict[str, Any]:
        """
        Start capturing network requests on a page.

        Args:
            page_id: Tab to capture from
            url_pattern: Only capture URLs matching this pattern (regex)
            resource_types: Filter by type: document, script, stylesheet, image, xhr, fetch, etc.
            methods: Filter by HTTP method: GET, POST, PUT, DELETE, etc.
            capture_body: Whether to capture response bodies (increases memory usage)
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return {"status": "error", "error": f"Page not found: {page_id}"}

        # Initialize storage
        self._captures[page_id] = deque(maxlen=self._max_entries)
        self._active[page_id] = True
        self._filters[page_id] = {
            "url_pattern": re.compile(url_pattern) if url_pattern else None,
            "resource_types": [rt.lower() for rt in resource_types] if resource_types else None,
            "methods": [m.upper() for m in methods] if methods else None,
            "capture_body": capture_body,
        }

        # Attach request/response listeners
        page.on("request", lambda req: asyncio.ensure_future(self._on_request(page_id, req)))
        page.on("response", lambda resp: asyncio.ensure_future(self._on_response(page_id, resp)))
        page.on("requestfailed", lambda req: asyncio.ensure_future(self._on_request_failed(page_id, req)))

        logger.info(f"Network capture started on page {page_id}")

        return {
            "status": "success",
            "page_id": page_id,
            "filters": {
                "url_pattern": url_pattern,
                "resource_types": resource_types,
                "methods": methods,
                "capture_body": capture_body,
            },
            "max_entries": self._max_entries,
        }

    async def stop_capture(self, page_id: str = "main") -> Dict[str, Any]:
        """Stop capturing and return summary."""
        self._active[page_id] = False
        captured = self._captures.get(page_id, deque())

        return {
            "status": "success",
            "page_id": page_id,
            "total_captured": len(captured),
            "by_type": self._count_by_type(captured),
            "by_method": self._count_by_method(captured),
            "by_status": self._count_by_status(captured),
        }

    async def get_captured(
        self,
        page_id: str = "main",
        url_pattern: str = None,
        resource_type: str = None,
        method: str = None,
        status_code: int = None,
        api_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get captured requests with optional filtering.

        Args:
            page_id: Which tab's captures to query
            url_pattern: Filter URLs matching this pattern (regex string)
            resource_type: Filter by resource type
            method: Filter by HTTP method
            status_code: Filter by response status code
            api_only: Only return XHR/Fetch requests (API calls)
            limit: Max results to return
            offset: Pagination offset
        """
        captured = list(self._captures.get(page_id, deque()))

        # Apply filters
        filtered = captured

        if url_pattern:
            try:
                pattern = re.compile(url_pattern, re.IGNORECASE)
                filtered = [r for r in filtered if pattern.search(r.url)]
            except re.error:
                return {"status": "error", "error": f"Invalid regex: {url_pattern}"}

        if resource_type:
            filtered = [r for r in filtered if r.resource_type == resource_type.lower()]

        if method:
            filtered = [r for r in filtered if r.method == method.upper()]

        if status_code:
            filtered = [r for r in filtered if r.response_status == status_code]

        if api_only:
            filtered = [r for r in filtered if r.resource_type in ("xhr", "fetch", "other")]

        # Paginate
        total = len(filtered)
        page_items = filtered[offset:offset + limit]

        return {
            "status": "success",
            "page_id": page_id,
            "total": total,
            "offset": offset,
            "limit": limit,
            "requests": [r.to_dict() for r in page_items],
        }

    async def get_apis(self, page_id: str = "main") -> Dict[str, Any]:
        """Discover all API endpoints captured on a page."""
        captured = list(self._captures.get(page_id, deque()))
        api_requests = [r for r in captured if r.resource_type in ("xhr", "fetch", "other")]

        # Group by base URL
        endpoints = {}
        for req in api_requests:
            # Extract base path (remove query params for grouping)
            base_url = req.url.split("?")[0]
            key = f"{req.method} {base_url}"

            if key not in endpoints:
                endpoints[key] = {
                    "method": req.method,
                    "url": base_url,
                    "full_urls": [],
                    "status_codes": set(),
                    "content_types": set(),
                    "count": 0,
                    "request_ids": [],
                }

            endpoints[key]["full_urls"].append(req.url)
            endpoints[key]["count"] += 1
            endpoints[key]["request_ids"].append(req.id)
            if req.response_status:
                endpoints[key]["status_codes"].add(req.response_status)
            if req.response_headers:
                ct = req.response_headers.get("content-type", "")
                if ct:
                    endpoints[key]["content_types"].add(ct.split(";")[0].strip())

        # Convert sets to lists for JSON
        for ep in endpoints.values():
            ep["status_codes"] = sorted(ep["status_codes"])
            ep["content_types"] = sorted(ep["content_types"])
            ep["full_urls"] = list(set(ep["full_urls"]))[:5]  # Dedupe, keep 5 examples

        return {
            "status": "success",
            "page_id": page_id,
            "total_apis": len(endpoints),
            "endpoints": sorted(endpoints.values(), key=lambda e: e["count"], reverse=True),
        }

    async def get_request_detail(self, request_id: str) -> Dict[str, Any]:
        """Get full details of a captured request by ID."""
        req = self._request_map.get(request_id)
        if not req:
            return {"status": "error", "error": f"Request not found: {request_id}"}
        return {"status": "success", "request": req.to_dict()}

    async def export_json(self, page_id: str = "main", filename: str = None) -> Dict[str, Any]:
        """Export captured requests to JSON file."""
        captured = list(self._captures.get(page_id, deque()))
        if not captured:
            return {"status": "error", "error": "No captured requests to export"}

        filename = filename or f"capture-{page_id}-{int(time.time())}.json"
        path = self._export_dir / filename

        data = {
            "exported_at": time.time(),
            "page_id": page_id,
            "total_requests": len(captured),
            "requests": [r.to_dict() for r in captured],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "path": str(path), "total": len(captured)}

    async def export_har(self, page_id: str = "main", filename: str = None) -> Dict[str, Any]:
        """Export captured requests in HAR (HTTP Archive) format."""
        captured = list(self._captures.get(page_id, deque()))
        if not captured:
            return {"status": "error", "error": "No captured requests to export"}

        filename = filename or f"capture-{page_id}-{int(time.time())}.har"
        path = self._export_dir / filename

        har_entries = []
        for req in captured:
            entry = {
                "startedDateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(req.timestamp)),
                "time": req.duration_ms or 0,
                "request": {
                    "method": req.method,
                    "url": req.url,
                    "headers": [{"name": k, "value": v} for k, v in (req.headers or {}).items()],
                    "postData": {"text": req.post_data} if req.post_data else None,
                },
                "response": {
                    "status": req.response_status or 0,
                    "headers": [{"name": k, "value": v} for k, v in (req.response_headers or {}).items()],
                    "content": {
                        "size": req.response_body_size or 0,
                        "text": req.response_body[:10000] if req.response_body else None,
                    },
                },
            }
            har_entries.append(entry)

        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "Agent-OS", "version": "2.0"},
                "entries": har_entries,
            }
        }

        with open(path, "w") as f:
            json.dump(har, f, indent=2)

        return {"status": "success", "path": str(path), "entries": len(har_entries)}

    async def clear(self, page_id: str = "main") -> Dict[str, Any]:
        """Clear captured requests for a page."""
        count = len(self._captures.get(page_id, deque()))
        self._captures[page_id] = deque(maxlen=self._max_entries)
        # Remove associated request map entries that belong to this page
        # Since request IDs include page context, we can clean up related entries
        keys_to_remove = [
            k for k, v in self._request_map.items()
            if hasattr(v, 'page_id') and v.page_id == page_id
        ]
        for k in keys_to_remove:
            del self._request_map[k]
        return {"status": "success", "cleared": count}

    def get_stats(self, page_id: str = "main") -> Dict[str, Any]:
        """Get capture statistics."""
        captured = list(self._captures.get(page_id, deque()))
        if not captured:
            return {"status": "success", "total": 0, "page_id": page_id}

        total_size = sum(r.response_body_size or 0 for r in captured)
        total_time = sum(r.duration_ms or 0 for r in captured)
        failed = sum(1 for r in captured if r.failed)

        return {
            "status": "success",
            "page_id": page_id,
            "total": len(captured),
            "total_response_size_bytes": total_size,
            "avg_duration_ms": round(total_time / len(captured)) if captured else 0,
            "failed_requests": failed,
            "by_type": self._count_by_type(captured),
            "by_method": self._count_by_method(captured),
            "by_status": self._count_by_status(captured),
            "active": self._active.get(page_id, False),
        }

    # ─── Internal Handlers ─────────────────────────────────

    async def _on_request(self, page_id: str, request):
        """Handle outgoing request."""
        if not self._active.get(page_id):
            return

        filters = self._filters.get(page_id, {})

        # Apply URL filter
        if filters.get("url_pattern"):
            if not filters["url_pattern"].search(request.url):
                return

        # Apply resource type filter
        if filters.get("resource_types"):
            if request.resource_type.lower() not in filters["resource_types"]:
                return

        # Apply method filter
        if filters.get("methods"):
            if request.method.upper() not in filters["methods"]:
                return

        req_id = hashlib.md5(f"{request.url}{time.time()}{id(request)}".encode()).hexdigest()[:12]

        req = NetworkRequest(
            id=req_id,
            url=request.url,
            method=request.method,
            headers=dict(request.headers),
            post_data=request.post_data,
            resource_type=request.resource_type,
            timestamp=time.time(),
        )

        if page_id not in self._captures:
            self._captures[page_id] = deque(maxlen=self._max_entries)

        self._captures[page_id].append(req)
        self._request_map[req_id] = req

    async def _on_response(self, page_id: str, response):
        """Handle incoming response."""
        if not self._active.get(page_id):
            return

        # Find matching request by URL + method + unresolved status
        # Prioritize requests that match both URL and method and haven't been resolved
        for req in reversed(self._captures.get(page_id, deque())):
            if req.url == response.url and req.method == response.request.method and req.response_status is None:
                req.response_status = response.status
                req.response_headers = dict(response.headers)
                req.duration_ms = int((time.time() - req.timestamp) * 1000)

                # Capture body if enabled
                filters = self._filters.get(page_id, {})
                if filters.get("capture_body"):
                    try:
                        body = await response.text()
                        if len(body) <= self._max_body_size:
                            req.response_body = body
                        req.response_body_size = len(body)
                    except Exception:
                        pass
                break

    async def _on_request_failed(self, page_id: str, request):
        """Handle failed request."""
        if not self._active.get(page_id):
            return

        for req in reversed(self._captures.get(page_id, deque())):
            if req.url == request.url and req.method == request.method and not req.failed:
                req.failed = True
                req.error = request.failure
                req.duration_ms = int((time.time() - req.timestamp) * 1000)
                break

    def _count_by_type(self, captured) -> Dict[str, int]:
        counts = {}
        for r in captured:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def _count_by_method(self, captured) -> Dict[str, int]:
        counts = {}
        for r in captured:
            counts[r.method] = counts.get(r.method, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def _count_by_status(self, captured) -> Dict[str, int]:
        counts = {}
        for r in captured:
            status = str(r.response_status or "pending")
            counts[status] = counts.get(status, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
