"""
Agent-X Tool Registry — Single Source of Truth
================================================
Defines ALL server commands with their parameters, descriptions, and categories.
Used by MCP, OpenAI, and CLI connectors to stay in sync with the server.

Usage:
    from connectors._tool_registry import TOOLS, get_mcp_tools, get_openai_tools, get_cli_commands
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ToolParam:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False

@dataclass
class ToolDef:
    server_cmd: str           # Server command name (e.g., "navigate")
    mcp_name: str             # MCP tool name (e.g., "browser_navigate")
    openai_name: str          # OpenAI function name (e.g., "browser_navigate")
    cli_name: str             # CLI command name (e.g., "navigate")
    description: str          # Tool description
    params: List[ToolParam] = field(default_factory=list)
    category: str = "general"

# ─── All 198 Server Commands ──────────────────────────────────

TOOLS: List[ToolDef] = [
    # ═══════════════════════════════════════════════════════════
    # NAVIGATION
    # ═══════════════════════════════════════════════════════════
    ToolDef("navigate", "browser_navigate", "browser_navigate", "navigate",
        "Navigate to a URL using a real Chromium browser with anti-detection.",
        [ToolParam("url", "string", "The URL to navigate to", True),
         ToolParam("wait_until", "string", "Wait condition: load, domcontentloaded, networkidle")],
        "navigation"),
    ToolDef("smart-navigate", "browser_smart_navigate", "browser_smart_navigate", "smart_navigate",
        "Smart navigate with automatic strategy selection. Tries HTTP first, falls back to browser.",
        [ToolParam("url", "string", "URL to navigate to", True)], "navigation"),
    ToolDef("back", "browser_back", "browser_back", "back",
        "Go back in browser history.", [], "navigation"),
    ToolDef("forward", "browser_forward", "browser_forward", "forward",
        "Go forward in browser history.", [], "navigation"),
    ToolDef("reload", "browser_reload", "browser_reload", "reload",
        "Reload the current page.", [], "navigation"),
    ToolDef("route", "browser_route", "browser_route", "route",
        "Decide whether a query needs web/browser access. USE THIS FIRST before any browser tool.",
        [ToolParam("query", "string", "The user's question or task to analyze", True),
         ToolParam("context", "string", "Optional conversation context")], "router"),
    ToolDef("route-stats", "browser_route_stats", "browser_route_stats", "route_stats",
        "Get query routing statistics.", [], "router"),

    # ═══════════════════════════════════════════════════════════
    # INTERACTION
    # ═══════════════════════════════════════════════════════════
    ToolDef("click", "browser_click", "browser_click", "click",
        "Click an element using CSS selector.",
        [ToolParam("selector", "string", "CSS selector of the element to click", True)], "interaction"),
    ToolDef("double-click", "browser_double_click", "browser_double_click", "double_click",
        "Double-click an element.",
        [ToolParam("selector", "string", "CSS selector", True)], "interaction"),
    ToolDef("right-click", "browser_right_click", "browser_right_click", "right_click",
        "Right-click an element to open context menu.",
        [ToolParam("selector", "string", "CSS selector", True)], "interaction"),
    ToolDef("context-action", "browser_context_action", "browser_context_action", "context_action",
        "Right-click and select a context menu option.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("action_text", "string", "Text of the context menu option", True)], "interaction"),
    ToolDef("hover", "browser_hover", "browser_hover", "hover",
        "Hover over an element.",
        [ToolParam("selector", "string", "CSS selector", True)], "interaction"),
    ToolDef("type", "browser_type", "browser_type", "type",
        "Type text into the currently focused element.",
        [ToolParam("text", "string", "Text to type", True)], "interaction"),
    ToolDef("press", "browser_press", "browser_press", "press",
        "Press a keyboard key.",
        [ToolParam("key", "string", "Key to press (Enter, Tab, Escape, Backspace, etc.)", True)], "interaction"),
    ToolDef("fill-form", "browser_fill_form", "browser_fill_form", "fill_form",
        "Fill multiple form fields at once.",
        [ToolParam("fields", "object", "Dict mapping CSS selectors to values", True)], "interaction"),
    ToolDef("clear-input", "browser_clear_input", "browser_clear_input", "clear_input",
        "Clear an input field.",
        [ToolParam("selector", "string", "CSS selector of the input", True)], "interaction"),
    ToolDef("select", "browser_select", "browser_select", "select",
        "Select a dropdown option.",
        [ToolParam("selector", "string", "CSS selector of the select element", True),
         ToolParam("value", "string", "Value to select", True)], "interaction"),
    ToolDef("upload", "browser_upload", "browser_upload", "upload",
        "Upload a file to a file input.",
        [ToolParam("selector", "string", "CSS selector of the file input", True),
         ToolParam("file_path", "string", "Path to the file to upload", True)], "interaction"),
    ToolDef("checkbox", "browser_checkbox", "browser_checkbox", "checkbox",
        "Set checkbox state.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("checked", "boolean", "Whether to check or uncheck", True)], "interaction"),
    ToolDef("drag-drop", "browser_drag_drop", "browser_drag_drop", "drag_drop",
        "Drag and drop from one element to another.",
        [ToolParam("source", "string", "Source CSS selector", True),
         ToolParam("target", "string", "Target CSS selector", True)], "interaction"),
    ToolDef("drag-offset", "browser_drag_offset", "browser_drag_offset", "drag_offset",
        "Drag an element by pixel offset.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("x", "number", "Horizontal offset in pixels", True),
         ToolParam("y", "number", "Vertical offset in pixels", True)], "interaction"),
    ToolDef("scroll", "browser_scroll", "browser_scroll", "scroll",
        "Scroll the page with human-like behavior.",
        [ToolParam("direction", "string", "Direction: up, down, left, right", True),
         ToolParam("amount", "number", "Scroll amount in pixels")], "interaction"),
    ToolDef("scroll-into-view", "browser_scroll_into_view", "browser_scroll_into_view", "scroll_into_view",
        "Scroll an element into view. Supports @eN refs from snapshot.",
        [ToolParam("selector", "string", "CSS selector or @eN ref of the element", True)], "interaction"),
    ToolDef("wait", "browser_wait", "browser_wait", "wait",
        "Wait for an element to appear.",
        [ToolParam("selector", "string", "CSS selector to wait for", True),
         ToolParam("timeout", "number", "Timeout in seconds")], "interaction"),
    ToolDef("viewport", "browser_viewport", "browser_viewport", "viewport",
        "Change the browser viewport size.",
        [ToolParam("width", "number", "Viewport width in pixels", True),
         ToolParam("height", "number", "Viewport height in pixels", True)], "interaction"),

    # ═══════════════════════════════════════════════════════════
    # SMART FINDER (No CSS Selector Needed)
    # ═══════════════════════════════════════════════════════════
    ToolDef("smart-find", "browser_smart_find", "browser_smart_find", "smart_find",
        "Find an element by visible text, aria-label, placeholder, title, or alt text. No CSS selector needed.",
        [ToolParam("description", "string", "Visible text or description to find", True),
         ToolParam("tag", "string", "Optional tag filter (button, a, input, etc.)"),
         ToolParam("timeout", "number", "Timeout in seconds")], "smart_finder"),
    ToolDef("smart-find-all", "browser_smart_find_all", "browser_smart_find_all", "smart_find_all",
        "Find all elements matching visible text or description.",
        [ToolParam("description", "string", "Text to search for", True)], "smart_finder"),
    ToolDef("smart-click", "browser_smart_click", "browser_smart_click", "smart_click",
        "Click an element by its visible text. No CSS selector needed.",
        [ToolParam("text", "string", "Visible text of the element to click", True),
         ToolParam("tag", "string", "Optional tag filter"),
         ToolParam("timeout", "number", "Timeout in seconds")], "smart_finder"),
    ToolDef("smart-fill", "browser_smart_fill", "browser_smart_fill", "smart_fill",
        "Fill an input by its label or placeholder text. No CSS selector needed.",
        [ToolParam("label", "string", "Label or placeholder text of the input", True),
         ToolParam("value", "string", "Value to fill", True),
         ToolParam("timeout", "number", "Timeout in seconds")], "smart_finder"),

    # ═══════════════════════════════════════════════════════════
    # CONTENT EXTRACTION
    # ═══════════════════════════════════════════════════════════
    ToolDef("get-content", "browser_get_content", "browser_get_content", "get_content",
        "Get the page HTML and extracted text content.", [], "extraction"),
    ToolDef("get-dom", "browser_get_dom", "browser_get_dom", "get_dom",
        "Get a structured DOM snapshot of the page.", [], "extraction"),
    ToolDef("screenshot", "browser_screenshot", "browser_screenshot", "screenshot",
        "Take a screenshot of the current page.",
        [ToolParam("full_page", "boolean", "Capture full page (not just viewport)")], "extraction"),
    ToolDef("get-links", "browser_get_links", "browser_get_links", "get_links",
        "Extract all links from the page.", [], "extraction"),
    ToolDef("get-images", "browser_get_images", "browser_get_images", "get_images",
        "Extract all images from the page.", [], "extraction"),
    ToolDef("get-text", "browser_get_text", "browser_get_text", "get_text",
        "Get text content of a specific element.",
        [ToolParam("selector", "string", "CSS selector", True)], "extraction"),
    ToolDef("get-attr", "browser_get_attr", "browser_get_attr", "get_attr",
        "Get an attribute value from an element.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("attribute", "string", "Attribute name", True)], "extraction"),
    ToolDef("evaluate-js", "browser_evaluate_js", "browser_evaluate_js", "evaluate_js",
        "Execute JavaScript in the page context and return the result.",
        [ToolParam("script", "string", "JavaScript code to execute", True)], "extraction"),
    ToolDef("console-logs", "browser_console_logs", "browser_console_logs", "console_logs",
        "Get browser console logs.",
        [ToolParam("limit", "number", "Maximum number of logs to return")], "extraction"),

    # ═══════════════════════════════════════════════════════════
    # PAGE ANALYSIS
    # ═══════════════════════════════════════════════════════════
    ToolDef("page-summary", "browser_page_summary", "browser_page_summary", "page_summary",
        "Full page analysis: title, headings, content structure, tech stack.", [], "analysis"),
    ToolDef("page-tables", "browser_page_tables", "browser_page_tables", "page_tables",
        "Extract HTML tables as structured data.", [], "analysis"),
    ToolDef("page-seo", "browser_page_seo", "browser_page_seo", "page_seo",
        "SEO audit with score (0-100) and issues.", [], "analysis"),
    ToolDef("page-structured", "browser_page_structured", "browser_page_structured", "page_structured",
        "Extract JSON-LD and Microdata structured data.", [], "analysis"),
    ToolDef("page-emails", "browser_page_emails", "browser_page_emails", "page_emails",
        "Find all email addresses on the page.", [], "analysis"),
    ToolDef("page-phones", "browser_page_phones", "browser_page_phones", "page_phones",
        "Find all phone numbers on the page.", [], "analysis"),
    ToolDef("page-accessibility", "browser_page_accessibility", "browser_page_accessibility", "page_accessibility",
        "Basic accessibility audit.", [], "analysis"),
    ToolDef("analyze", "browser_analyze", "browser_analyze", "analyze",
        "Run comprehensive page analysis.",
        [ToolParam("url", "string", "URL to analyze")], "analysis"),
    ToolDef("analyze-search", "browser_analyze_search", "browser_analyze_search", "analyze_search",
        "Analyze search results for a query.",
        [ToolParam("query", "string", "Search query", True)], "analysis"),

    # ═══════════════════════════════════════════════════════════
    # NETWORK CAPTURE
    # ═══════════════════════════════════════════════════════════
    ToolDef("network-start", "browser_network_start", "browser_network_start", "network_start",
        "Start capturing network requests.",
        [ToolParam("url_pattern", "string", "URL pattern filter"),
         ToolParam("resource_types", "string", "Comma-separated resource types"),
         ToolParam("methods", "string", "HTTP methods filter"),
         ToolParam("capture_body", "boolean", "Capture request/response bodies")], "network"),
    ToolDef("network-stop", "browser_network_stop", "browser_network_stop", "network_stop",
        "Stop capturing and get summary.", [], "network"),
    ToolDef("network-get", "browser_network_get", "browser_network_get", "network_get",
        "Get captured network requests with filters.",
        [ToolParam("url_pattern", "string", "URL pattern filter"),
         ToolParam("resource_type", "string", "Resource type filter"),
         ToolParam("method", "string", "HTTP method filter"),
         ToolParam("status_code", "number", "Status code filter"),
         ToolParam("api_only", "boolean", "Only API requests"),
         ToolParam("limit", "number", "Max results"),
         ToolParam("offset", "number", "Offset for pagination")], "network"),
    ToolDef("network-apis", "browser_network_apis", "browser_network_apis", "network_apis",
        "Discover all API endpoints from captured traffic.", [], "network"),
    ToolDef("network-detail", "browser_network_detail", "browser_network_detail", "network_detail",
        "Get full details of a captured request.",
        [ToolParam("request_id", "string", "Request ID", True)], "network"),
    ToolDef("network-stats", "browser_network_stats", "browser_network_stats", "network_stats",
        "Get capture statistics.", [], "network"),
    ToolDef("network-export", "browser_network_export", "browser_network_export", "network_export",
        "Export captured requests to JSON or HAR.",
        [ToolParam("format", "string", "Export format: json or har"),
         ToolParam("filename", "string", "Output filename")], "network"),
    ToolDef("network-clear", "browser_network_clear", "browser_network_clear", "network_clear",
        "Clear all captured requests.", [], "network"),

    # ═══════════════════════════════════════════════════════════
    # SECURITY SCANNING
    # ═══════════════════════════════════════════════════════════
    ToolDef("scan-xss", "browser_scan_xss", "browser_scan_xss", "scan_xss",
        "Scan a URL for XSS vulnerabilities.",
        [ToolParam("url", "string", "URL to scan", True)], "security"),
    ToolDef("scan-sqli", "browser_scan_sqli", "browser_scan_sqli", "scan_sqli",
        "Scan a URL for SQL injection vulnerabilities.",
        [ToolParam("url", "string", "URL to scan", True)], "security"),
    ToolDef("scan-sensitive", "browser_scan_sensitive", "browser_scan_sensitive", "scan_sensitive",
        "Scan the current page for exposed sensitive data (API keys, tokens, emails).", [], "security"),

    # ═══════════════════════════════════════════════════════════
    # WORKFLOWS
    # ═══════════════════════════════════════════════════════════
    ToolDef("workflow", "browser_workflow", "browser_workflow", "workflow",
        "Execute a multi-step browser workflow.",
        [ToolParam("steps", "array", "List of step objects with command and params", True),
         ToolParam("variables", "object", "Template variables"),
         ToolParam("on_error", "string", "Error handling: abort, continue, retry"),
         ToolParam("retry_count", "number", "Retry count on error"),
         ToolParam("step_delay_ms", "number", "Delay between steps in ms")], "workflow"),
    ToolDef("workflow-save", "browser_workflow_save", "browser_workflow_save", "workflow_save",
        "Save a workflow as a reusable template.",
        [ToolParam("name", "string", "Template name", True),
         ToolParam("steps", "array", "Workflow steps", True),
         ToolParam("variables", "object", "Default variables"),
         ToolParam("description", "string", "Template description")], "workflow"),
    ToolDef("workflow-template", "browser_workflow_template", "browser_workflow_template", "workflow_template",
        "Run a saved workflow template.",
        [ToolParam("template_name", "string", "Template name", True),
         ToolParam("variables", "object", "Override variables")], "workflow"),
    ToolDef("workflow-list", "browser_workflow_list", "browser_workflow_list", "workflow_list",
        "List all saved workflow templates.", [], "workflow"),
    ToolDef("workflow-status", "browser_workflow_status", "browser_workflow_status", "workflow_status",
        "Get status of a running workflow.",
        [ToolParam("workflow_id", "string", "Workflow ID", True)], "workflow"),
    ToolDef("workflow-json", "browser_workflow_json", "browser_workflow_json", "workflow_json",
        "Execute a workflow from a JSON string.",
        [ToolParam("json", "string", "Workflow JSON", True)], "workflow"),

    # ═══════════════════════════════════════════════════════════
    # SESSIONS & AUTH
    # ═══════════════════════════════════════════════════════════
    ToolDef("save-session", "browser_save_session", "browser_save_session", "save_session",
        "Save the full browser state (cookies, localStorage, tabs).",
        [ToolParam("name", "string", "Session name", True)], "session"),
    ToolDef("restore-session", "browser_restore_session", "browser_restore_session", "restore_session",
        "Restore a saved browser session.",
        [ToolParam("name", "string", "Session name", True)], "session"),
    ToolDef("list-sessions", "browser_list_sessions", "browser_list_sessions", "list_sessions",
        "List all saved browser sessions.", [], "session"),
    ToolDef("delete-session", "browser_delete_session", "browser_delete_session", "delete_session",
        "Delete a saved session.",
        [ToolParam("name", "string", "Session name", True)], "session"),
    ToolDef("export-tokens", "browser_export_tokens", "browser_export_tokens", "export_tokens",
        "Export all session/local/auth tokens from the browser.", [], "session"),
    ToolDef("load-tokens", "browser_load_tokens", "browser_load_tokens", "load_tokens",
        "Load/import session/local/auth tokens into the browser.",
        [ToolParam("tokens", "string", "Base64 encoded JSON string containing exported tokens", True)], "session"),
    ToolDef("save-creds", "browser_save_credentials", "browser_save_credentials", "save_creds",
        "Save login credentials (AES-256 encrypted).",
        [ToolParam("domain", "string", "Website domain", True),
         ToolParam("username", "string", "Username or email", True),
         ToolParam("password", "string", "Password", True)], "session"),
    ToolDef("auto-login", "browser_auto_login", "browser_auto_login", "auto_login",
        "Auto-login using saved credentials.",
        [ToolParam("url", "string", "Login URL", True),
         ToolParam("domain", "string", "Website domain")], "session"),
    ToolDef("get-cookies", "browser_get_cookies", "browser_get_cookies", "get_cookies",
        "Get all cookies for the current page.", [], "session"),
    ToolDef("set-cookie", "browser_set_cookie", "browser_set_cookie", "set_cookie",
        "Set a cookie.",
        [ToolParam("name", "string", "Cookie name", True),
         ToolParam("value", "string", "Cookie value", True),
         ToolParam("domain", "string", "Cookie domain"),
         ToolParam("path", "string", "Cookie path"),
         ToolParam("secure", "boolean", "Secure flag")], "session"),

    # ═══════════════════════════════════════════════════════════
    # TABS
    # ═══════════════════════════════════════════════════════════
    ToolDef("tabs", "browser_tabs", "browser_tabs", "tabs",
        "Manage browser tabs (list, new, switch, close).",
        [ToolParam("action", "string", "Action: list, new, switch, close", True),
         ToolParam("tab_id", "string", "Tab ID for switch/close")], "tabs"),
    ToolDef("add-extension", "browser_add_extension", "browser_add_extension", "add_extension",
        "Add a browser extension.",
        [ToolParam("path", "string", "Path to extension directory or .crx file", True)], "tabs"),

    # ═══════════════════════════════════════════════════════════
    # PROXY & DEVICE
    # ═══════════════════════════════════════════════════════════
    ToolDef("set-proxy", "browser_set_proxy", "browser_set_proxy", "set_proxy",
        "Set HTTP/SOCKS5 proxy.",
        [ToolParam("proxy_url", "string", "Proxy URL (http:// or socks5://)", True)], "proxy"),
    ToolDef("get-proxy", "browser_get_proxy", "browser_get_proxy", "get_proxy",
        "Get current proxy configuration.", [], "proxy"),
    ToolDef("emulate-device", "browser_emulate_device", "browser_emulate_device", "emulate_device",
        "Emulate a mobile/tablet/desktop device.",
        [ToolParam("device", "string", "Device preset name (iphone_14, ipad, desktop_1080, etc.)", True)], "device"),
    ToolDef("list-devices", "browser_list_devices", "browser_list_devices", "list_devices",
        "List all available device presets.", [], "device"),

    # ═══════════════════════════════════════════════════════════
    # PROXY ROTATION ENGINE
    # ═══════════════════════════════════════════════════════════
    ToolDef("proxy-add", "browser_proxy_add", "browser_proxy_add", "proxy_add",
        "Add a proxy to the rotation pool.",
        [ToolParam("url", "string", "Proxy URL", True),
         ToolParam("proxy_type", "string", "Type: http, https, socks5"),
         ToolParam("country", "string", "Country code"),
         ToolParam("region", "string", "Region name")], "proxy_rotation"),
    ToolDef("proxy-remove", "browser_proxy_remove", "browser_proxy_remove", "proxy_remove",
        "Remove a proxy from the pool.",
        [ToolParam("proxy_id", "string", "Proxy ID", True)], "proxy_rotation"),
    ToolDef("proxy-list", "browser_proxy_list", "browser_proxy_list", "proxy_list",
        "List all proxies in the pool.",
        [ToolParam("status", "string", "Filter by status: healthy, unhealthy, all")], "proxy_rotation"),
    ToolDef("proxy-check", "browser_proxy_check", "browser_proxy_check", "proxy_check",
        "Check health of a specific proxy.",
        [ToolParam("proxy_id", "string", "Proxy ID", True)], "proxy_rotation"),
    ToolDef("proxy-check-all", "browser_proxy_check_all", "browser_proxy_check_all", "proxy_check_all",
        "Check health of all proxies.", [], "proxy_rotation"),
    ToolDef("proxy-rotate", "browser_proxy_rotate", "browser_proxy_rotate", "proxy_rotate",
        "Rotate to the next healthy proxy.",
        [ToolParam("strategy", "string", "Rotation strategy: round_robin, random, least_used, fastest")], "proxy_rotation"),
    ToolDef("proxy-stats", "browser_proxy_stats", "browser_proxy_stats", "proxy_stats",
        "Get proxy pool statistics.", [], "proxy_rotation"),
    ToolDef("proxy-enable", "browser_proxy_enable", "browser_proxy_enable", "proxy_enable",
        "Enable proxy rotation.", [], "proxy_rotation"),
    ToolDef("proxy-disable", "browser_proxy_disable", "browser_proxy_disable", "proxy_disable",
        "Disable proxy rotation.", [], "proxy_rotation"),
    ToolDef("proxy-strategy", "browser_proxy_strategy", "browser_proxy_strategy", "proxy_strategy",
        "Set the proxy rotation strategy.",
        [ToolParam("strategy", "string", "Strategy: round_robin, random, least_used, fastest", True)], "proxy_rotation"),
    ToolDef("proxy-save", "browser_proxy_save", "browser_proxy_save", "proxy_save",
        "Save proxy pool to file.",
        [ToolParam("filename", "string", "Output filename")], "proxy_rotation"),
    ToolDef("proxy-load", "browser_proxy_load", "browser_proxy_load", "proxy_load",
        "Load proxy pool from file.",
        [ToolParam("filename", "string", "Input filename", True)], "proxy_rotation"),
    ToolDef("proxy-load-file", "browser_proxy_load_file", "browser_proxy_load_file", "proxy_load_file",
        "Load proxies from a text file (one per line).",
        [ToolParam("filepath", "string", "Path to proxy file", True)], "proxy_rotation"),
    ToolDef("proxy-load-api", "browser_proxy_load_api", "browser_proxy_load_api", "proxy_load_api",
        "Load proxies from an API endpoint.",
        [ToolParam("url", "string", "API URL", True),
         ToolParam("api_key", "string", "API key"),
         ToolParam("format", "string", "Response format: json, text")], "proxy_rotation"),
    ToolDef("proxy-record", "browser_proxy_record", "browser_proxy_record", "proxy_record",
        "Record a proxy's performance.",
        [ToolParam("proxy_id", "string", "Proxy ID", True),
         ToolParam("success", "boolean", "Whether the request succeeded", True),
         ToolParam("response_time", "number", "Response time in seconds")], "proxy_rotation"),
    ToolDef("proxy-get", "browser_proxy_get", "browser_proxy_get", "proxy_get",
        "Get current active proxy details.", [], "proxy_rotation"),

    # ═══════════════════════════════════════════════════════════
    # ADAPTIVE SCRAPER — Element fingerprinting + relocation
    # ═══════════════════════════════════════════════════════════
    ToolDef("adaptive-find", "adaptive_find", "adaptive_find", "adaptive_find",
        "Find element adaptively — survives page structure changes. Tries normal selector first, then uses stored fingerprints with similarity scoring to relocate the element.",
        [ToolParam("selector", "string", "CSS or XPath selector", True),
         ToolParam("identifier", "string", "Custom name for this element (defaults to selector)"),
         ToolParam("page_id", "string", "Browser tab ID"),
         ToolParam("auto_save", "boolean", "Save fingerprints automatically (default: true)"),
         ToolParam("threshold", "number", "Minimum similarity score 0-100 (default: 40)")], "adaptive"),
    ToolDef("adaptive-save", "adaptive_save", "adaptive_save", "adaptive_save",
        "Save an element's fingerprint for future adaptive relocation.",
        [ToolParam("selector", "string", "CSS/XPath selector", True),
         ToolParam("identifier", "string", "Name to save under", True),
         ToolParam("page_id", "string", "Browser tab ID")], "adaptive"),
    ToolDef("adaptive-stats", "adaptive_stats", "adaptive_stats", "adaptive_stats",
        "Get adaptive scraper statistics — domains, fingerprints, storage.", [], "adaptive"),
    ToolDef("adaptive-cleanup", "adaptive_cleanup", "adaptive_cleanup", "adaptive_cleanup",
        "Clean up expired fingerprints.",
        [ToolParam("max_age_days", "number", "Max age in days (default: 30)")], "adaptive"),

    # ═══════════════════════════════════════════════════════════
    # DOM SNAPSHOT — Token-Efficient Page Representation
    # ═══════════════════════════════════════════════════════════
    ToolDef("snapshot", "browser_snapshot", "browser_snapshot", "snapshot",
        "Get compact accessibility tree snapshot. Instead of raw HTML (50K+ chars), returns semantic tree (2-5K chars). Use @eN refs to interact with elements. 90%+ token savings.",
        [ToolParam("compact", "boolean", "Remove empty structural elements (default: true)"),
         ToolParam("depth", "number", "Limit tree depth"),
         ToolParam("urls", "boolean", "Include href URLs for links")], "snapshot"),
    ToolDef("snapshot-interactive", "browser_snapshot_interactive", "browser_snapshot_interactive", "snapshot_interactive",
        "Get interactive elements only (buttons, links, inputs). Minimal tokens, all clickable things. Returns @eN refs for click/fill/type commands.",
        [ToolParam("compact", "boolean", "Remove empty structural elements (default: true)"),
         ToolParam("depth", "number", "Limit tree depth")], "snapshot"),
    ToolDef("snapshot-selector", "browser_snapshot_selector", "browser_snapshot_selector", "snapshot_selector",
        "Get snapshot scoped to a CSS selector. Useful for analyzing specific page regions.",
        [ToolParam("selector", "string", "CSS selector to scope to", True),
         ToolParam("compact", "boolean", "Remove empty structural elements (default: true)")], "snapshot"),

    # ═══════════════════════════════════════════════════════════
    # SMART WAIT ENGINE
    # ═══════════════════════════════════════════════════════════
    ToolDef("smart-wait", "browser_smart_wait", "browser_smart_wait", "smart_wait",
        "Intelligent wait with multiple strategies.",
        [ToolParam("selector", "string", "CSS selector to wait for"),
         ToolParam("timeout", "number", "Timeout in seconds"),
         ToolParam("strategy", "string", "Wait strategy: element, network, js, dom, page")], "smart_wait"),
    ToolDef("smart-wait-element", "browser_smart_wait_element", "browser_smart_wait_element", "smart_wait_element",
        "Wait for an element with auto-retry.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("timeout", "number", "Timeout in seconds"),
         ToolParam("state", "string", "State: visible, hidden, attached, detached")], "smart_wait"),
    ToolDef("smart-wait-network", "browser_smart_wait_network", "browser_smart_wait_network", "smart_wait_network",
        "Wait for network to become idle.",
        [ToolParam("timeout", "number", "Timeout in seconds"),
         ToolParam("idle_ms", "number", "Idle time in ms")], "smart_wait"),
    ToolDef("smart-wait-js", "browser_smart_wait_js", "browser_smart_wait_js", "smart_wait_js",
        "Wait for a JavaScript condition to be true.",
        [ToolParam("script", "string", "JavaScript expression that returns true when ready", True),
         ToolParam("timeout", "number", "Timeout in seconds")], "smart_wait"),
    ToolDef("smart-wait-dom", "browser_smart_wait_dom", "browser_smart_wait_dom", "smart_wait_dom",
        "Wait for DOM changes to stop.",
        [ToolParam("timeout", "number", "Timeout in seconds"),
         ToolParam("stable_ms", "number", "Time DOM must be stable in ms")], "smart_wait"),
    ToolDef("smart-wait-page", "browser_smart_wait_page", "browser_smart_wait_page", "smart_wait_page",
        "Wait for full page load with all resources.",
        [ToolParam("timeout", "number", "Timeout in seconds")], "smart_wait"),
    ToolDef("smart-wait-compose", "browser_smart_wait_compose", "browser_smart_wait_compose", "smart_wait_compose",
        "Compose multiple wait conditions (AND/OR logic).",
        [ToolParam("conditions", "array", "List of wait condition objects", True),
         ToolParam("logic", "string", "Logic: and, or")], "smart_wait"),

    # ═══════════════════════════════════════════════════════════
    # AUTO-HEAL ENGINE
    # ═══════════════════════════════════════════════════════════
    ToolDef("heal-click", "browser_heal_click", "browser_heal_click", "heal_click",
        "Click with auto-healing. If selector fails, finds element by nearby text.",
        [ToolParam("selector", "string", "Primary CSS selector", True),
         ToolParam("text_hint", "string", "Nearby visible text for fallback")], "heal"),
    ToolDef("heal-fill", "browser_heal_fill", "browser_heal_fill", "heal_fill",
        "Fill input with auto-healing.",
        [ToolParam("selector", "string", "Primary CSS selector", True),
         ToolParam("value", "string", "Value to fill", True),
         ToolParam("text_hint", "string", "Nearby label text for fallback")], "heal"),
    ToolDef("heal-hover", "browser_heal_hover", "browser_heal_hover", "heal_hover",
        "Hover with auto-healing.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("text_hint", "string", "Nearby text for fallback")], "heal"),
    ToolDef("heal-double-click", "browser_heal_double_click", "browser_heal_double_click", "heal_double_click",
        "Double-click with auto-healing.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("text_hint", "string", "Nearby text for fallback")], "heal"),
    ToolDef("heal-wait", "browser_heal_wait", "browser_heal_wait", "heal_wait",
        "Wait with auto-healing.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("timeout", "number", "Timeout in seconds")], "heal"),
    ToolDef("heal-selector", "browser_heal_selector", "browser_heal_selector", "heal_selector",
        "Get a working selector for an element (tries multiple strategies).",
        [ToolParam("selector", "string", "Original CSS selector", True),
         ToolParam("text_hint", "string", "Nearby text hint")], "heal"),
    ToolDef("heal-stats", "browser_heal_stats", "browser_heal_stats", "heal_stats",
        "Get auto-heal statistics (success rate, fallback usage).", [], "heal"),
    ToolDef("heal-clear", "browser_heal_clear", "browser_heal_clear", "heal_clear",
        "Clear auto-heal cache and statistics.", [], "heal"),
    ToolDef("heal-fingerprint", "browser_heal_fingerprint", "browser_heal_fingerprint", "heal_fingerprint",
        "Generate a fingerprint of the current page for change detection.", [], "heal"),
    ToolDef("heal-fingerprint-page", "browser_heal_fingerprint_page", "browser_heal_fingerprint_page", "heal_fingerprint_page",
        "Check if the page has changed since last fingerprint.", [], "heal"),

    # ═══════════════════════════════════════════════════════════
    # AUTO-RETRY ENGINE
    # ═══════════════════════════════════════════════════════════
    ToolDef("retry-navigate", "browser_retry_navigate", "browser_retry_navigate", "retry_navigate",
        "Navigate with automatic retry on failure.",
        [ToolParam("url", "string", "URL to navigate to", True),
         ToolParam("max_retries", "number", "Maximum retry attempts"),
         ToolParam("retry_delay", "number", "Delay between retries in seconds")], "retry"),
    ToolDef("retry-click", "browser_retry_click", "browser_retry_click", "retry_click",
        "Click with automatic retry on failure.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("max_retries", "number", "Maximum retry attempts")], "retry"),
    ToolDef("retry-fill", "browser_retry_fill", "browser_retry_fill", "retry_fill",
        "Fill form field with automatic retry.",
        [ToolParam("selector", "string", "CSS selector", True),
         ToolParam("value", "string", "Value to fill", True),
         ToolParam("max_retries", "number", "Maximum retry attempts")], "retry"),
    ToolDef("retry-execute", "browser_retry_execute", "browser_retry_execute", "retry_execute",
        "Execute any command with automatic retry.",
        [ToolParam("command", "string", "Command name", True),
         ToolParam("params", "object", "Command parameters"),
         ToolParam("max_retries", "number", "Maximum retry attempts")], "retry"),
    ToolDef("retry-api-call", "browser_retry_api_call", "browser_retry_api_call", "retry_api_call",
        "Make an API call with automatic retry and circuit breaker.",
        [ToolParam("url", "string", "API URL", True),
         ToolParam("method", "string", "HTTP method"),
         ToolParam("headers", "object", "Request headers"),
         ToolParam("body", "string", "Request body")], "retry"),
    ToolDef("retry-stats", "browser_retry_stats", "browser_retry_stats", "retry_stats",
        "Get auto-retry statistics.", [], "retry"),
    ToolDef("retry-health", "browser_retry_health", "browser_retry_health", "retry_health",
        "Get circuit breaker health status.", [], "retry"),
    ToolDef("retry-circuit-breakers", "browser_retry_circuit_breakers", "browser_retry_circuit_breakers", "retry_circuit_breakers",
        "List all circuit breakers and their states.", [], "retry"),
    ToolDef("retry-reset-circuit", "browser_retry_reset_circuit", "browser_retry_reset_circuit", "retry_reset_circuit",
        "Reset a specific circuit breaker.",
        [ToolParam("circuit_name", "string", "Circuit breaker name", True)], "retry"),
    ToolDef("retry-reset-all-circuits", "browser_retry_reset_all_circuits", "browser_retry_reset_all_circuits", "retry_reset_all_circuits",
        "Reset all circuit breakers.", [], "retry"),

    # ═══════════════════════════════════════════════════════════
    # SESSION RECORDING & REPLAY
    # ═══════════════════════════════════════════════════════════
    ToolDef("record-start", "browser_record_start", "browser_record_start", "record_start",
        "Start recording browser actions.",
        [ToolParam("name", "string", "Recording name")], "recording"),
    ToolDef("record-stop", "browser_record_stop", "browser_record_stop", "record_stop",
        "Stop recording and save.", [], "recording"),
    ToolDef("record-pause", "browser_record_pause", "browser_record_pause", "record_pause",
        "Pause recording.", [], "recording"),
    ToolDef("record-resume", "browser_record_resume", "browser_record_resume", "record_resume",
        "Resume paused recording.", [], "recording"),
    ToolDef("record-status", "browser_record_status", "browser_record_status", "record_status",
        "Get recording status.", [], "recording"),
    ToolDef("record-list", "browser_record_list", "browser_record_list", "record_list",
        "List all saved recordings.", [], "recording"),
    ToolDef("record-delete", "browser_record_delete", "browser_record_delete", "record_delete",
        "Delete a recording.",
        [ToolParam("name", "string", "Recording name", True)], "recording"),
    ToolDef("record-annotate", "browser_record_annotate", "browser_record_annotate", "record_annotate",
        "Add an annotation to a recording.",
        [ToolParam("name", "string", "Recording name", True),
         ToolParam("step_index", "number", "Step index", True),
         ToolParam("note", "string", "Annotation text", True)], "recording"),
    ToolDef("replay-play", "browser_replay_play", "browser_replay_play", "replay_play",
        "Play a recorded session.",
        [ToolParam("name", "string", "Recording name", True),
         ToolParam("speed", "number", "Playback speed multiplier")], "replay"),
    ToolDef("replay-stop", "browser_replay_stop", "browser_replay_stop", "replay_stop",
        "Stop playback.", [], "replay"),
    ToolDef("replay-pause", "browser_replay_pause", "browser_replay_pause", "replay_pause",
        "Pause playback.", [], "replay"),
    ToolDef("replay-resume", "browser_replay_resume", "browser_replay_resume", "replay_resume",
        "Resume paused playback.", [], "replay"),
    ToolDef("replay-step", "browser_replay_step", "browser_replay_step", "replay_step",
        "Step forward one action in playback.", [], "replay"),
    ToolDef("replay-jump", "browser_replay_jump", "browser_replay_jump", "replay_jump",
        "Jump to a specific step in playback.",
        [ToolParam("step_index", "number", "Step index", True)], "replay"),
    ToolDef("replay-position", "browser_replay_position", "browser_replay_position", "replay_position",
        "Get current playback position.", [], "replay"),
    ToolDef("replay-events", "browser_replay_events", "browser_replay_events", "replay_events",
        "Get all events from a recording.",
        [ToolParam("name", "string", "Recording name", True)], "replay"),
    ToolDef("replay-load", "browser_replay_load", "browser_replay_load", "replay_load",
        "Load a recording for playback.",
        [ToolParam("name", "string", "Recording name", True)], "replay"),
    ToolDef("replay-export-workflow", "browser_replay_export_workflow", "browser_replay_export_workflow", "replay_export_workflow",
        "Export a recording as a reusable workflow.",
        [ToolParam("name", "string", "Recording name", True)], "replay"),

    # ═══════════════════════════════════════════════════════════
    # MULTI-AGENT HUB
    # ═══════════════════════════════════════════════════════════
    ToolDef("hub-register", "browser_hub_register", "browser_hub_register", "hub_register",
        "Register an agent in the multi-agent hub.",
        [ToolParam("agent_id", "string", "Unique agent ID", True),
         ToolParam("agent_type", "string", "Agent type/role"),
         ToolParam("capabilities", "array", "List of capabilities")], "hub"),
    ToolDef("hub-unregister", "browser_hub_unregister", "browser_hub_unregister", "hub_unregister",
        "Unregister an agent from the hub.",
        [ToolParam("agent_id", "string", "Agent ID", True)], "hub"),
    ToolDef("hub-agents", "browser_hub_agents", "browser_hub_agents", "hub_agents",
        "List all registered agents.", [], "hub"),
    ToolDef("hub-status", "browser_hub_status", "browser_hub_status", "hub_status",
        "Get hub status and agent count.", [], "hub"),
    ToolDef("hub-broadcast", "browser_hub_broadcast", "browser_hub_broadcast", "hub_broadcast",
        "Broadcast a message to all agents.",
        [ToolParam("message", "string", "Message to broadcast", True),
         ToolParam("exclude_self", "boolean", "Exclude sender from broadcast")], "hub"),
    ToolDef("hub-handoff", "browser_hub_handoff", "browser_hub_handoff", "hub_handoff",
        "Hand off browser control to another agent.",
        [ToolParam("target_agent", "string", "Target agent ID", True),
         ToolParam("context", "object", "Context to pass")], "hub"),
    ToolDef("hub-heartbeat", "browser_hub_heartbeat", "browser_hub_heartbeat", "hub_heartbeat",
        "Send heartbeat to keep agent registration alive.", [], "hub"),
    ToolDef("hub-lock", "browser_hub_lock", "browser_hub_lock", "hub_lock",
        "Acquire a distributed lock.",
        [ToolParam("resource", "string", "Resource to lock", True),
         ToolParam("timeout", "number", "Lock timeout in seconds")], "hub"),
    ToolDef("hub-unlock", "browser_hub_unlock", "browser_hub_unlock", "hub_unlock",
        "Release a distributed lock.",
        [ToolParam("resource", "string", "Resource to unlock", True)], "hub"),
    ToolDef("hub-locks", "browser_hub_locks", "browser_hub_locks", "hub_locks",
        "List all active locks.", [], "hub"),
    ToolDef("hub-task-create", "browser_hub_task_create", "browser_hub_task_create", "hub_task_create",
        "Create a task for agents to pick up.",
        [ToolParam("task_type", "string", "Task type", True),
         ToolParam("description", "string", "Task description", True),
         ToolParam("priority", "string", "Priority: low, medium, high, critical"),
         ToolParam("params", "object", "Task parameters")], "hub"),
    ToolDef("hub-task-claim", "browser_hub_task_claim", "browser_hub_task_claim", "hub_task_claim",
        "Claim a task for execution.",
        [ToolParam("task_id", "string", "Task ID", True),
         ToolParam("agent_id", "string", "Agent ID", True)], "hub"),
    ToolDef("hub-task-start", "browser_hub_task_start", "browser_hub_task_start", "hub_task_start",
        "Mark a task as started.",
        [ToolParam("task_id", "string", "Task ID", True)], "hub"),
    ToolDef("hub-task-complete", "browser_hub_task_complete", "browser_hub_task_complete", "hub_task_complete",
        "Mark a task as completed.",
        [ToolParam("task_id", "string", "Task ID", True),
         ToolParam("result", "object", "Task result")], "hub"),
    ToolDef("hub-task-fail", "browser_hub_task_fail", "browser_hub_task_fail", "hub_task_fail",
        "Mark a task as failed.",
        [ToolParam("task_id", "string", "Task ID", True),
         ToolParam("error", "string", "Error message")], "hub"),
    ToolDef("hub-task-cancel", "browser_hub_task_cancel", "browser_hub_task_cancel", "hub_task_cancel",
        "Cancel a pending task.",
        [ToolParam("task_id", "string", "Task ID", True)], "hub"),
    ToolDef("hub-tasks", "browser_hub_tasks", "browser_hub_tasks", "hub_tasks",
        "List all tasks with optional status filter.",
        [ToolParam("status", "string", "Filter by status: pending, claimed, running, completed, failed")], "hub"),
    ToolDef("hub-audit", "browser_hub_audit", "browser_hub_audit", "hub_audit",
        "Get audit log of hub events.",
        [ToolParam("limit", "number", "Max events to return")], "hub"),
    ToolDef("hub-memory-set", "browser_hub_memory_set", "browser_hub_memory_set", "hub_memory_set",
        "Store a value in shared agent memory.",
        [ToolParam("key", "string", "Memory key", True),
         ToolParam("value", "string", "Value to store", True),
         ToolParam("ttl", "number", "Time to live in seconds")], "hub"),
    ToolDef("hub-memory-get", "browser_hub_memory_get", "browser_hub_memory_get", "hub_memory_get",
        "Get a value from shared agent memory.",
        [ToolParam("key", "string", "Memory key", True)], "hub"),
    ToolDef("hub-memory-list", "browser_hub_memory_list", "browser_hub_memory_list", "hub_memory_list",
        "List all keys in shared agent memory.", [], "hub"),
    ToolDef("hub-memory-delete", "browser_hub_memory_delete", "browser_hub_memory_delete", "hub_memory_delete",
        "Delete a key from shared agent memory.",
        [ToolParam("key", "string", "Memory key", True)], "hub"),
    ToolDef("hub-events", "browser_hub_events", "browser_hub_events", "hub_events",
        "Get recent hub events (agent joins, leaves, task changes).",
        [ToolParam("limit", "number", "Max events to return"),
         ToolParam("event_type", "string", "Filter by event type")], "hub"),

    # ═══════════════════════════════════════════════════════════
    # LOGIN HANDOFF
    # ═══════════════════════════════════════════════════════════
    ToolDef("login-handoff-start", "browser_login_handoff_start", "browser_login_handoff_start", "login_handoff_start",
        "Start a login handoff session (for human-in-the-loop login).",
        [ToolParam("url", "string", "Login page URL", True),
         ToolParam("timeout", "number", "Handoff timeout in seconds")], "handoff"),
    ToolDef("login-handoff-status", "browser_login_handoff_status", "browser_login_handoff_status", "login_handoff_status",
        "Check login handoff status.",
        [ToolParam("session_id", "string", "Handoff session ID", True)], "handoff"),
    ToolDef("login-handoff-complete", "browser_login_handoff_complete", "browser_login_handoff_complete", "login_handoff_complete",
        "Complete a login handoff (human has finished logging in).",
        [ToolParam("session_id", "string", "Handoff session ID", True)], "handoff"),
    ToolDef("login-handoff-cancel", "browser_login_handoff_cancel", "browser_login_handoff_cancel", "login_handoff_cancel",
        "Cancel a login handoff.",
        [ToolParam("session_id", "string", "Handoff session ID", True)], "handoff"),
    ToolDef("login-handoff-list", "browser_login_handoff_list", "browser_login_handoff_list", "login_handoff_list",
        "List all active handoff sessions.", [], "handoff"),
    ToolDef("login-handoff-stats", "browser_login_handoff_stats", "browser_login_handoff_stats", "login_handoff_stats",
        "Get handoff statistics.", [], "handoff"),
    ToolDef("login-handoff-history", "browser_login_handoff_history", "browser_login_handoff_history", "login_handoff_history",
        "Get handoff history.",
        [ToolParam("limit", "number", "Max entries to return")], "handoff"),
    ToolDef("detect-login-page", "browser_detect_login_page", "browser_detect_login_page", "detect_login_page",
        "Detect if the current page is a login page and extract form fields.", [], "handoff"),

    # ═══════════════════════════════════════════════════════════
    # TLS HTTP CLIENT
    # ═══════════════════════════════════════════════════════════
    ToolDef("fetch", "browser_fetch", "browser_fetch", "fetch",
        "Fetch a URL using Chrome-impersonating HTTP client (no browser). Fast, bypasses TLS fingerprinting.",
        [ToolParam("url", "string", "URL to fetch", True)], "http"),
    ToolDef("tls-get", "browser_tls_get", "browser_tls_get", "tls_get",
        "Make a TLS-impersonated GET request.",
        [ToolParam("url", "string", "URL", True),
         ToolParam("headers", "object", "Additional headers")], "http"),
    ToolDef("tls-post", "browser_tls_post", "browser_tls_post", "tls_post",
        "Make a TLS-impersonated POST request.",
        [ToolParam("url", "string", "URL", True),
         ToolParam("body", "string", "Request body"),
         ToolParam("headers", "object", "Additional headers"),
         ToolParam("content_type", "string", "Content type")], "http"),
    ToolDef("tls-stats", "browser_tls_stats", "browser_tls_stats", "tls_stats",
        "Get TLS client statistics.", [], "http"),

    # ═══════════════════════════════════════════════════════════
    # LLM PROVIDER
    # ═══════════════════════════════════════════════════════════
    ToolDef("llm-complete", "browser_llm_complete", "browser_llm_complete", "llm_complete",
        "Generate text completion using configured LLM provider.",
        [ToolParam("prompt", "string", "Completion prompt", True),
         ToolParam("max_tokens", "number", "Max tokens to generate"),
         ToolParam("temperature", "number", "Temperature (0-2)")], "llm"),
    ToolDef("llm-summarize", "browser_llm_summarize", "browser_llm_summarize", "llm_summarize",
        "Summarize text or page content using LLM.",
        [ToolParam("text", "string", "Text to summarize"),
         ToolParam("url", "string", "URL to fetch and summarize"),
         ToolParam("max_length", "number", "Max summary length in words")], "llm"),
    ToolDef("llm-classify", "browser_llm_classify", "browser_llm_classify", "llm_classify",
        "Classify text into categories using LLM.",
        [ToolParam("text", "string", "Text to classify", True),
         ToolParam("categories", "array", "List of category names", True)], "llm"),
    ToolDef("llm-extract", "browser_llm_extract", "browser_llm_extract", "llm_extract",
        "Extract structured data from text using LLM.",
        [ToolParam("text", "string", "Text to extract from", True),
         ToolParam("schema", "object", "JSON schema for extraction", True)], "llm"),
    ToolDef("llm-provider-set", "browser_llm_provider_set", "browser_llm_provider_set", "llm_provider_set",
        "Configure the LLM provider.",
        [ToolParam("provider", "string", "Provider name (openai, anthropic, etc.)", True),
         ToolParam("api_key", "string", "API key"),
         ToolParam("model", "string", "Model name"),
         ToolParam("base_url", "string", "API base URL")], "llm"),
    ToolDef("llm-token-usage", "browser_llm_token_usage", "browser_llm_token_usage", "llm_token_usage",
        "Get LLM token usage statistics.", [], "llm"),
    ToolDef("llm-cache-clear", "browser_llm_cache_clear", "browser_llm_cache_clear", "llm_cache_clear",
        "Clear LLM response cache.", [], "llm"),

    # ═══════════════════════════════════════════════════════════
    # AI CONTENT EXTRACTION
    # ═══════════════════════════════════════════════════════════
    ToolDef("ai-content", "browser_ai_content", "browser_ai_content", "ai_content",
        "AI-powered content extraction with structured output (forms, schema.org, metadata).", [], "ai"),
    ToolDef("fill-job", "browser_fill_job", "browser_fill_job", "fill_job",
        "Fill a job application form using AI.",
        [ToolParam("data", "object", "Job application data (name, email, resume, etc.)", True)], "ai"),
    ToolDef("structured-extract", "browser_structured_extract", "browser_structured_extract", "structured_extract",
        "Extract structured data from page using AI.",
        [ToolParam("schema", "object", "Expected data schema", True)], "ai"),
    ToolDef("structured-format", "browser_structured_format", "browser_structured_format", "structured_format",
        "Format extracted data into a specific structure.",
        [ToolParam("data", "object", "Data to format", True),
         ToolParam("format", "string", "Output format: json, csv, markdown, table")], "ai"),
    ToolDef("structured-schema", "browser_structured_schema", "browser_structured_schema", "structured_schema",
        "Auto-detect the schema of structured data on the page.", [], "ai"),
    ToolDef("structured-deduplicate", "browser_structured_deduplicate", "browser_structured_deduplicate", "structured_deduplicate",
        "Remove duplicate entries from extracted data.",
        [ToolParam("data", "array", "List of data items", True),
         ToolParam("key_fields", "array", "Fields to use for deduplication")], "ai"),

    # ═══════════════════════════════════════════════════════════
    # CAPTCHA SYSTEM
    # ═══════════════════════════════════════════════════════════
    ToolDef("captcha-assess", "browser_captcha_assess", "browser_captcha_assess", "captcha_assess",
        "Assess if a CAPTCHA is present on the current page.", [], "captcha"),
    ToolDef("captcha-preflight", "browser_captcha_preflight", "browser_captcha_preflight", "captcha_preflight",
        "Pre-flight check for CAPTCHA before navigation.",
        [ToolParam("url", "string", "URL to check", True)], "captcha"),
    ToolDef("captcha-health", "browser_captcha_health", "browser_captcha_health", "captcha_health",
        "Get CAPTCHA bypass system health.", [], "captcha"),
    ToolDef("captcha-monitor-start", "browser_captcha_monitor_start", "browser_captcha_monitor_start", "captcha_monitor_start",
        "Start monitoring for CAPTCHAs during browsing.", [], "captcha"),
    ToolDef("captcha-monitor-stop", "browser_captcha_monitor_stop", "browser_captcha_monitor_stop", "captcha_monitor_stop",
        "Stop CAPTCHA monitoring.", [], "captcha"),
    ToolDef("captcha-shutdown", "browser_captcha_shutdown", "browser_captcha_shutdown", "captcha_shutdown",
        "Shut down CAPTCHA bypass system.", [], "captcha"),

    # ═══════════════════════════════════════════════════════════
    # WEB QUERY ROUTER
    # ═══════════════════════════════════════════════════════════
    ToolDef("classify-query", "browser_classify_query", "browser_classify_query", "classify_query",
        "Classify a query: does it need web access, calculation, code, knowledge, or security?",
        [ToolParam("query", "string", "Query to classify", True)], "router"),
    ToolDef("needs-web", "browser_needs_web", "browser_needs_web", "needs_web",
        "Quick yes/no: does this query need browser access?",
        [ToolParam("query", "string", "Query to check", True)], "router"),
    ToolDef("query-strategy", "browser_query_strategy", "browser_query_strategy", "query_strategy",
        "Get recommended strategy for handling a query.",
        [ToolParam("query", "string", "Query to analyze", True)], "router"),
    ToolDef("router-stats", "browser_router_stats", "browser_router_stats", "router_stats",
        "Get query router classification statistics.", [], "router"),

    # ═══════════════════════════════════════════════════════════
    # NAVIGATION STATS
    # ═══════════════════════════════════════════════════════════
    ToolDef("nav-stats", "browser_nav_stats", "browser_nav_stats", "nav_stats",
        "Get navigation statistics (success rate, avg response time).", [], "stats"),

    # ═══════════════════════════════════════════════════════════
    # TRANSCRIPTION
    # ═══════════════════════════════════════════════════════════
    ToolDef("transcribe", "browser_transcribe", "browser_transcribe", "transcribe",
        "Transcribe audio/video from a URL using Whisper.",
        [ToolParam("url", "string", "URL of audio/video to transcribe", True),
         ToolParam("language", "string", "Language code (en, es, fr, etc.)")], "media"),

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════
    ToolDef("health", "browser_status", "browser_status", "status",
        "Check server health, uptime, active sessions, and browser state.", [], "status"),
]


def get_tool_by_server_cmd(cmd: str) -> Optional[ToolDef]:
    """Get tool definition by server command name."""
    for t in TOOLS:
        if t.server_cmd == cmd:
            return t
    return None

def get_tools_by_category(category: str) -> List[ToolDef]:
    """Get all tools in a category."""
    return [t for t in TOOLS if t.category == category]

def get_all_server_commands() -> List[str]:
    """Get all server command names."""
    return [t.server_cmd for t in TOOLS]

def get_mcp_tools() -> List[Dict[str, Any]]:
    """Get tool definitions in MCP format."""
    tools = []
    for t in TOOLS:
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
            "name": t.mcp_name,
            "description": t.description,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
            }
        })
    return tools

def get_openai_tools() -> List[Dict[str, Any]]:
    """Get tool definitions in OpenAI function-calling format."""
    tools = []
    for t in TOOLS:
        props = {}
        required = []
        for p in t.params:
            prop = {"type": p.type if p.type != "array" else "array", "description": p.description}
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

def get_command_map() -> Dict[str, tuple]:
    """Get mapping of MCP tool names to (server_cmd, param_keys)."""
    mapping = {}
    for t in TOOLS:
        param_keys = [p.name for p in t.params]
        mapping[t.mcp_name] = (t.server_cmd, param_keys)
    return mapping

def get_cli_commands() -> List[Dict[str, str]]:
    """Get CLI command definitions."""
    return [{"cli": t.cli_name, "server": t.server_cmd, "desc": t.description} for t in TOOLS]


# ─── Validation ────────────────────────────────────────────────

def _validate_tool_names():
    """Validate that all MCP tool names are unique at module load time."""
    names = [t.mcp_name for t in TOOLS]
    duplicates = [n for n in names if names.count(n) > 1]
    if duplicates:
        raise ValueError(f"Duplicate MCP tool names: {set(duplicates)}")

_validate_tool_names()
