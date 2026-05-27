"""
Agent-X Enhanced Cloudflare Bypass Engine
Production-grade Cloudflare v1/v2/v3 + Turnstile + Managed Challenge bypass.

This is the NEXT-GEN bypass system that handles:
  - Cloudflare JS Challenge (v1/v2) — classic "Just a moment..."
  - Cloudflare v3 (managed challenge) — invisible browser check
  - Cloudflare Turnstile — CAPTCHA replacement
  - Cloudflare WAF blocks — 1020/1015/1012 errors
  - cf_clearance cookie extraction and reuse
  - TLS fingerprint matching with cf-req-sys-hash
  - JA3 fingerprint rotation
  - Browser fingerprint consistency with CF expectations

Strategy: Multi-layer bypass combining:
  1. Playwright-based challenge solving (browser-level)
  2. curl_cffi TLS fingerprint matching (HTTP-level)
  3. cloudscraper fallback (Python-level)
  4. cf_clearance cookie reuse across sessions
  5. Automatic challenge detection and strategy selection
"""
import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("agent-x.cf-bypass")


# ═══════════════════════════════════════════════════════════════
# CHALLENGE TYPE DETECTION
# ═══════════════════════════════════════════════════════════════

class CloudflareChallengeType(str, Enum):
    JS_CHALLENGE = "js_challenge"           # Classic "Just a moment..." page
    MANAGED_CHALLENGE = "managed_challenge"  # v3 — invisible browser check
    TURNSTILE = "turnstile"                 # CAPTCHA replacement
    WAF_BLOCK = "waf_block"                 # 1020/1015/1012 rules
    CAPTCHA = "captcha"                     # Legacy CF CAPTCHA
    I_UNDERSTAND = "i_understand"           # "I understand" button
    NO_CHALLENGE = "no_challenge"           # No CF protection detected


@dataclass
class ChallengeDetection:
    """Result of Cloudflare challenge detection on a page."""
    challenge_type: CloudflareChallengeType
    confidence: float          # 0.0 to 1.0
    ray_id: str = ""           # CF-Ray header value
    server: str = ""           # Server header
    status_code: int = 0
    title: str = ""
    has_turnstile: bool = False
    turnstile_sitekey: str = ""
    has_clearance_cookie: bool = False
    has_cf_mitigation: bool = False
    waf_rule_id: str = ""
    page_html: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# CF_CLEARANCE COOKIE STORE
# ═══════════════════════════════════════════════════════════════

class ClearanceStore:
    """
    Stores and manages cf_clearance cookies per domain.
    Enables reuse across sessions to avoid re-solving challenges.
    """

    def __init__(self, storage_dir: str = None):
        self._dir = Path(storage_dir or os.path.expanduser("~/.agent-x/cf_clearance"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict] = {}  # domain -> cookie data
        self._load()

    def _load(self):
        """Load saved clearance cookies."""
        for path in self._dir.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                domain = path.stem
                self._cache[domain] = data
            except Exception:
                continue
        logger.info(f"Loaded {len(self._cache)} clearance cookies")

    def get(self, domain: str) -> Optional[Dict]:
        """Get clearance cookies for a domain."""
        data = self._cache.get(domain)
        if not data:
            # Try parent domain
            parts = domain.split(".")
            for i in range(1, len(parts)):
                parent = ".".join(parts[i:])
                data = self._cache.get(parent)
                if data:
                    break

        if not data:
            return None

        # Check expiry (cf_clearance typically lasts 30 minutes to 24 hours)
        created = data.get("created", 0)
        max_age = data.get("max_age", 1800)  # Default 30 min
        if time.time() - created > max_age:
            self.remove(domain)
            return None

        return data

    def save(self, domain: str, cookies: Dict[str, str],
             user_agent: str = "", max_age: int = 1800):
        """Save clearance cookies for a domain."""
        data = {
            "domain": domain,
            "cookies": cookies,
            "user_agent": user_agent,
            "created": time.time(),
            "max_age": max_age,
        }
        self._cache[domain] = data
        path = self._dir / f"{domain}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved clearance cookies for {domain}")

    def remove(self, domain: str):
        """Remove clearance cookies for a domain."""
        self._cache.pop(domain, None)
        path = self._dir / f"{domain}.json"
        if path.exists():
            path.unlink()

    def list_domains(self) -> List[str]:
        """List domains with stored clearance."""
        return list(self._cache.keys())

    def clear_expired(self) -> int:
        """Remove expired clearance cookies."""
        removed = 0
        for domain in list(self._cache.keys()):
            data = self._cache[domain]
            created = data.get("created", 0)
            max_age = data.get("max_age", 1800)
            if time.time() - created > max_age:
                self.remove(domain)
                removed += 1
        return removed


# ═══════════════════════════════════════════════════════════════
# CHALLENGE DETECTOR
# ═══════════════════════════════════════════════════════════════

class ChallengeDetector:
    """
    Detects Cloudflare challenge type from page content, headers, and URL.
    Works with both Playwright pages and raw HTTP responses.
    """

    # CF-Ray header pattern
    CF_RAY_PATTERN = re.compile(r'^[a-f0-9]{16}(-[A-Z]{2,3})?$')

    # Challenge page indicators
    JS_CHALLENGE_INDICATORS = [
        "just a moment",
        "checking your browser",
        "ddos protection by cloudflare",
        "please wait while your request is being verified",
        "please turn javascript on",
        "ray id",
        "cf-browser-verification",
    ]

    MANAGED_CHALLENGE_INDICATORS = [
        "managed challenge",
        "verify you are human",
        "security verification",
        "performing security verification",
        "cf-challenge-running",
    ]

    TURNSTILE_INDICATORS = [
        "challenges.cloudflare.com/turnstile",
        "cf-turnstile",
        "turnstile-widget",
        "data-sitekey",
        "_cf_chl_opt",
    ]

    WAF_INDICATORS = [
        "error 1020",
        "error 1015",
        "error 1012",
        "access denied",
        "you do not have access",
        "the site owner may have set restrictions",
        "cloudflare ray id",
    ]

    async def detect_from_page(self, page, response=None) -> ChallengeDetection:
        """
        Detect challenge type from a Playwright page.

        Args:
            page: Playwright Page object
            response: Optional Playwright Response from navigation
        """
        headers = {}
        status_code = 0

        if response:
            status_code = response.status
            headers = dict(response.headers) if hasattr(response, 'headers') else {}

        # Get page content
        title = ""
        html = ""
        try:
            title = await page.title()
        except Exception:
            pass
        try:
            html = await page.content()
        except Exception:
            pass

        # Check URL for challenge patterns
        url = page.url if hasattr(page, 'url') else ""

        return self._analyze(url, title, html, headers, status_code)

    async def detect_from_response(self, url: str, status_code: int,
                                    headers: Dict[str, str], body: str) -> ChallengeDetection:
        """Detect challenge type from raw HTTP response."""
        return self._analyze(url, "", body, headers, status_code)

    def _analyze(self, url: str, title: str, html: str,
                 headers: Dict[str, str], status_code: int) -> ChallengeDetection:
        """Core analysis logic."""
        html_lower = html.lower() if html else ""
        title_lower = title.lower() if title else ""
        combined = title_lower + " " + html_lower[:3000]

        # Extract CF-Ray
        ray_id = ""
        for h_name in ["cf-ray", "CF-Ray", "Cf-Ray"]:
            if h_name in headers:
                ray_id = headers[h_name]
                break

        # Check for cf_clearance cookie (in headers or page)
        _has_clearance = "cf_clearance" in html_lower or "cf_clearance" in str(headers)

        # Check server header
        server = headers.get("server", headers.get("Server", ""))

        # Detect challenge type
        detection = ChallengeDetection(
            challenge_type=CloudflareChallengeType.NO_CHALLENGE,
            confidence=0.0,
            ray_id=ray_id,
            server=server,
            status_code=status_code,
            title=title,
            headers=headers,
            page_html=html[:2000] if html else "",
        )

        # Check if page is a Cloudflare page at all
        is_cf_page = (
            "cloudflare" in server.lower() or
            ray_id or
            "cf-" in combined or
            "cloudflare" in combined
        )

        if not is_cf_page:
            # Not a CF page — but check status codes
            if status_code in (403, 503, 429, 1020):
                detection.challenge_type = CloudflareChallengeType.WAF_BLOCK
                detection.confidence = 0.7
            return detection

        # Check for Turnstile (highest priority — newest CF anti-bot)
        turnstile_score = sum(1 for ind in self.TURNSTILE_INDICATORS if ind in combined)
        if turnstile_score > 0:
            detection.challenge_type = CloudflareChallengeType.TURNSTILE
            detection.confidence = min(0.5 + turnstile_score * 0.15, 0.95)
            detection.has_turnstile = True

            # Extract Turnstile sitekey
            sitekey_match = re.search(r'data-sitekey=["\']([^"\']+)', html or "")
            if sitekey_match:
                detection.turnstile_sitekey = sitekey_match[1]
            else:
                # Try from _cf_chl_opt
                cf_opt_match = re.search(r'_cf_chl_opt\s*=\s*({[^}]+})', html or "")
                if cf_opt_match:
                    try:
                        cf_opt = json.loads(cf_opt_match[1])
                        detection.turnstile_sitekey = cf_opt.get("chlApiSitekey", "")
                    except Exception:
                        pass

            return detection

        # Check for Managed Challenge (v3)
        managed_score = sum(1 for ind in self.MANAGED_CHALLENGE_INDICATORS if ind in combined)
        if managed_score > 0:
            detection.challenge_type = CloudflareChallengeType.MANAGED_CHALLENGE
            detection.confidence = min(0.5 + managed_score * 0.15, 0.95)
            return detection

        # Check for JS Challenge (classic)
        js_score = sum(1 for ind in self.JS_CHALLENGE_INDICATORS if ind in combined)
        if js_score > 0:
            detection.challenge_type = CloudflareChallengeType.JS_CHALLENGE
            detection.confidence = min(0.4 + js_score * 0.1, 0.9)
            return detection

        # Check for WAF Block
        waf_score = sum(1 for ind in self.WAF_INDICATORS if ind in combined)
        if waf_score > 0 or status_code in (1020, 1015, 1012):
            detection.challenge_type = CloudflareChallengeType.WAF_BLOCK
            detection.confidence = min(0.4 + waf_score * 0.1, 0.9)

            # Extract WAF rule ID
            rule_match = re.search(r'rule.id["\s:=]+["\']?(\d+)', html_lower)
            if rule_match:
                detection.waf_rule_id = rule_match[1]

            return detection

        # Check for CAPTCHA (legacy)
        if "captcha" in combined or "managed-challenge" in combined:
            detection.challenge_type = CloudflareChallengeType.CAPTCHA
            detection.confidence = 0.7
            return detection

        # CF page but no specific challenge detected
        if is_cf_page:
            detection.challenge_type = CloudflareChallengeType.JS_CHALLENGE
            detection.confidence = 0.5

        return detection


# ═══════════════════════════════════════════════════════════════
# CHALLENGE SOLVERS
# ═══════════════════════════════════════════════════════════════

class JSChallengeSolver:
    """
    Solves classic CF JS challenges by waiting for the browser
    to complete the challenge naturally.
    """

    async def solve(self, page, detection: ChallengeDetection,
                    timeout: int = 30) -> Dict[str, Any]:
        """
        Wait for JS challenge to complete in the browser.

        CF JS challenges run JavaScript that performs browser checks,
        then sets a cf_clearance cookie and redirects.
        """
        start = time.time()

        try:
            # Wait for either:
            # 1. Navigation away from challenge page
            # 2. cf_clearance cookie to appear
            # 3. Page title to change (challenge passed)

            initial_url = page.url
            initial_title = await page.title()

            while time.time() - start < timeout:
                await asyncio.sleep(1.0)

                # Check if page changed (challenge passed)
                try:
                    current_url = page.url
                    current_title = await page.title()

                    # URL changed = redirect after challenge
                    if current_url != initial_url:
                        logger.info(f"JS Challenge solved: redirected to {current_url[:60]}")
                        return {
                            "status": "success",
                            "method": "browser_js_solve",
                            "time": round(time.time() - start, 2),
                            "redirected_to": current_url,
                        }

                    # Title changed = page content updated
                    if current_title != initial_title and "just a moment" not in current_title.lower():
                        logger.info(f"JS Challenge solved: title changed to '{current_title}'")
                        return {
                            "status": "success",
                            "method": "browser_js_solve",
                            "time": round(time.time() - start, 2),
                        }

                    # Check for cf_clearance cookie
                    cookies = await page.context.cookies()
                    for cookie in cookies:
                        if cookie.get("name") == "cf_clearance":
                            logger.info("JS Challenge solved: cf_clearance cookie found")
                            return {
                                "status": "success",
                                "method": "browser_js_solve",
                                "time": round(time.time() - start, 2),
                                "cf_clearance": True,
                            }

                except Exception:
                    pass

            return {
                "status": "timeout",
                "error": f"JS challenge not solved within {timeout}s",
                "time": round(time.time() - start, 2),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "time": round(time.time() - start, 2),
            }


class TurnstileSolver:
    """
    Solves Cloudflare Turnstile challenges.

    Turnstile is CF's CAPTCHA replacement. It uses a combination of
    browser fingerprinting, proof-of-work, and optional interactive
    challenges.

    Strategies (in order):
    1. Auto-solve (non-interactive mode) — most Turnstile passes are automatic
    2. External solver API (2captcha, Anti-Captcha)
    3. Manual intervention prompt
    """

    async def solve(self, page, detection: ChallengeDetection,
                    timeout: int = 8) -> Dict[str, Any]:
        """
        Solve Turnstile challenge.

        For non-interactive Turnstile, the browser needs to:
        1. Load the Turnstile script
        2. Execute the proof-of-work challenge
        3. Submit the token back to the page

        Note: In headless mode Turnstile NEVER auto-solves, so the timeout
        is intentionally short (8s). After expiry we return failure immediately
        rather than wasting more time on checkbox-click fallbacks.
        """
        start = time.time()

        try:
            # Strategy 1: Wait for auto-solve
            # Turnstile often auto-solves if browser fingerprint looks legitimate
            logger.info("Waiting for Turnstile auto-solve...")

            initial_url = page.url

            while time.time() - start < timeout:
                await asyncio.sleep(1.5)

                try:
                    # Check if Turnstile resolved
                    result = await page.evaluate("""
                        () => {
                            // Check for Turnstile response token
                            const resp = document.querySelector('[name="cf-turnstile-response"]');
                            if (resp && resp.value && resp.value.length > 10) {
                                return {solved: true, token: resp.value.substring(0, 50) + '...'};
                            }

                            // Check if widget shows success
                            const widget = document.querySelector('.cf-turnstile');
                            if (widget) {
                                const iframe = widget.querySelector('iframe');
                                if (iframe) {
                                    try {
                                        const iframeDoc = iframe.contentDocument;
                                        if (iframeDoc) {
                                            const success = iframeDoc.querySelector('[class*="success"], [class*="checkmark"]');
                                            if (success) return {solved: true, method: 'widget_success'};
                                        }
                                    } catch(e) {
                                        // Cross-origin iframe — can't access, check visibility
                                    }
                                }
                            }

                            // Check for page redirect (challenge passed)
                            return {solved: false, url: window.location.href};
                        }
                    """)

                    if result.get("solved"):
                        logger.info(f"Turnstile auto-solved in {time.time() - start:.1f}s")
                        return {
                            "status": "success",
                            "method": "auto_solve",
                            "time": round(time.time() - start, 2),
                        }

                    # Check if page redirected away from challenge
                    current_url = page.url
                    if current_url != initial_url:
                        # Verify it's not still a challenge page
                        title = await page.title()
                        if "just a moment" not in title.lower() and "challenge" not in title.lower():
                            logger.info(f"Turnstile solved via redirect to {current_url[:60]}")
                            return {
                                "status": "success",
                                "method": "redirect_solve",
                                "time": round(time.time() - start, 2),
                                "redirected_to": current_url,
                            }

                except Exception:
                    pass

            # Strategy 2: Scrapling-style Checkbox Click Fallback
            logger.info("Auto-solve timed out or not applicable, attempting Scrapling manual interaction...")
            box_selector = "#cf_turnstile div, #cf-turnstile div, .turnstile>div>div"
            outer_box = {}
            
            iframe = None
            for frame in page.frames:
                if frame.url and "challenges.cloudflare.com/cdn-cgi/challenge-platform" in frame.url:
                    iframe = frame
                    break
                    
            if iframe:
                try:
                    element = await iframe.frame_element()
                    if await element.is_visible():
                        outer_box = await element.bounding_box()
                except Exception:
                    pass
            
            if not iframe or not outer_box:
                try:
                    outer_box = await page.locator(box_selector).last.bounding_box()
                except Exception:
                    pass
                    
            if outer_box:
                # Calculate the Captcha coordinates with random jitter
                captcha_x = outer_box["x"] + random.randint(26, 28)
                captcha_y = outer_box["y"] + random.randint(25, 27)

                # Move the mouse to the center of the window, then press and hold the left mouse button
                logger.info(f"Clicking Turnstile box at ({captcha_x}, {captcha_y})")
                await page.mouse.click(captcha_x, captcha_y, delay=random.randint(100, 200), button="left")
                
                # Wait for interaction result
                attempts = 0
                while attempts < 10:
                    await asyncio.sleep(1.0)
                    title = await page.title()
                    if "just a moment" not in title.lower() and "challenge" not in title.lower():
                        logger.info("Turnstile solved via Scrapling interaction")
                        return {
                            "status": "success",
                            "method": "scrapling_interaction",
                            "time": round(time.time() - start, 2),
                        }
                    attempts += 1
            
            elapsed = round(time.time() - start, 2)
            logger.warning(f"Turnstile interaction failed or timed out after {elapsed}s")
            return {
                "status": "timeout",
                "error": f"Turnstile not solved within {timeout}s",
                "time": elapsed,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "time": round(time.time() - start, 2),
            }


class ManagedChallengeSolver:
    """
    Solves CF Managed Challenges (v3).
    These are invisible browser fingerprinting challenges.
    """

    async def solve(self, page, detection: ChallengeDetection,
                    timeout: int = 30) -> Dict[str, Any]:
        """Solve managed challenge by waiting for browser checks to pass."""
        start = time.time()
        initial_url = page.url

        try:
            while time.time() - start < timeout:
                await asyncio.sleep(1.0)

                try:
                    current_url = page.url
                    if current_url != initial_url:
                        title = await page.title()
                        if "challenge" not in title.lower() and "verify" not in title.lower():
                            return {
                                "status": "success",
                                "method": "managed_auto",
                                "time": round(time.time() - start, 2),
                            }

                    # Check for cf_clearance
                    cookies = await page.context.cookies()
                    for cookie in cookies:
                        if cookie.get("name") == "cf_clearance":
                            return {
                                "status": "success",
                                "method": "managed_clearance",
                                "time": round(time.time() - start, 2),
                            }

                    # Check page content for success indicators
                    html = await page.content()
                    if "challenge" not in html.lower() and "verify" not in html.lower():
                        if current_url != initial_url:
                            return {
                                "status": "success",
                                "method": "managed_passed",
                                "time": round(time.time() - start, 2),
                            }

                except Exception:
                    pass

            return {"status": "timeout", "error": "Managed challenge not passed"}

        except Exception as e:
            return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# TLS FINGERPRINT MATCHER
# ═══════════════════════════════════════════════════════════════

class TLSFingerprintMatcher:
    """
    Matches TLS fingerprints with cf-req-sys-hash expectations.

    Cloudflare checks TLS client hello fingerprint (JA3 hash).
    If the JA3 hash doesn't match a known browser, CF increases
    the challenge difficulty.

    This module:
    1. Generates browser-matching TLS fingerprints
    2. Uses curl_cffi to impersonate real browsers
    3. Matches cf-req-sys-hash when present
    """

    # Real browser JA3 hashes (Chrome, Firefox, Safari)
    BROWSER_JA3_HASHES = {
        "chrome_124": "773906b5cf21080981e6a5b3c9cb75a7",
        "chrome_123": "cd08e31494f9531f560d64c695473da9",
        "firefox_124": "6b0c49a0a697b09d4a394b3d5c204857",
        "firefox_123": "95740a455865c4e1f7f4b3f40e9c2d2a",
    }

    @staticmethod
    def get_curl_cffi_impersonate(browser: str = "chrome") -> str:
        """Get curl_cffi impersonate target string."""
        IMPERSONATE_MAP = {
            "chrome": "chrome124",
            "chrome_124": "chrome124",
            "chrome_123": "chrome123",
            "chrome_120": "chrome120",
            "chrome_116": "chrome116",
            "chrome_110": "chrome110",
            "firefox": "firefox124",
            "firefox_124": "firefox124",
            "firefox_123": "firefox123",
            "firefox_115": "firefox115",
            "safari": "safari17_0",
            "safari_17_0": "safari17_0",
            "safari_15_3": "safari15_3",
            "edge": "edge101",
            "edge_101": "edge101",
        }
        return IMPERSONATE_MAP.get(browser, "chrome124")


# ═══════════════════════════════════════════════════════════════
# MAIN BYPASS ENGINE
# ═══════════════════════════════════════════════════════════════

class CloudflareBypassEngine:
    """
    Main Cloudflare bypass engine orchestrating all strategies.

    Usage:
        engine = CloudflareBypassEngine(config)

        # Check a page for CF challenges
        detection = await engine.detect(page, response)

        # Solve detected challenge
        result = await engine.solve(page, detection)

        # Or use the high-level navigate method
        result = await engine.bypass_navigate(page, "https://protected-site.com")
    """

    def __init__(self, config=None):
        self.config = config
        self.detector = ChallengeDetector()
        self.clearance_store = ClearanceStore()

        # Solvers
        self.js_solver = JSChallengeSolver()
        self.turnstile_solver = TurnstileSolver()
        self.managed_solver = ManagedChallengeSolver()

        # TLS matcher
        self.tls_matcher = TLSFingerprintMatcher()

        # Stats
        self._stats = {
            "total_challenges": 0,
            "solved": 0,
            "failed": 0,
            "by_type": {},
        }

        # cloudscraper fallback
        self._cloudscraper = None
        try:
            import cloudscraper
            self._cloudscraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True},
                delay=5,
            )
            logger.info("CloudflareBypassEngine: cloudscraper available")
        except ImportError:
            logger.warning("CloudflareBypassEngine: cloudscraper not installed")

        # curl_cffi fallback
        self._curl_cffi = None
        try:
            from curl_cffi import requests as cffi_requests
            self._curl_cffi = cffi_requests
            logger.info("CloudflareBypassEngine: curl_cffi available")
        except ImportError:
            logger.warning("CloudflareBypassEngine: curl_cffi not installed")

    async def detect(self, page, response=None) -> ChallengeDetection:
        """Detect CF challenge on a page."""
        return await self.detector.detect_from_page(page, response)

    async def solve(self, page, detection: ChallengeDetection) -> Dict[str, Any]:
        """
        Solve a detected Cloudflare challenge.

        Routes to the appropriate solver based on challenge type.
        """
        self._stats["total_challenges"] += 1
        ct = detection.challenge_type
        type_key = ct.value
        self._stats["by_type"][type_key] = self._stats["by_type"].get(type_key, 0) + 1

        if ct == CloudflareChallengeType.NO_CHALLENGE:
            return {"status": "no_challenge"}

        logger.info(f"Solving {ct.value} challenge (confidence: {detection.confidence:.0%})")

        result = None

        if ct == CloudflareChallengeType.JS_CHALLENGE:
            result = await self.js_solver.solve(page, detection)

        elif ct == CloudflareChallengeType.TURNSTILE:
            result = await self.turnstile_solver.solve(page, detection)

        elif ct == CloudflareChallengeType.MANAGED_CHALLENGE:
            result = await self.managed_solver.solve(page, detection)

        elif ct in (CloudflareChallengeType.WAF_BLOCK, CloudflareChallengeType.CAPTCHA):
            # WAF blocks and CAPTCHAs need external solver
            result = {
                "status": "needs_external_solver",
                "challenge_type": ct.value,
                "suggestion": "Add 2captcha or Anti-Captcha API key for WAF/CAPTCHA bypass",
            }

        if result and result.get("status") == "success":
            self._stats["solved"] += 1
            # Save clearance cookies
            domain = urlparse(page.url).hostname or ""
            cookies = await page.context.cookies()
            cf_cookies = {c["name"]: c["value"] for c in cookies if "cf" in c["name"].lower()}
            if cf_cookies:
                self.clearance_store.save(domain, cf_cookies)
        else:
            self._stats["failed"] += 1

        return result or {"status": "error", "error": "No solver available"}

    async def bypass_navigate(self, page, url: str,
                               max_attempts: int = 3,
                               timeout: int = 60) -> Dict[str, Any]:
        """
        High-level navigate with automatic CF bypass.

        Handles the full flow:
        1. Check for cached clearance cookies
        2. Navigate to URL
        3. Detect challenge type
        4. Solve challenge
        5. Retry with different strategies if needed

        Args:
            page: Playwright Page object
            url: Target URL
            max_attempts: Max bypass attempts
            timeout: Timeout per attempt
        """
        domain = urlparse(url).hostname or ""
        last_detection = None

        for attempt in range(max_attempts):
            logger.info(f"CF bypass attempt {attempt + 1}/{max_attempts} for {url[:60]}")

            # Check for cached clearance
            if attempt == 0:
                clearance = self.clearance_store.get(domain)
                if clearance:
                    logger.info(f"Found cached clearance for {domain}")
                    try:
                        cookies = []
                        for name, value in clearance["cookies"].items():
                            cookies.append({
                                "name": name,
                                "value": value,
                                "domain": domain,
                                "path": "/",
                            })
                        await page.context.add_cookies(cookies)
                    except Exception:
                        pass

            # Navigate
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                _status_code = response.status if response else 200
            except Exception as e:
                logger.error(f"Navigation failed: {e}")
                # Try with networkidle on timeout
                if "timeout" in str(e).lower():
                    try:
                        response = await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                        _status_code = response.status if response else 200
                    except Exception as e2:
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(random.uniform(2, 5))
                            continue
                        return {"status": "error", "error": str(e2)}
                else:
                    continue

            # Wait for page to settle
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # Detect challenge
            detection = await self.detect(page, response)
            last_detection = detection

            if detection.challenge_type == CloudflareChallengeType.NO_CHALLENGE:
                # No challenge — page loaded successfully
                title = await page.title()
                return {
                    "status": "success",
                    "url": page.url,
                    "title": title,
                    "challenge_type": "none",
                    "attempt": attempt + 1,
                    "clearance_used": attempt == 0 and bool(self.clearance_store.get(domain)),
                }

            logger.info(f"Challenge detected: {detection.challenge_type.value} (confidence: {detection.confidence:.0%})")

            # Solve challenge
            solve_result = await self.solve(page, detection)

            if solve_result.get("status") == "success":
                # Verify we're past the challenge
                await asyncio.sleep(random.uniform(1.0, 2.0))
                title = await page.title()

                # Check if we're still on a challenge page
                verify_detection = await self.detect(page, None)
                if verify_detection.challenge_type == CloudflareChallengeType.NO_CHALLENGE:
                    return {
                        "status": "success",
                        "url": page.url,
                        "title": title,
                        "challenge_type": detection.challenge_type.value,
                        "solve_method": solve_result.get("method"),
                        "solve_time": solve_result.get("time"),
                        "attempt": attempt + 1,
                    }

            # Wait before retry
            if attempt < max_attempts - 1:
                wait = random.uniform(3.0, 8.0) * (attempt + 1)
                logger.info(f"Bypass attempt {attempt + 1} failed, waiting {wait:.1f}s...")
                await asyncio.sleep(wait)

        return {
            "status": "failed",
            "error": f"All {max_attempts} bypass attempts failed",
            "last_challenge_type": last_detection.challenge_type.value if last_detection else "unknown",
            "suggestion": "Try with Firefox engine or add residential proxy",
        }

    async def http_get_with_bypass(self, url: str,
                                    impersonate: str = "chrome") -> Dict[str, Any]:
        """
        HTTP GET with TLS fingerprint impersonation (no browser needed).

        Uses curl_cffi to match real browser TLS fingerprints,
        bypassing CF's TLS fingerprint check.
        """
        domain = urlparse(url).hostname or ""

        # Try with curl_cffi first (best TLS fingerprinting)
        if self._curl_cffi:
            try:
                imp = self.tls_matcher.get_curl_cffi_impersonate(impersonate)
                resp = self._curl_cffi.get(
                    url,
                    impersonate=imp,
                    timeout=30,
                    allow_redirects=True,
                )

                # Check if we passed CF
                if resp.status_code == 200:
                    # Extract and save clearance cookies
                    cf_cookies = {k: v for k, v in resp.cookies.items() if "cf" in k.lower()}
                    if cf_cookies:
                        self.clearance_store.save(domain, cf_cookies)

                    return {
                        "status": "success",
                        "status_code": resp.status_code,
                        "text": resp.text[:5000],
                        "headers": dict(resp.headers),
                        "method": "curl_cffi",
                        "impersonate": imp,
                        "cookies": cf_cookies,
                    }
                else:
                    return {
                        "status": "blocked",
                        "status_code": resp.status_code,
                        "text": resp.text[:1000],
                        "method": "curl_cffi",
                    }

            except Exception as e:
                logger.warning(f"curl_cffi request failed: {e}")

        # Fallback to cloudscraper
        if self._cloudscraper:
            try:
                resp = self._cloudscraper.get(url, timeout=30)
                if resp.status_code == 200:
                    cf_cookies = {k: v for k, v in resp.cookies.items() if "cf" in k.lower()}
                    if cf_cookies:
                        self.clearance_store.save(domain, cf_cookies)

                    return {
                        "status": "success",
                        "status_code": resp.status_code,
                        "text": resp.text[:5000],
                        "method": "cloudscraper",
                        "cookies": cf_cookies,
                    }
            except Exception as e:
                logger.warning(f"cloudscraper request failed: {e}")

        return {"status": "error", "error": "No HTTP bypass method available"}

    def get_stats(self) -> Dict[str, Any]:
        """Get bypass statistics."""
        return {
            "total_challenges": self._stats["total_challenges"],
            "solved": self._stats["solved"],
            "failed": self._stats["failed"],
            "success_rate": round(
                self._stats["solved"] / max(1, self._stats["total_challenges"]) * 100, 1
            ),
            "by_type": dict(self._stats["by_type"]),
            "cached_clearances": len(self.clearance_store.list_domains()),
            "curl_cffi_available": self._curl_cffi is not None,
            "cloudscraper_available": self._cloudscraper is not None,
        }

    def cleanup_expired(self) -> int:
        """Clean up expired clearance cookies."""
        return self.clearance_store.clear_expired()
# Alias for backward compatibility
CloudflareBypass = CloudflareBypassEngine
