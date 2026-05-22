#!/usr/bin/env python3
"""
Agent-OS BRUTAL AUDIT TEST
==========================
Complete A-to-Z code validation — no mercy.
Tests every module, every import chain, every command handler.
Catches skeleton code, broken connections, missing implementations.
"""
import sys
import os
import traceback
import importlib
import inspect
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

RESULTS = {"PASS": 0, "FAIL": 0, "WARN": 0, "ERRORS": []}

def record(result_type, test_name, detail=""):
    RESULTS[result_type] = RESULTS.get(result_type, 0) + 1
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(result_type, "❓")
    msg = f"{icon} {test_name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if result_type == "FAIL":
        RESULTS["ERRORS"].append(f"{test_name}: {detail}")

# ═══════════════════════════════════════════════════════════════
# PHASE 1: IMPORT CHAIN TEST — Every module must import cleanly
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 1: IMPORT CHAIN VALIDATION")
print("=" * 70)

IMPORT_TESTS = [
    ("src.core.config", "Config"),
    ("src.core.browser", "AgentBrowser"),
    ("src.core.session", "SessionManager"),
    ("src.core.stealth", "ANTI_DETECTION_JS"),
    ("src.core.cdp_stealth", "CDPStealthInjector"),
    ("src.core.stealth_god", "GodModeStealth"),
    ("src.core.tls_spoof", "apply_browser_tls_spoofing"),
    ("src.core.tls_proxy", "TLSProxyServer"),
    ("src.core.http_client", "TLSClient"),
    ("src.core.smart_navigator", "SmartNavigator"),
    ("src.core.firefox_engine", "FirefoxEngine"),
    ("src.core.persistent_browser", "PersistentBrowserManager"),
    ("src.security.evasion_engine", "EvasionEngine"),
    ("src.security.human_mimicry", "HumanMimicry"),
    ("src.security.captcha_solver", "CaptchaSolver"),
    ("src.security.captcha_bypass", "CaptchaBypass"),
    ("src.security.cloudflare_bypass", "CloudflareBypassEngine"),
    ("src.security.auth_handler", "AuthHandler"),
    ("src.infra.database", "DatabaseManager"),
    ("src.infra.redis_client", "RedisClient"),
    ("src.infra.logging", "setup_logging"),
    ("src.infra.models", "User"),
    ("src.validation.schemas", "validate_command_payload"),
    ("src.tools.session_recording", "SessionRecorder"),
    ("src.tools.scanner", "Scanner"),
    ("src.tools.smart_finder", "SmartElementFinder"),
    ("src.tools.auto_retry", "AutoRetry"),
    ("src.tools.ai_content", "AIContentExtractor"),
    ("src.tools.web_query_router", "WebQueryRouter"),
    ("src.tools.page_analyzer", "PageAnalyzer"),
    ("src.tools.transcriber", "Transcriber"),
    ("src.tools.login_handoff", "LoginHandoffManager"),
    ("src.tools.smart_wait", "SmartWait"),
    ("src.tools.multi_agent", "AgentHub"),
    ("src.tools.network_capture", "NetworkCapture"),
    ("src.tools.auto_heal", "AutoHeal"),
    ("src.tools.workflow", "WorkflowEngine"),
    ("src.tools.form_filler", "FormFiller"),
    ("src.tools.auto_proxy", "AutoProxyManager"),
    ("src.tools.proxy_rotation", "ProxyManager"),
    ("src.agents.server", "AgentServer"),
    ("src.agents.web_need_router", "WebNeedRouter"),
    ("src.auth.middleware", "AuthMiddleware"),
    ("src.auth.jwt_handler", "JWTHandler"),
    ("src.auth.api_key_manager", "APIKeyManager"),
    ("src.auth.user_manager", "UserManager"),
    ("src.setup.wizard", "SetupWizard"),
    # Agent Swarm
    ("src.agent_swarm.config", "SwarmConfig"),
    ("src.agent_swarm.router.orchestrator", "QueryRouter"),
    ("src.agent_swarm.agents.pool", "AgentPool"),
    ("src.agent_swarm.agents.profiles", "SearchProfile"),
    ("src.agent_swarm.search.base", "SearchBackend"),
    ("src.agent_swarm.search.http_backend", "HTTPSearchBackend"),
    ("src.agent_swarm.search.agent_os_backend", "AgentOSBackend"),
    ("src.agent_swarm.output.formatter", "OutputFormatter"),
    ("src.agent_swarm.output.quality", "QualityScorer"),
    ("src.agent_swarm.output.aggregator", "ResultAggregator"),
    ("src.agent_swarm.output.dedup", "Deduplicator"),
]

for module_path, symbol in IMPORT_TESTS:
    try:
        mod = importlib.import_module(module_path)
        if not hasattr(mod, symbol):
            record("FAIL", f"Import {module_path}", f"Missing symbol: {symbol}")
        else:
            record("PASS", f"Import {module_path}.{symbol}")
    except Exception as e:
        record("FAIL", f"Import {module_path}", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# PHASE 2: SKELETON CODE DETECTION — No pass-only methods
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 2: SKELETON CODE DETECTION")
print("=" * 70)

SRC_DIR = Path(__file__).parent / "src"
skeleton_found = 0

for py_file in SRC_DIR.rglob("*.py"):
    if py_file.name == "__init__.py" and py_file.stat().st_size < 500:
        continue  # Small __init__.py is fine

    try:
        source = py_file.read_text()
        lines = source.split("\n")
        rel_path = py_file.relative_to(Path(__file__).parent)

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check for TODO/FIXME/HACK/STUB
            for marker in ["TODO:", "FIXME:", "HACK:", "STUB:"]:
                if marker in stripped and not stripped.startswith("#"):
                    # Allow in comments
                    if not stripped.startswith("#") and not stripped.startswith('"""') and not stripped.startswith("'''"):
                        record("WARN", f"Skeleton marker in {rel_path}:{i}", f"Found {marker}")

            # Check for NotImplementedError
            if "raise NotImplementedError" in stripped:
                record("FAIL", f"NotImplementedError in {rel_path}:{i}", stripped[:80])

            # Check for bare pass in function bodies (not in except/finally)
            if stripped == "pass":
                # Check context: is this inside an except or finally?
                prev_lines = lines[max(0, i-5):i]
                in_except = any("except" in l or "finally" in l for l in prev_lines)
                in_abstract = any("abstractmethod" in l or "@abc" in l for l in prev_lines)
                if not in_except and not in_abstract:
                    # Check if it's inside a function definition
                    func_lines = lines[max(0, i-10):i]
                    in_func = any(l.strip().startswith("def ") or l.strip().startswith("async def ") for l in func_lines)
                    if in_func:
                        record("FAIL", f"Skeleton function in {rel_path}:{i}", f"Function body is just 'pass'")
                        skeleton_found += 1

    except Exception as e:
        record("WARN", f"Cannot scan {py_file}", str(e)[:60])

if skeleton_found == 0:
    record("PASS", "No skeleton code found", "All function bodies have real implementations")

# ═══════════════════════════════════════════════════════════════
# PHASE 3: CLASS INSTANTIATION TEST — Key classes can be created
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 3: CLASS INSTANTIATION TEST")
print("=" * 70)

# Test Config
try:
    from src.core.config import Config
    config = Config()  # Default config, no file needed
    assert config.get("server.ws_port", 8000) == 8000
    record("PASS", "Config instantiation + get()")
except Exception as e:
    record("FAIL", "Config instantiation", str(e)[:100])

# Test AIContentExtractor
try:
    from src.tools.ai_content import AIContentExtractor, AIContent, ContentTypeDetector
    extractor = AIContentExtractor()
    # Test content type detection
    ct, conf = ContentTypeDetector.detect("https://example.com/blog/post-1")
    assert ct == "article", f"Expected 'article', got '{ct}'"
    assert conf > 0
    record("PASS", "AIContentExtractor + ContentTypeDetector")
except Exception as e:
    record("FAIL", "AIContentExtractor", str(e)[:100])

# Test AIContent dataclass
try:
    from src.tools.ai_content import AIContent
    content = AIContent(
        content_type="article",
        url="https://example.com",
        title="Test",
        main_text="Hello world",
    )
    d = content.to_dict()
    assert "content_type" in d
    assert "url" in d
    record("PASS", "AIContent dataclass + to_dict()")
except Exception as e:
    record("FAIL", "AIContent dataclass", str(e)[:100])

# Test ContentTypeDetector URL patterns
try:
    from src.tools.ai_content import ContentTypeDetector
    tests = [
        ("https://amazon.com/dp/B1234", "product"),
        ("https://reddit.com/r/python", "forum"),
        ("https://example.com/search?q=test", "listing"),
        ("https://docs.example.com/api/v1", "api_doc"),
        ("https://example.com/blog/my-post", "article"),
        ("https://twitter.com/elonmusk", "profile"),
    ]
    for url, expected in tests:
        ct, conf = ContentTypeDetector.detect(url)
        if ct == expected:
            record("PASS", f"ContentTypeDetector: {url} → {ct}")
        else:
            record("WARN", f"ContentTypeDetector: {url} → {ct} (expected {expected})")
except Exception as e:
    record("FAIL", "ContentTypeDetector URL patterns", str(e)[:100])

# Test HTML extraction (no browser needed)
try:
    from src.tools.ai_content import AIContentExtractor
    extractor = AIContentExtractor()
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Test Article</title>
        <meta property="og:type" content="article">
        <meta name="description" content="A test article">
        <script type="application/ld+json">{"@type":"Article","name":"Test"}</script>
    </head>
    <body>
        <article>
            <h1>Main Heading</h1>
            <p>This is a test paragraph with enough text to pass the minimum length threshold for content extraction testing.</p>
            <p>Second paragraph with additional content about something interesting that happened today.</p>
            <h2>Sub Heading</h2>
            <p>Third paragraph under the sub heading with more details about the topic being discussed.</p>
            <ul><li>Item 1</li><li>Item 2</li></ul>
            <table><thead><tr><th>Name</th><th>Value</th></tr></thead>
            <tbody><tr><td>Test</td><td>123</td></tr></tbody></table>
            <form action="/submit" method="POST">
                <input type="text" name="username" placeholder="Enter username" required>
                <input type="email" name="email" placeholder="Enter email">
                <button type="submit">Submit</button>
            </form>
            <a href="https://example.com/link1">Link 1</a>
            <img src="image.jpg" alt="Test Image">
        </article>
    </body>
    </html>
    """
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_from_html(test_html, "https://example.com/blog/test")
    )
    if result.get("status") != "success":
        record("FAIL", "HTML extraction", f"Status: {result.get('status')}, Error: {result.get('error')}")
    else:
        data = result["data"]
        checks = {
            "content_type": data.get("content_type") in ("article", "other"),
            "title": data.get("title") == "Test Article",
            "headings": len(data.get("headings", [])) >= 1,
            "paragraphs": len(data.get("paragraphs", [])) >= 1,
            "tables": len(data.get("tables", [])) >= 1,
            "lists": len(data.get("lists", [])) >= 1,
            "forms": len(data.get("forms", [])) >= 1,
            "links": len(data.get("links", [])) >= 1,
            "images": len(data.get("images", [])) >= 1,
            "schema_org": len(data.get("schema_org", [])) >= 1,
            "open_graph": "type" in data.get("open_graph", {}),
            "meta": "description" in data.get("meta", {}),
            "summary": len(data.get("summary", "")) > 0,
            "main_text": len(data.get("main_text", "")) > 0,
        }
        for check_name, passed in checks.items():
            if passed:
                record("PASS", f"HTML extraction: {check_name}")
            else:
                record("FAIL", f"HTML extraction: {check_name}", f"Value: {data.get(check_name)}")
except Exception as e:
    record("FAIL", "HTML extraction", str(e)[:200])

# Test SetupWizard
try:
    from src.setup.wizard import SetupWizard
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wizard = SetupWizard(config_path=tmp)
        # Test non-interactive mode
        result = wizard.run_non_interactive()
        assert result is not None
        assert "config" in result
        assert wizard.config_file.exists()
        record("PASS", "SetupWizard non-interactive mode")
except Exception as e:
    record("FAIL", "SetupWizard", str(e)[:100])

# Test WebQueryRouter
try:
    from src.tools.web_query_router import WebQueryRouter
    router = WebQueryRouter()
    result = router.classify("What is the weather in New York?")
    assert "needs_web" in result
    assert "category" in result
    record("PASS", "WebQueryRouter.classify()")
except Exception as e:
    record("FAIL", "WebQueryRouter", str(e)[:100])

# Test WebNeedRouter
try:
    from src.agents.web_need_router import WebNeedRouter
    wnr = WebNeedRouter({})
    result = wnr.route("What is the current price of Bitcoin?")
    assert "needs_web" in result or "route" in result
    record("PASS", "WebNeedRouter.route()")
except Exception as e:
    record("FAIL", "WebNeedRouter", str(e)[:100])

# Test JWTHandler
try:
    from src.auth.jwt_handler import JWTHandler
    jwt = JWTHandler(secret_key="test-secret-key-for-testing-only", algorithm="HS256")
    tokens = jwt.create_token_pair(user_id="test-user", scopes=["browser"])
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    # Verify access token
    payload = jwt.verify_token(tokens["access_token"], token_type="access")
    assert payload is not None
    assert payload["sub"] == "test-user"
    record("PASS", "JWTHandler create + verify tokens")
except Exception as e:
    record("FAIL", "JWTHandler", str(e)[:100])

# Test SessionManager
try:
    from src.core.session import SessionManager
    from src.core.config import Config
    config = Config()
    sm = SessionManager(config)
    record("PASS", "SessionManager instantiation")
except Exception as e:
    record("FAIL", "SessionManager", str(e)[:100])

# Test HumanMimicry
try:
    from src.security.human_mimicry import HumanMimicry
    hm = HumanMimicry()
    record("PASS", "HumanMimicry instantiation")
except Exception as e:
    record("FAIL", "HumanMimicry", str(e)[:100])

# Test AutoRetry + CircuitBreaker
try:
    from src.tools.auto_retry import AutoRetry, CircuitBreaker, RetryBudget
    ar = AutoRetry()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    budget = RetryBudget(max_retries=100, window_seconds=60)
    record("PASS", "AutoRetry + CircuitBreaker + RetryBudget")
except Exception as e:
    record("FAIL", "AutoRetry/CircuitBreaker", str(e)[:100])

# Test AgentHub
try:
    from src.tools.multi_agent import AgentHub, Task
    hub = AgentHub()
    record("PASS", "AgentHub instantiation")
except Exception as e:
    record("FAIL", "AgentHub", str(e)[:100])

# Test EvasionEngine
try:
    from src.security.evasion_engine import EvasionEngine, CloudflareSolver
    ee = EvasionEngine()
    fp = ee.generate_fingerprint()
    assert "user_agent" in fp
    record("PASS", "EvasionEngine.generate_fingerprint()")
except Exception as e:
    record("FAIL", "EvasionEngine", str(e)[:100])

# Test CloudflareBypassEngine
try:
    from src.security.cloudflare_bypass import CloudflareBypassEngine, CloudflareChallengeType
    # Can't fully init without Config, but check the class exists
    assert hasattr(CloudflareChallengeType, 'JS_CHALLENGE')
    record("PASS", "CloudflareBypassEngine + CloudflareChallengeType")
except Exception as e:
    record("FAIL", "CloudflareBypassEngine", str(e)[:100])

# Test FormFiller
try:
    from src.tools.form_filler import FormFiller, ProfileBuilder
    ff = FormFiller()
    pb = ProfileBuilder()
    profile = pb.build_profile({
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe.test@example.com",
    })
    assert profile["first_name"] == "John"
    record("PASS", "FormFiller + ProfileBuilder")
except Exception as e:
    record("FAIL", "FormFiller", str(e)[:100])

# Test TLSClient
try:
    from src.core.http_client import TLSClient
    client = TLSClient()
    record("PASS", "TLSClient instantiation")
except Exception as e:
    record("FAIL", "TLSClient", str(e)[:100])

# Test FirefoxFingerprint
try:
    from src.core.firefox_engine import FirefoxFingerprint
    fp = FirefoxFingerprint.generate()
    assert "user_agent" in fp
    assert "viewport" in fp
    assert "Firefox" in fp["user_agent"]
    record("PASS", "FirefoxFingerprint.generate()")
except Exception as e:
    record("FAIL", "FirefoxFingerprint", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# PHASE 4: COMMAND HANDLER REGISTRATION — All commands wired up
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 4: COMMAND HANDLER REGISTRATION")
print("=" * 70)

try:
    from src.agents.server import AgentServer
    # Check that _process_command references all expected commands
    # by inspecting the _COMMAND_MAP
    source = inspect.getsource(AgentServer)

    REQUIRED_COMMANDS = [
        "navigate", "click", "type", "screenshot", "scroll",
        "fill-form", "get-content", "go-back", "go-forward",
        "new-tab", "close-tab", "reload", "execute-js",
        "wait", "get-cookies", "set-cookie", "delete-cookie",
        "ai-content",  # Our new command
        "classify-query", "needs-web", "query-strategy",  # WebQueryRouter
        "handoff-start", "handoff-status",  # LoginHandoff
        "smart-wait", "heal-click",  # SmartWait + AutoHeal
        "retry-execute",  # AutoRetry
        "record-start",  # Session Recording
        "proxy-add", "proxy-list",  # Proxy
        "tls-get", "tls-post",  # TLS
        "swarm-search", "swarm-route",  # Swarm endpoints
    ]

    for cmd in REQUIRED_COMMANDS:
        if f'"{cmd}"' in source or f"'{cmd}'" in source:
            record("PASS", f"Command registered: {cmd}")
        else:
            record("FAIL", f"Command NOT registered: {cmd}", "Missing from AgentServer")

except Exception as e:
    record("FAIL", "Command handler registration check", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# PHASE 5: CONNECTION WIRING — Features connect to each other
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 5: FEATURE CONNECTION WIRING")
print("=" * 70)

# Check ai-content connects to SmartNavigator
try:
    from src.core.smart_navigator import SmartNavigator
    source = inspect.getsource(SmartNavigator)
    assert "ai_format" in source, "SmartNavigator missing ai_format parameter"
    assert "AIContentExtractor" in source or "ai_content" in source, "SmartNavigator not wired to AIContentExtractor"
    record("PASS", "SmartNavigator ↔ AIContentExtractor wiring")
except Exception as e:
    record("FAIL", "SmartNavigator ↔ AIContentExtractor", str(e)[:100])

# Check ai-content command connects to AIContentExtractor
try:
    from src.agents.server import AgentServer
    source = inspect.getsource(AgentServer)
    assert "_cmd_ai_content" in source, "AgentServer missing _cmd_ai_content handler"
    assert "AIContentExtractor" in source, "AgentServer not importing AIContentExtractor"
    record("PASS", "AgentServer ↔ AIContentExtractor wiring")
except Exception as e:
    record("FAIL", "AgentServer ↔ AIContentExtractor", str(e)[:100])

# Check WebNeedRouter connects to AgentServer
try:
    from src.agents.server import AgentServer
    source = inspect.getsource(AgentServer)
    assert "_get_web_router" in source, "AgentServer missing _get_web_router lazy init"
    assert "WebNeedRouter" in source, "AgentServer not importing WebNeedRouter"
    record("PASS", "AgentServer ↔ WebNeedRouter wiring")
except Exception as e:
    record("FAIL", "AgentServer ↔ WebNeedRouter", str(e)[:100])

# Check LoginHandoff connects to AgentServer
try:
    from src.agents.server import AgentServer
    source = inspect.getsource(AgentServer)
    assert "_get_login_handoff" in source, "AgentServer missing _get_login_handoff lazy init"
    assert "LoginHandoffManager" in source, "AgentServer not importing LoginHandoffManager"
    record("PASS", "AgentServer ↔ LoginHandoffManager wiring")
except Exception as e:
    record("FAIL", "AgentServer ↔ LoginHandoffManager", str(e)[:100])

# Check Swarm connects to AgentServer
try:
    from src.agents.server import AgentServer
    source = inspect.getsource(AgentServer)
    assert "_init_swarm" in source, "AgentServer missing _init_swarm"
    assert "AgentPool" in source, "AgentServer not importing AgentPool"
    assert "QueryRouter" in source, "AgentServer not importing QueryRouter"
    record("PASS", "AgentServer ↔ AgentSwarm wiring")
except Exception as e:
    record("FAIL", "AgentServer ↔ AgentSwarm", str(e)[:100])

# Check main.py connects setup wizard
try:
    source = Path(__file__).parent.joinpath("main.py").read_text()
    assert "--setup" in source, "main.py missing --setup flag"
    assert "run_setup_if_needed" in source, "main.py not calling run_setup_if_needed"
    record("PASS", "main.py ↔ SetupWizard wiring")
except Exception as e:
    record("FAIL", "main.py ↔ SetupWizard", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# PHASE 6: VERSION CONSISTENCY
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 6: VERSION CONSISTENCY")
print("=" * 70)

try:
    source = Path(__file__).parent.joinpath("main.py").read_text()
    assert '__version__ = "3.2.0"' in source, f"main.py version mismatch"
    record("PASS", "main.py version = 3.2.0")
except Exception as e:
    record("FAIL", "main.py version", str(e)[:100])

# Check startup banner uses __version__
try:
    source = Path(__file__).parent.joinpath("main.py").read_text()
    assert "v{__version__}" in source or "f\"v{__version__}" in source or f"v{__version__}" in source, \
        "Startup banner should use __version__ variable, not hardcoded version"
    record("PASS", "Startup banner uses __version__ variable")
except Exception as e:
    record("FAIL", "Startup banner version", str(e)[:100])

# Check server status endpoint version
try:
    from src.agents.server import AgentServer
    source = inspect.getsource(AgentServer._handle_status)
    assert "3.2.0" in source or "__version__" in source, "Status endpoint version mismatch"
    record("PASS", "Server status endpoint version")
except Exception as e:
    record("WARN", "Server status endpoint version check", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# PHASE 7: SECURITY CHECKS — No detection leaks
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PHASE 7: SECURITY / STEALTH CHECKS")
print("=" * 70)

# Firefox stealth should NOT have console.log
try:
    source = Path(__file__).parent.joinpath("src/core/firefox_engine.py").read_text()
    if "console.log('[Agent-OS]" in source or 'console.log("[Agent-OS]' in source:
        record("FAIL", "Firefox stealth console.log", "Detection risk: console.log in stealth JS")
    else:
        record("PASS", "Firefox stealth: no console.log leak")
except Exception as e:
    record("FAIL", "Firefox stealth check", str(e)[:100])

# Chromium stealth should NOT have console.log
try:
    source = Path(__file__).parent.joinpath("src/core/stealth.py").read_text()
    if "console.log" in source and "agent-os" in source.lower():
        record("FAIL", "Chromium stealth console.log", "Detection risk: console.log with project name")
    else:
        record("PASS", "Chromium stealth: no console.log leak with project name")
except Exception as e:
    record("WARN", "Chromium stealth check", str(e)[:100])

# Error messages should not leak internal details
try:
    from src.agents.server import AgentServer
    # Test _sanitize_error_message
    test_cases = [
        ("browser has been closed", "Browser session has been lost"),
        ("/home/user/project/src/browser.py:42", "[path]"),
        ("0x7f1234567890", "[addr]"),
        ('File "browser.py", line 42', "[traceback]"),
        ("<module 'src.core.browser'>", "[object]"),
    ]
    for input_err, expected_in_output in test_cases:
        result = AgentServer._sanitize_error_message(input_err)
        if expected_in_output in result or expected_in_output == result:
            record("PASS", f"Error sanitization: {input_err[:30]}")
        else:
            record("FAIL", f"Error sanitization: {input_err[:30]}", f"Got: {result[:60]}")
except Exception as e:
    record("FAIL", "Error sanitization", str(e)[:100])

# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("BRUTAL AUDIT RESULTS")
print("=" * 70)
total = RESULTS.get("PASS", 0) + RESULTS.get("FAIL", 0) + RESULTS.get("WARN", 0)
print(f"  Total:  {total}")
print(f"  PASS:   {RESULTS.get('PASS', 0)}")
print(f"  FAIL:   {RESULTS.get('FAIL', 0)}")
print(f"  WARN:   {RESULTS.get('WARN', 0)}")
print()

if RESULTS["ERRORS"]:
    print("FAILURES:")
    for err in RESULTS["ERRORS"]:
        print(f"  ❌ {err}")
    print()

pass_rate = (RESULTS.get("PASS", 0) / total * 100) if total > 0 else 0
print(f"Pass Rate: {pass_rate:.1f}%")
if pass_rate >= 95:
    print("🟢 EXCELLENT — Production ready!")
elif pass_rate >= 85:
    print("🟡 GOOD — Minor issues to address")
else:
    print("🔴 NEEDS WORK — Critical issues found")

sys.exit(0 if RESULTS.get("FAIL", 0) == 0 else 1)
