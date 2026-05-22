"""
Agent-OS CAPTCHA Bypass System
Blocks bot-detection queries at the network level and returns fake human responses.
This is the core anti-detection technology.
"""
import re
import random
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.captcha-bypass")


@dataclass
class BlockedEndpoint:
    """A bot detection endpoint that has been blocked."""
    url: str
    pattern_matched: str
    fake_response: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class CaptchaBypass:
    """
    CAPTCHA prevention engine.

    Strategy: Don't SOLVE CAPTCHAs — PREVENT them from loading.
    We intercept bot-detection scripts and queries, returning fake "human verified" responses.
    """

    # URL patterns that trigger bot detection.
    # All patterns are matched against the HOSTNAME only (not the full URL)
    # unless the domain is a known CDN (gstatic.com, cdnjs.cloudflare.com, etc.)
    # where we also check the path.
    DETECTION_PATTERNS = [
        # Google reCAPTCHA
        r"recaptcha\.net",
        r"google\.com/recaptcha",
        r"gstatic\.com/recaptcha",
        r"googleapis\.com/recaptcha",
        # hCaptcha
        r"hcaptcha\.com",
        # Cloudflare Turnstile
        r"challenges\.cloudflare\.com",
        r"turnstile",
        # PerimeterX
        r"captcha\.px-cloud\.net",
        r"perimeterx",
        r"px-cdn\.net",
        r"px-client\.net",
        r"px-captcha\.net",
        # DataDome
        r"datadome\.co",
        r"captcha\.geo\.datadome",
        r"js\.datadome\.co",
        # Imperva/Incapsula
        r"imperva\.com",
        r"incapdns\.net",
        r"_Incapsula_Resource",
        # Akamai Bot Manager
        r"akamai-bot",
        r"akadns\.net.*bot",
        r"akamai.*sensor",
        # Shape Security
        r"shapesecurity\.com",
        # Kasada
        r"kasada\.io",
        r"k-i\.co",
        # F5 / BigIP
        r"f5-.*\.net",
        r"bigip",
        # Arkose Labs (FunCaptcha)
        r"arkoselabs\.com",
        r"funcaptcha\.co",
        r"funcaptcha\.com",
        # Generic bot detection
        r"bot-detection",
        r"botdetect",
        r"verify-human",
        r"check-bot",
        r"anti-bot",
        r"captcha",
        r"challenge\.php",
        # Fraud detection
        r"threatmetrix",
        r"iovation",
        r"nethra",
        r"sardine\.com",
        r"seon\.io",
        r"ipqualityscore",
        # Fingerprinting services
        r"fingerprintjs\.com",
        r"fpjs\.io",
        r"fingerprint\.com",
        r"botd\.fpjs\.io",
        # Additional anti-bot vendors
        r"netacea\.com",
        r"reblaze\.com",
    ]

    # Known CDN domains where path matching is also needed.
    # For these domains we check the full URL (hostname + path).
    CDN_DOMAINS_REQUIRING_PATH = [
        "gstatic.com",
        "googleapis.com",
        "google.com",
        "cdnjs.cloudflare.com",
        "jsdelivr.net",
        "unpkg.com",
        "cdn.jsdelivr.net",
        "cloudflareinsights.com",
    ]

    # JavaScript patterns that detect bots
    BOT_DETECTION_JS_PATTERNS = [
        "navigator.webdriver",
        "window.cdc_adoQpoasnfa76pfcZLmcfl_Array",
        "window.cdc_adoQpoasnfa76pfcZLmcfl_Promise",
        "window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol",
        "phantom",
        "__nightmare",
        "_selenium",
        "_phantom",
        "callPhantom",
        "__webdriver_evaluate",
        "__selenium_evaluate",
        "__fxdriver_evaluate",
        "__driver_unwrapped",
        "__webdriver_unwrapped",
        "__selenium_unwrapped",
        "__fxdriver_unwrapped",
    ]

    def __init__(self) -> None:
        self._compiled_patterns: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in self.DETECTION_PATTERNS
        ]
        self._blocked: List[BlockedEndpoint] = []
        self._stats: Dict[str, Any] = {
            "total_blocked": 0,
            "by_type": {},
        }

    def _get_match_target(self, url: str) -> str:
        """Extract the appropriate matching target from a URL.

        For most URLs, we match patterns against the hostname only.
        For known CDN domains, we also include the path because legitimate
        CDNs host both detection scripts and normal assets — we only want
        to block the detection-specific paths.

        Args:
            url: The full URL to process.

        Returns:
            A string to match patterns against (hostname for regular domains,
            hostname + path for CDN domains).
        """
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        # For CDN domains, include the path to avoid false positives
        for cdn in self.CDN_DOMAINS_REQUIRING_PATH:
            if cdn in hostname:
                path = (parsed.path or "").lower()
                return hostname + path

        return hostname

    def is_bot_detection(self, url: str) -> bool:
        """Check if a URL is a bot detection endpoint.

        Args:
            url: The full URL to check.

        Returns:
            True if the URL matches a known bot detection pattern.
        """
        match_target = self._get_match_target(url)
        for pattern in self._compiled_patterns:
            if pattern.search(match_target):
                return True
        return False

    def detect(self, url: str) -> Optional[str]:
        """Detect bot detection type for a URL. Alias for combined check + type.

        Args:
            url: The full URL to check.

        Returns:
            The detection type string (e.g. "recaptcha", "hcaptcha") if detected,
            None if the URL is not a bot detection endpoint.
        """
        if self.is_bot_detection(url):
            return self.get_detection_type(url)
        return None

    def get_detection_type(self, url: str) -> str:
        """Identify which type of bot detection this is.

        Args:
            url: The URL to classify.

        Returns:
            A string identifier for the detection type.
        """
        match_target = self._get_match_target(url)
        type_map: Dict[str, List[str]] = {
            "recaptcha": ["recaptcha", "gstatic.com/recaptcha"],
            "hcaptcha": ["hcaptcha"],
            "cloudflare": ["challenges.cloudflare", "turnstile"],
            "perimeterx": ["perimeterx", "px-cloud", "px-cdn", "px-client", "px-captcha"],
            "datadome": ["datadome"],
            "imperva": ["imperva", "incapdns", "_Incapsula_Resource"],
            "akamai": ["akamai"],
            "shape": ["shapesecurity"],
            "kasada": ["kasada", "k-i.co"],
            "f5": ["f5-", "bigip"],
            "arkose": ["arkoselabs", "funcaptcha"],
            "threatmetrix": ["threatmetrix", "nethra"],
            "iovation": ["iovation"],
            "sardine": ["sardine"],
            "seon": ["seon"],
            "ipqualityscore": ["ipqualityscore"],
            "fingerprint": ["fingerprintjs", "fpjs.io", "fingerprint.com", "botd.fpjs.io"],
            "netacea": ["netacea"],
            "reblaze": ["reblaze"],
        }
        for det_type, patterns in type_map.items():
            if any(p in match_target for p in patterns):
                return det_type
        return "generic"

    def get_fake_response(self, detection_type: str) -> Dict[str, Any]:
        """Generate a convincing fake human verification response.

        Args:
            detection_type: The detection type string from get_detection_type().

        Returns:
            A dict mimicking a successful human verification response.
        """
        responses: Dict[str, Dict[str, Any]] = {
            "recaptcha": {
                "success": True,
                "score": round(random.uniform(0.85, 0.99), 2),
                "action": "login",
                "challenge_ts": "2026-04-08T12:00:00Z",
                "hostname": "localhost"
            },
            "hcaptcha": {
                "success": True,
                "challenge_ts": "2026-04-08T12:00:00Z",
                "hostname": "localhost",
                "credit": False
            },
            "cloudflare": {
                "success": True,
                "cf_clearance": "agent_os_clearance_token_2026",
                "ray": "fake_ray_id"
            },
            "perimeterx": {
                "status": 0,
                "uuid": "agent-os-fake-uuid",
                "vid": "agent-os-fake-vid",
                "risk_score": random.randint(1, 15),
                "action": "captcha_pass"
            },
            "datadome": {
                "status": "allowed",
                "cookie": "datadome=verified_agent_os",
                "response": "human"
            },
            "imperva": {
                "result": "human",
                "confidence": round(random.uniform(0.9, 0.99), 2)
            },
            "akamai": {
                "bot_score": random.randint(90, 100),
                "classification": "human"
            },
            "shape": {
                "blocked": False,
                "human": True
            },
            "kasada": {
                "verified": True,
                "token": "agent-os-kasada-token"
            },
            "f5": {
                "bot_score": random.randint(90, 100),
                "human": True
            },
            "arkose": {
                "solved": True,
                "session_token": "agent-os-arkose-token"
            },
            "threatmetrix": {
                "org_id": "agent-os",
                "result": "pass",
                "risk_score": random.randint(1, 10)
            },
            "iovation": {
                "result": "pass",
                "confidence": round(random.uniform(0.9, 0.99), 2)
            },
            "sardine": {
                "decision": "approve",
                "risk_score": random.randint(1, 15)
            },
            "seon": {
                "fraud_score": random.randint(1, 15),
                "decision": "approve"
            },
            "ipqualityscore": {
                "success": True,
                "fraud_score": random.randint(1, 15),
                "message": "Low Risk"
            },
            "fingerprint": {
                "blocked": True,
                "human": True,
                "score": round(random.uniform(0.9, 0.99), 2),
                "visitor_id": "agent-os-visitor-" + str(random.randint(100000, 999999))
            },
            "netacea": {
                "decision": "allow",
                "confidence": round(random.uniform(0.9, 0.99), 2)
            },
            "reblaze": {
                "blocked": False,
                "human": True
            },
            "generic": {
                "human": True,
                "verified": True,
                "score": round(random.uniform(0.9, 0.99), 2)
            }
        }
        return responses.get(detection_type, responses["generic"])

    def block_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Check if a request should be blocked.

        Args:
            url: The full URL of the outgoing request.

        Returns:
            A fake response dict if the request should be blocked,
            None if the request should be allowed through.
        """
        if self.is_bot_detection(url):
            detection_type = self.get_detection_type(url)
            fake_response = self.get_fake_response(detection_type)

            self._blocked.append(BlockedEndpoint(
                url=url,
                pattern_matched=detection_type,
                fake_response=fake_response,
                timestamp=time.time(),
            ))

            self._stats["total_blocked"] += 1
            self._stats["by_type"][detection_type] = self._stats["by_type"].get(detection_type, 0) + 1

            logger.info(f"Blocked {detection_type} detection: {url[:80]}...")
            return fake_response

        return None

    def sanitize_js(self, html: str) -> str:
        """Remove bot detection JavaScript from HTML before execution.

        This prevents detection scripts from running at all.
        It complements network-level blocking by catching inline scripts
        that don't load from external URLs.

        Args:
            html: The raw HTML to sanitize.

        Returns:
            HTML with detection scripts replaced by comments.
        """
        sanitized = html

        # Remove webdriver detection via __defineGetter__
        sanitized = re.sub(
            r'navigator\.__defineGetter__\(\s*["\']webdriver["\'].*?\)',
            'navigator.__defineGetter__("webdriver", () => false)',
            sanitized,
            flags=re.DOTALL
        )

        # Remove webdriver detection via defineProperty
        sanitized = re.sub(
            r'Object\.defineProperty\(\s*navigator\s*,\s*["\']webdriver["\'].*?\)',
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})',
            sanitized,
            flags=re.DOTALL
        )

        # Remove detection script blocks by JS content patterns
        for pattern in self.BOT_DETECTION_JS_PATTERNS:
            sanitized = re.sub(
                rf'<script[^>]*>.*?{re.escape(pattern)}.*?</script>',
                '<!-- Agent-OS: bot detection script blocked -->',
                sanitized,
                flags=re.DOTALL | re.IGNORECASE
            )

        # Remove scripts that load from known detection domains
        detection_domain_patterns = [
            r"recaptcha",
            r"hcaptcha",
            r"perimeterx",
            r"datadome",
            r"kasada",
            r"arkoselabs",
            r"funcaptcha",
            r"fingerprintjs",
            r"fpjs\.io",
            r"botd",
            r"threatmetrix",
            r"iovation",
            r"sardine",
            r"ipqualityscore",
            r"netacea",
            r"reblaze",
        ]
        for domain_pattern in detection_domain_patterns:
            sanitized = re.sub(
                rf'<script[^>]+src=["\'][^"\']*{domain_pattern}[^"\']*["\'][^>]*>.*?</script>',
                '<!-- Agent-OS: detection domain script blocked -->',
                sanitized,
                flags=re.DOTALL | re.IGNORECASE
            )
            # Also catch self-closing script tags
            sanitized = re.sub(
                rf'<script[^>]+src=["\'][^"\']*{domain_pattern}[^"\']*["\'][^>]*/>',
                '<!-- Agent-OS: detection domain script blocked -->',
                sanitized,
                flags=re.DOTALL | re.IGNORECASE
            )

        return sanitized

    def get_stats(self) -> Dict[str, Any]:
        """Get bypass statistics.

        Returns:
            Dict with total_blocked, by_type breakdown, and recent blocks.
        """
        return {
            "total_blocked": self._stats["total_blocked"],
            "by_type": dict(self._stats["by_type"]),
            "recent_blocks": [
                {
                    "url": b.url[:100],
                    "type": b.pattern_matched,
                    "timestamp": b.timestamp,
                }
                for b in self._blocked[-10:]
            ]
        }

    def get_blocklist_update(self) -> List[str]:
        """Return current detection patterns for external updates.

        Returns:
            A copy of the DETECTION_PATTERNS list.
        """
        return self.DETECTION_PATTERNS.copy()
