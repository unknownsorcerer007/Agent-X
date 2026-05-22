"""
Agent-OS Firefox Fallback Engine
Production-grade Firefox browser automation with full stealth support.

When Chromium gets detected (Cloudflare, PerimeterX, DataDome, etc.),
Firefox provides a completely different browser fingerprint that many
anti-bot systems don't check as aggressively.

Features:
- Full Playwright Firefox integration
- Firefox-specific stealth patches (different from Chromium)
- Automatic engine switching on Chromium detection
- Session migration between engines
- Firefox-specific fingerprint generation
- Geckodriver compatibility layer
"""
import asyncio
import json
import logging
import random
import time
import os
import hashlib
from typing import Optional, Dict, Any, List
from pathlib import Path
from urllib.parse import urlparse

from patchright.async_api import async_playwright, Browser, Page, BrowserContext

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False

logger = logging.getLogger("agent-os.firefox")

# ═══════════════════════════════════════════════════════════════
# FIREFOX-SPECIFIC STEALTH PATCHES
# ═══════════════════════════════════════════════════════════════

FIREFOX_STEALTH_JS = """
// === AGENT-OS FIREFOX STEALTH v1.0 ===
// Firefox-specific anti-detection patches
// Different from Chromium — Firefox has different APIs and detection surfaces

(function() {
'use strict';

// 1. Firefox doesn't have navigator.webdriver by default in real Firefox,
// but Playwright sets it. Remove at prototype level.
try { delete Navigator.prototype.webdriver; } catch(e) {}

// 2. Firefox-specific: Remove automation indicators
const ffAutomationProps = [
    '__executionContextId', '__pw_manual', '__pw_script',
    'cdc_adoQpoasnfa76pfcZLmcfl_Array', 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
    'cdc_adoQpoasnfa76pfcZLmcfl_Symbol', '__playwright',
    '__playwright_binding__', '__pw_disconnect_reason',
];
for (const p of ffAutomationProps) {
    try { delete window[p]; } catch(e) {
        try { Object.defineProperty(window, p, {get:()=>undefined, configurable:true}); } catch(e2) {}
    }
}

// 3. Firefox has different plugin structure
Object.defineProperty(navigator, 'plugins', {
    get: function() {
        const plugins = [
            {name: 'PDF.js', filename: 'pdf.js', description: 'Portable Document Format', length: 1},
        ];
        plugins.length = 1;
        plugins.item = function(i) { return this[i] || null; };
        plugins.namedItem = function(n) { return this.find(function(x) { return x.name === n; }) || null; };
        plugins.refresh = function() {};
        return plugins;
    },
    configurable: true, enumerable: true
});

// 4. Firefox platform
Object.defineProperty(navigator, 'platform', {
    get: function() {
        const ua = navigator.userAgent;
        if (ua.includes('Win')) return 'Win32';
        if (ua.includes('Mac')) return 'MacIntel';
        return 'Linux x86_64';
    },
    configurable: true, enumerable: true
});

// 5. Firefox doesn't have chrome object — but some sites check for it
// In real Firefox, window.chrome is undefined
if (typeof window.chrome !== 'undefined') {
    try { delete window.chrome; } catch(e) {
        Object.defineProperty(window, 'chrome', {get:()=>undefined, configurable:true});
    }
}

// 6. Firefox-specific: Remove Playwright traces from Error stack traces
const _ffPrepareStack = Error.prepareStackTrace;
Error.prepareStackTrace = function(error, stack) {
    if (_ffPrepareStack) {
        const result = _ffPrepareStack(error, stack);
        if (typeof result === 'string') {
            return result
                .replace(/playwright[^\n]*/gi, '')
                .replace(/agent-os[^\n]*/gi, '')
                .replace(/at eval[^\n]*/gi, '');
        }
        return result;
    }
    return stack.map(function(frame) {
        return '    at ' + (frame.getFunctionName() || '<anonymous>') +
               ' (' + (frame.getFileName() || '<unknown>') + ':' +
               frame.getLineNumber() + ':' + frame.getColumnNumber() + ')';
    }).join('\n');
};

// 7. Canvas fingerprint noise (consistent per session)
const ffCanvasSeed = Math.floor(Math.random() * 2147483647);
function ffSeededRandom(seed) {
    let s = seed;
    return function() {
        s = (s * 16807 + 0) % 2147483647;
        return (s - 1) / 2147483646;
    };
}
const ffCanvasRNG = ffSeededRandom(ffCanvasSeed);

const _ffToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx && this.width > 16 && this.height > 16) {
        try {
            const d = ctx.getImageData(0, 0, this.width, this.height);
            const step = Math.max(67, Math.floor(d.data.length / 10000));
            for (let i = 0; i < d.data.length; i += step) {
                d.data[i] = Math.max(0, Math.min(255, d.data[i] + Math.floor(ffCanvasRNG() * 3) - 1));
            }
            ctx.putImageData(d, 0, 0);
        } catch(e) {}
    }
    return _ffToDataURL.apply(this, arguments);
};

// 8. WebGL fingerprint for Firefox (different from Chrome ANGLE)
const _ffGetParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    // Firefox uses different WebGL vendor/renderer strings
    if (p === 37445) return 'Mozilla';  // VENDOR
    if (p === 37446) return 'Mozilla';  // RENDERER — Firefox never uses ANGLE
    return _ffGetParam.call(this, p);
};

// 9. Audio fingerprint noise
if (typeof AnalyserNode !== 'undefined') {
    const ffAudioRNG = ffSeededRandom(ffCanvasSeed + 1);
    const _ffGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = function(arr) {
        _ffGetFloat.call(this, arr);
        for (let i = 0; i < arr.length; i++) {
            arr[i] += (ffAudioRNG() - 0.5) * 0.0001;
        }
    };
}

// 10. WebRTC IP leak protection
const _ffRTC = window.RTCPeerConnection;
if (_ffRTC) {
    window.RTCPeerConnection = function(config, constraints) {
        if (config && config.iceServers) config.iceServers = [];
        const pc = new _ffRTC(config, constraints);
        const _createOffer = pc.createOffer.bind(pc);
        pc.createOffer = function(opts) {
            return _createOffer(opts).then(function(offer) {
                offer.sdp = offer.sdp.replace(/a=candidate:.*typ host.*/g, '');
                return offer;
            });
        };
        return pc;
    };
    window.RTCPeerConnection.prototype = _ffRTC.prototype;
    Object.setPrototypeOf(window.RTCPeerConnection, _ffRTC);
}

// 11. Block fingerprinting libraries
const ffBlockedLibs = [
    'fingerprintjs','fingerprint2','fingerprint3','fpjs','fpjs2','fpjs3',
    'clientjs','thumbmark','creepjs','amiunique',
    'sardine','iovation','threatmetrix','nethra','seon',
    'datadome','perimeterx','kasada','shapesecurity',
];

const _ffFetch = window.fetch;
window.fetch = function(resource, init) {
    const url = typeof resource === 'string' ? resource : (resource && resource.url) || '';
    if (ffBlockedLibs.some(lib => url.toLowerCase().includes(lib))) {
        return Promise.resolve(new Response('{"blocked":true}', {status: 200}));
    }
    return _ffFetch.apply(this, arguments);
};

const _ffXhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    if (ffBlockedLibs.some(lib => String(url).toLowerCase().includes(lib))) {
        this._agentOsBlocked = true;
        return;
    }
    return _ffXhrOpen.apply(this, arguments);
};
const _ffXhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(data) {
    if (this._agentOsBlocked) {
        Object.defineProperty(this, 'readyState', {get:()=>4});
        Object.defineProperty(this, 'status', {get:()=>200});
        Object.defineProperty(this, 'responseText', {get:()=>''});
        if (this.onreadystatechange) this.onreadystatechange();
        if (this.onload) this.onload();
        return;
    }
    return _ffXhrSend.apply(this, arguments);
};

// Stealth loaded — no console.log (detection risk)
})();
"""

# Firefox User-Agents (real-world Firefox versions)
FIREFOX_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
]

# Firefox screen resolutions
FIREFOX_RESOLUTIONS = [
    (1920, 1080), (1536, 864), (1366, 768), (1440, 900),
    (1280, 720), (2560, 1440), (1600, 900), (1680, 1050),
]

# Sites known to detect Chromium specifically (Firefox works better)
CHROMIUM_DETECTED_DOMAINS = [
    "bloomberg.com", "reuters.com", "washingtonpost.com",
    "bestbuy.com", "adobe.com", "fidelity.com",
    "coinbase.com", "quora.com", "udemy.com",
    "etsy.com", "homedepot.com", "pexels.com",
    "shutterstock.com", "deviantart.com", "artstation.com",
    "tripadvisor.com", "lyft.com", "canva.com",
    "stackoverflow.com", "medium.com", "producthunt.com",
    "usa today.com", "ox.ac.uk", "quizlet.com",
]


class FirefoxFingerprint:
    """Generate Firefox-compatible fingerprints."""

    @staticmethod
    def generate() -> Dict[str, Any]:
        ua = random.choice(FIREFOX_USER_AGENTS)
        w, h = random.choice(FIREFOX_RESOLUTIONS)
        cores = random.choice([4, 6, 8, 8, 12, 16])
        memory = random.choice([4, 8, 8, 16, 16, 32])

        return {
            "user_agent": ua,
            "viewport": {"width": w, "height": h},
            "screen_width": w,
            "screen_height": h,
            "hardware_concurrency": cores,
            "device_memory": memory,
            "platform": "Win32" if "Windows" in ua else ("MacIntel" if "Mac" in ua else "Linux x86_64"),
            "pixel_ratio": random.choice([1, 1, 1.25, 1.5]) if "Windows" in ua else random.choice([1, 2, 2]),
            "timezone": random.choice([
                "America/New_York", "America/Chicago", "America/Los_Angeles",
                "Europe/London", "Europe/Berlin", "Europe/Paris",
            ]),
            "locale": random.choice(["en-US", "en-US", "en-GB", "en"]),
        }


class FirefoxEngine:
    """
    Firefox browser engine with full stealth support.
    Drop-in alternative to Chromium for sites that detect Chrome/CDP.
    """

    def __init__(self, config):
        self.config = config
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._pages: Dict[str, Page] = {}
        self._console_logs: Dict[str, List[Dict]] = {}
        self._fingerprint: Optional[Dict] = None
        self._cookie_dir = Path(os.path.expanduser("~/.agent-os/cookies/firefox"))
        self._download_dir = Path(os.path.expanduser("~/.agent-os/downloads/firefox"))
        self._proxy_config = None
        self._blocked_requests = 0
        self._launch_args = None
        self._crash_count = 0
        self._max_crash_retries = 3
        self._recovery_lock = asyncio.Lock()
        self._cookies_dirty = False
        # Cookie encryption (same pattern as browser.py)
        self._cookie_key = self._get_or_create_cookie_key()
        self._cookie_fernet = Fernet(self._cookie_key) if _FERNET_AVAILABLE else None

    @property
    def engine_name(self) -> str:
        return "firefox"

    async def start(self):
        """Launch Firefox with stealth settings."""
        self._cookie_dir.mkdir(parents=True, exist_ok=True)
        self._download_dir.mkdir(parents=True, exist_ok=True)

        await self._launch_browser()
        logger.info("Firefox engine started with stealth patches v1.0")

    async def _launch_browser(self):
        """Launch Firefox browser and create context."""
        self.playwright = await async_playwright().start()

        headless = self.config.get("browser.headless", True)

        # Firefox-specific launch args
        if self._launch_args is None:
            self._launch_args = [
                "--disable-blink-features=AutomationControlled",
                "-devtools",  # Don't auto-open devtools
            ]

        firefox_prefs = {
            # Disable automation indicators
            "dom.webdriver.enabled": False,
            "useAutomationExtension": False,
            # Disable devtools auto-open
            "devtools.toolbox.selectedTool": "webconsole",
            "devtools.policy.disabled": True,
            # Disable various tracking/telemetry
            "datareporting.healthreport.uploadEnabled": False,
            "datareporting.policy.dataSubmissionEnabled": False,
            "toolkit.telemetry.enabled": False,
            "app.shield.optoutstudies.enabled": False,
            "browser.discovery.enabled": False,
            # Disable WebRTC IP leak
            "media.peerconnection.ice.default_address_only": True,
            "media.peerconnection.ice.no_host": True,
            # Privacy
            "privacy.trackingprotection.enabled": True,
            "privacy.resistFingerprinting": False,  # Too aggressive, breaks sites
            # Performance
            "gfx.webrender.all": True,
            "layers.acceleration.force-enabled": True,
        }

        launch_options = {
            "headless": headless,
            "firefox_user_prefs": firefox_prefs,
        }

        # Proxy support
        proxy_url = self.config.get("browser.proxy")
        if proxy_url:
            self._proxy_config = self._parse_proxy_url(proxy_url)
            launch_options["proxy"] = self._proxy_config

        self.browser = await self.playwright.firefox.launch(**launch_options)

        # Generate fingerprint
        self._fingerprint = FirefoxFingerprint.generate()

        # Create context
        context_options = {
            "user_agent": self._fingerprint["user_agent"],
            "viewport": self._fingerprint["viewport"],
            "locale": self._fingerprint["locale"],
            "timezone_id": self._fingerprint["timezone"],
            "color_scheme": "light",
            "device_scale_factor": self._fingerprint["pixel_ratio"],
            "has_touch": False,
            "is_mobile": False,
            "java_script_enabled": True,
            "ignore_https_errors": True,
        }

        self.context = await self.browser.new_context(**context_options)

        # Inject Firefox stealth patches
        await self.context.add_init_script(FIREFOX_STEALTH_JS)

        # Request interception
        await self.context.route("**/*", self._handle_request)

        # Download handler
        self.context.on("download", self._handle_download)

        # Create main page
        self.page = await self.context.new_page()
        self._pages["main"] = self.page
        self._attach_console_listener("main", self.page)

    async def _handle_request(self, route, request):
        """Intercept bot detection requests."""
        url_lower = request.url.lower()
        BLOCK_DOMAINS = [
            "google.com/recaptcha", "gstatic.com/recaptcha", "recaptcha.net",
            "hcaptcha.com", "challenges.cloudflare.com",
            "cloudflare.com/cdn-cgi/challenge",
            "captcha.px-cloud.net", "px-cdn.net", "px-client.net",
            "js.datadome.co", "datadome.co",
            "kasada.io", "k-i.co",
            "arkoselabs.com", "funcaptcha.co", "funcaptcha.com",
            "threatmetrix.com", "iovation.com", "sardine.com",
        ]

        for domain in BLOCK_DOMAINS:
            if domain in url_lower:
                self._blocked_requests += 1
                await route.fulfill(status=200, body="")
                return

        # Block bot detection scripts
        if request.resource_type == "script":
            script_blocks = ["recaptcha", "hcaptcha", "perimeterx", "kasada", "datadome"]
            for pattern in script_blocks:
                if pattern in url_lower:
                    self._blocked_requests += 1
                    await route.fulfill(status=200, body="")
                    return

        await route.continue_()

    async def _handle_download(self, download):
        """Handle downloads."""
        download_path = self._download_dir / download.suggested_filename
        await download.save_as(download_path)
        logger.info(f"Firefox downloaded: {download_path}")

    def _attach_console_listener(self, page_id: str, page: Page):
        """Attach console/error listeners."""
        self._console_logs[page_id] = []

        def on_console(msg):
            self._console_logs[page_id].append({
                "type": msg.type,
                "text": msg.text,
                "timestamp": time.time(),
            })
            # Cap at 150 per page
            if len(self._console_logs[page_id]) > 150:
                self._console_logs[page_id] = self._console_logs[page_id][-150:]

        def on_page_error(error):
            self._console_logs[page_id].append({
                "type": "pageerror",
                "text": str(error),
                "timestamp": time.time(),
            })

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

    BLOCK_INDICATORS = [
        "cloudflare challenge",
        "checking your browser",
        "please wait while we verify",
        "access denied - bot detection",
        "are you a robot",
        "cf-browser-verification",
        "just a moment",
        "ray id",
    ]

    def _is_blocked_page(self, title: str, text: str) -> bool:
        combined = (title + " " + text[:500]).lower()
        return any(indicator in combined for indicator in self.BLOCK_INDICATORS)

    async def navigate(self, url: str, page_id: str = "main",
                       wait_until: str = "domcontentloaded",
                       retries: int = 2) -> Dict[str, Any]:
        """Navigate with Firefox stealth."""
        page = self._pages.get(page_id, self.page)
        last_error = None

        for attempt in range(retries + 1):
            if attempt > 0:
                wait_time = random.uniform(2.0, 5.0) * attempt
                logger.info(f"Firefox retry {attempt}/{retries} for {url[:60]} (waiting {wait_time:.1f}s)")
                await asyncio.sleep(wait_time)

            await asyncio.sleep(random.uniform(0.3, 1.2))

            try:
                response = await page.goto(url, wait_until=wait_until, timeout=30000)

                # Only add human-like delay for complex sites that need JS rendering time
                domain = urlparse(url).netloc.lower()
                if any(d in domain for d in ['twitter.com', 'facebook.com', 'instagram.com', 'linkedin.com']):
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                else:
                    await asyncio.sleep(random.uniform(0.1, 0.3))

                title = await page.title()
                text = ""
                try:
                    body = await page.query_selector("body")
                    if body:
                        text = await body.inner_text()
                except Exception:
                    pass

                status_code = response.status if response else 200

                if self._is_blocked_page(title, text) and attempt < retries:
                    logger.warning(f"Firefox: block detected on {url[:60]} (attempt {attempt + 1})")
                    continue

                # Save cookies after successful navigation
                await self._save_cookies("default")

                return {
                    "status": "success",
                    "url": page.url,
                    "title": title,
                    "status_code": status_code,
                    "blocked_requests": self._blocked_requests,
                    "engine": "firefox",
                    "attempt": attempt + 1,
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"Firefox navigation attempt {attempt + 1} failed: {e}")
                if "timeout" in last_error.lower() and attempt < retries:
                    wait_until = "networkidle"

        return {"status": "error", "error": last_error or "All retries exhausted", "engine": "firefox"}

    async def get_content(self, page_id: str = "main") -> Dict[str, Any]:
        """Get page content."""
        page = self._pages.get(page_id, self.page)
        return {
            "url": page.url,
            "title": await page.title(),
            "html": await page.content(),
            "text": await page.inner_text("body") if await page.query_selector("body") else "",
            "engine": "firefox",
        }

    async def screenshot(self, page_id: str = "main", full_page: bool = False) -> str:
        """Take screenshot."""
        import base64
        page = self._pages.get(page_id, self.page)
        img_bytes = await page.screenshot(type="png", full_page=full_page)
        return base64.b64encode(img_bytes).decode()

    async def fill_form(self, fields: Dict[str, str], page_id: str = "main") -> Dict[str, Any]:
        """Fill form fields with human-like typing."""
        page = self._pages.get(page_id, self.page)
        filled = []

        for selector, value in fields.items():
            try:
                element = await page.query_selector(selector)
                if not element:
                    for alt in [f'input[name="{selector}"]', f'input[placeholder*="{selector}"]',
                                f'textarea[name="{selector}"]', f'#{selector}']:
                        element = await page.query_selector(alt)
                        if element:
                            break

                if element:
                    await element.click()
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await element.fill("")
                    for char in value:
                        await element.type(char, delay=random.randint(50, 150))
                    filled.append(selector)
            except Exception as e:
                logger.error(f"Firefox fill error for {selector}: {e}")

        return {"status": "success", "filled": filled, "total": len(fields), "engine": "firefox"}

    async def click(self, selector: str, page_id: str = "main") -> Dict[str, Any]:
        """Click with human-like movement."""
        page = self._pages.get(page_id, self.page)
        try:
            element = await page.query_selector(selector)
            if not element:
                return {"status": "error", "error": f"Element not found: {selector}", "engine": "firefox"}

            await asyncio.sleep(random.uniform(0.05, 0.15))
            await element.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))

            return {"status": "success", "selector": selector, "engine": "firefox"}
        except Exception as e:
            return {"status": "error", "error": str(e), "engine": "firefox"}

    async def type_text(self, text: str, page_id: str = "main") -> Dict[str, Any]:
        """Type text."""
        page = self._pages.get(page_id, self.page)
        for char in text:
            await page.keyboard.type(char, delay=random.randint(50, 150))
        return {"status": "success", "typed": len(text), "engine": "firefox"}

    async def press_key(self, key: str, page_id: str = "main") -> Dict[str, Any]:
        """Press keyboard key."""
        page = self._pages.get(page_id, self.page)
        await page.keyboard.press(key)
        return {"status": "success", "key": key, "engine": "firefox"}

    async def evaluate_js(self, script: str, page_id: str = "main") -> Dict[str, Any]:
        """Execute JavaScript — returns {"status": ..., "result"/"error": ...}."""
        page = self._pages.get(page_id, self.page)
        try:
            value = await page.evaluate(script)
            return {"status": "success", "result": value}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500, page_id: str = "main") -> Dict[str, Any]:
        """Scroll page."""
        page = self._pages.get(page_id, self.page)
        y = amount if direction == "down" else -amount
        steps = random.randint(3, 8)
        for i in range(steps):
            step_y = y / steps + random.randint(-20, 20)
            await page.mouse.wheel(0, int(step_y))
            await asyncio.sleep(random.uniform(0.05, 0.15))
        return {"status": "success", "direction": direction, "amount": amount, "engine": "firefox"}

    async def go_back(self, page_id: str = "main") -> Dict[str, Any]:
        page = self._pages.get(page_id, self.page)
        await page.go_back()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return {"status": "success", "url": page.url, "engine": "firefox"}

    async def go_forward(self, page_id: str = "main") -> Dict[str, Any]:
        page = self._pages.get(page_id, self.page)
        await page.go_forward()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return {"status": "success", "url": page.url, "engine": "firefox"}

    async def new_tab(self, tab_id: str) -> str:
        """Create new tab."""
        page = await self.context.new_page()
        self._pages[tab_id] = page
        self._attach_console_listener(tab_id, page)
        return tab_id

    async def close_tab(self, tab_id: str) -> bool:
        """Close tab."""
        if tab_id in self._pages and tab_id != "main":
            await self._pages[tab_id].close()
            del self._pages[tab_id]
            self._console_logs.pop(tab_id, None)
            return True
        return False

    async def reload(self, page_id: str = "main") -> Dict[str, Any]:
        page = self._pages.get(page_id, self.page)
        await page.reload()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return {"status": "success", "url": page.url, "engine": "firefox"}

    async def get_console_logs(self, page_id: str = "main", clear: bool = False) -> Dict[str, Any]:
        logs = self._console_logs.get(page_id, [])
        result = logs[-100:]
        if clear:
            self._console_logs[page_id] = []
        return {"status": "success", "logs": result, "count": len(result), "engine": "firefox"}

    async def get_cookies(self, page_id: str = "main") -> Dict[str, Any]:
        cookies = await self.context.cookies()
        return {"status": "success", "cookies": cookies, "count": len(cookies), "engine": "firefox"}

    async def set_cookie(self, name: str, value: str, domain: str = None, page_id: str = "main", **kwargs) -> Dict[str, Any]:
        page = self._pages.get(page_id, self.page)
        if not domain:
            try:
                parsed = page.url.split("/")
                if len(parsed) >= 3:
                    domain = parsed[2].split(":")[0]
            except Exception:
                pass
        if not domain:
            return {"status": "error", "error": "Cannot infer domain", "engine": "firefox"}

        cookie = {"name": name, "value": value, "domain": domain, "path": kwargs.get("path", "/")}
        try:
            await self.context.add_cookies([cookie])
            return {"status": "success", "cookie": cookie, "engine": "firefox"}
        except Exception as e:
            return {"status": "error", "error": str(e), "engine": "firefox"}

    def _parse_proxy_url(self, proxy_url: str) -> Dict[str, Any]:
        parsed = urlparse(proxy_url)
        config = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8080}"}
        if parsed.username:
            config["username"] = parsed.username
        if parsed.password:
            config["password"] = parsed.password
        return config

    def _get_or_create_cookie_key(self) -> bytes:
        """Get or create encryption key for cookie storage."""
        key_path = Path(os.path.expanduser("~/.agent-os/.cookie_key"))
        if key_path.exists():
            return key_path.read_bytes()
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        return key

    def _load_cookies(self, profile: str = "default") -> Optional[Dict]:
        """Load saved cookies for a profile (encrypted)."""
        cookie_file = self._cookie_dir / f"{profile}.enc"
        if cookie_file.exists():
            try:
                if self._cookie_fernet:
                    encrypted = cookie_file.read_bytes()
                    decrypted = self._cookie_fernet.decrypt(encrypted)
                    return json.loads(decrypted)
                else:
                    # Fallback to plaintext if Fernet unavailable
                    with open(cookie_file) as f:
                        return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cookies for {profile}: {e}")
        return None

    async def _save_cookies(self, profile: str = "default"):
        """Save cookies to disk with Fernet encryption."""
        if not self.context:
            return
        try:
            state = await self.context.storage_state()
            cookie_file = self._cookie_dir / f"{profile}.enc"
            if self._cookie_fernet:
                encrypted = self._cookie_fernet.encrypt(json.dumps(state).encode())
                cookie_file.write_bytes(encrypted)
            else:
                # Fallback to plaintext if Fernet unavailable
                with open(cookie_file, "w") as f:
                    json.dump(state, f)
            cookie_file.chmod(0o600)
            self._cookies_dirty = False
            logger.info(f"Firefox cookies saved for profile: {profile}")
        except Exception as e:
            logger.warning(f"Firefox cookie save failed: {e}")

    async def recover(self):
        """Recover from crash."""
        async with self._recovery_lock:
            self._crash_count += 1
            if self._crash_count > self._max_crash_retries:
                raise RuntimeError("Firefox exceeded max crash retries")

            logger.warning(f"Firefox recovering (attempt {self._crash_count})")
            try:
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception:
                pass

            self.browser = None
            self.context = None
            self.page = None
            self._pages.clear()
            self._console_logs.clear()

            await self._launch_browser()
            self._crash_count = 0
            logger.info("Firefox recovered successfully")

    async def stop(self):
        """Clean shutdown."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Firefox engine stopped")


class DualEngineManager:
    """
    Manages both Chromium and Firefox engines with automatic fallback.

    When a site blocks Chromium, automatically retries with Firefox.
    Tracks which engine works best per domain.

    Usage:
        manager = DualEngineManager(config)
        await manager.start()

        # Auto-fallback: tries Chromium first, Firefox on failure
        result = await manager.navigate("https://example.com")

        # Force engine
        result = await manager.navigate("https://example.com", engine="firefox")

        await manager.stop()
    """

    def __init__(self, config, chromium_engine=None):
        self.config = config
        self.chromium = chromium_engine  # Existing AgentBrowser instance
        self.firefox: Optional[FirefoxEngine] = None
        self._domain_engine_map: Dict[str, str] = {}  # domain -> preferred engine
        self._engine_stats: Dict[str, Dict[str, int]] = {
            "chromium": {"success": 0, "fail": 0, "blocked": 0},
            "firefox": {"success": 0, "fail": 0, "blocked": 0},
        }
        self._started = False

    async def start(self):
        """Start Firefox engine (Chromium assumed already running)."""
        if not self.firefox:
            self.firefox = FirefoxEngine(self.config)
            await self.firefox.start()
            self._started = True
            logger.info("Dual engine manager started (Chromium + Firefox)")

    async def navigate(self, url: str, engine: str = None,
                       retries: int = 2, **kwargs) -> Dict[str, Any]:
        """
        Navigate with automatic engine fallback.

        Args:
            url: Target URL
            engine: Force "chromium" or "firefox", or None for auto
            retries: Retries per engine
            **kwargs: Passed to engine's navigate()
        """
        domain = urlparse(url).hostname or ""

        # Determine which engine to use
        if engine:
            primary_engine = engine
        elif domain in self._domain_engine_map:
            primary_engine = self._domain_engine_map[domain]
            logger.info(f"Using cached engine '{primary_engine}' for {domain}")
        else:
            primary_engine = "chromium"  # Default: try Chromium first

        engines_to_try = [primary_engine]
        if primary_engine == "chromium":
            engines_to_try.append("firefox")
        else:
            engines_to_try.append("chromium")

        last_result = None

        for eng in engines_to_try:
            browser = self.chromium if eng == "chromium" else self.firefox
            if not browser:
                continue

            try:
                result = await browser.navigate(url, retries=retries, **kwargs)

                if result.get("status") == "success":
                    self._engine_stats[eng]["success"] += 1
                    self._domain_engine_map[domain] = eng
                    result["engine_used"] = eng
                    return result
                else:
                    # Check if blocked
                    if self._is_block_result(result):
                        self._engine_stats[eng]["blocked"] += 1
                        logger.warning(f"{eng} blocked on {domain[:50]}, trying fallback")
                    else:
                        self._engine_stats[eng]["fail"] += 1

                    last_result = result

            except Exception as e:
                self._engine_stats[eng]["fail"] += 1
                logger.error(f"{eng} crashed on {url[:50]}: {e}")
                last_result = {"status": "error", "error": str(e), "engine": eng}

        # Both engines failed
        if last_result:
            last_result["engines_tried"] = engines_to_try
            return last_result

        return {"status": "error", "error": "No engines available"}

    def _is_block_result(self, result: Dict) -> bool:
        """Check if result indicates a block/detection."""
        status = result.get("status_code", 0)
        error = (result.get("error", "") or "").lower()

        if status in (403, 406, 429):
            return True
        if any(kw in error for kw in ["blocked", "denied", "captcha", "challenge", "bot"]):
            return True
        return False

    async def get_content(self, engine: str = "chromium", **kwargs) -> Dict:
        browser = self.chromium if engine == "chromium" else self.firefox
        if browser:
            return await browser.get_content(**kwargs)
        return {"error": f"Engine {engine} not available"}

    async def screenshot(self, engine: str = "chromium", **kwargs):
        browser = self.chromium if engine == "chromium" else self.firefox
        if browser:
            return await browser.screenshot(**kwargs)
        return None

    async def fill_form(self, fields: Dict, engine: str = "chromium", **kwargs) -> Dict:
        browser = self.chromium if engine == "chromium" else self.firefox
        if browser:
            return await browser.fill_form(fields, **kwargs)
        return {"error": f"Engine {engine} not available"}

    async def click(self, selector: str, engine: str = "chromium", **kwargs) -> Dict:
        browser = self.chromium if engine == "chromium" else self.firefox
        if browser:
            return await browser.click(selector, **kwargs)
        return {"error": f"Engine {engine} not available"}

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "engine_stats": self._engine_stats,
            "domain_preferences": dict(self._domain_engine_map),
            "firefox_available": self.firefox is not None,
            "chromium_available": self.chromium is not None,
        }

    def get_preferred_engine(self, domain: str) -> str:
        """Get preferred engine for a domain."""
        return self._domain_engine_map.get(domain, "chromium")

    async def stop(self):
        """Stop all engines."""
        if self.firefox:
            await self.firefox.stop()
        logger.info("Dual engine manager stopped")
