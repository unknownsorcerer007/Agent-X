"""
Agent-OS Evasion Engine
Real fingerprint generation, cloudscraper integration, unified HTTP engine.
"""

import json
import logging
import random
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("agent-os.evasion")


# ═══════════════════════════════════════════════════════════════
# REALISTIC BROWSER DATA — sourced from real browser telemetry
# ═══════════════════════════════════════════════════════════════

# GPU renderers actually seen in Chrome on Windows (real data)
@dataclass
class ConsistentFingerprint:
    """
    A fingerprint that's consistent across ALL detection vectors.
    Sites cross-check: if WebGL says Intel but canvas says NVIDIA → bot.
    This ensures everything matches a real hardware combination.
    """

    # Hardware profile (real combinations from telemetry data)
    HARDWARE_PROFILES = [
        {
            "name": "Intel UHD 630 + i7-10700",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "Intel Iris Xe + i7-1165G7",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "NVIDIA GTX 1660 + Ryzen 5",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 6,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "NVIDIA RTX 3060 + i5-12400",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 6,
            "memory": 32,
            "screen_res": (2560, 1440),
            "pixel_ratio": 1.0,
        },
        {
            "name": "AMD Radeon RX 580 + Ryzen 7",
            "webgl_vendor": "Google Inc. (AMD)",
            "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "Apple M1 Pro",
            "webgl_vendor": "Google Inc. (Apple)",
            "webgl_renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
            "cores": 10,
            "memory": 16,
            "screen_res": (2560, 1600),
            "pixel_ratio": 2.0,
        },
        {
            "name": "Apple M2",
            "webgl_vendor": "Google Inc. (Apple)",
            "webgl_renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)",
            "cores": 8,
            "memory": 8,
            "screen_res": (2560, 1600),
            "pixel_ratio": 2.0,
        },
    ]

    CHROME_VERSIONS = [
        ("148", 90), ("146", 5), ("145", 3), ("133", 2),
    ]

    TIMEZONES = [
        ("America/New_York", 20), ("America/Chicago", 10),
        ("America/Los_Angeles", 15), ("Europe/London", 12),
        ("Europe/Berlin", 10), ("Europe/Paris", 8),
    ]

    def __init__(self, seed: int = None):
        """Generate a consistent fingerprint from a seed."""
        if seed is None:
            seed = random.randint(1, 2**31 - 1)

        self.seed = seed
        self._rng = random.Random(seed)

        # Select hardware profile
        self.hardware = self._rng.choice(self.HARDWARE_PROFILES)

        # Select Chrome version
        versions, weights = zip(*self.CHROME_VERSIONS)
        self.chrome_version = self._weighted_choice(versions, weights)

        # Select timezone
        timezones, tz_weights = zip(*self.TIMEZONES)
        self.timezone = self._weighted_choice(timezones, tz_weights)

        # Derived values
        self.platform = "Win32" if "Apple" not in self.hardware["name"] else "MacIntel"
        self.os = "windows" if self.platform == "Win32" else "mac"

        # Canvas/Audio noise seeds (deterministic from main seed)
        self.canvas_seed = self._rng.randint(1, 2**31 - 1)
        self.audio_seed = self._rng.randint(1, 2**31 - 1)

        # Fingerprint ID (for tracking)
        self.fp_id = hashlib.md5(
            f"{seed}{self.hardware['name']}{self.chrome_version}".encode()
        ).hexdigest()[:12]

        # Build user agent
        if self.os == "windows":
            ua_os = "Windows NT 10.0; Win64; x64"
        else:
            ua_os = "Macintosh; Intel Mac OS X 10_15_7"

        self.user_agent = (
            f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{self.chrome_version}.0.0.0 Safari/537.36"
        )

    def _weighted_choice(self, items, weights):
        total = sum(weights)
        r = self._rng.uniform(0, total)
        cumulative = 0
        for item, weight in zip(items, weights):
            cumulative += weight
            if r <= cumulative:
                return item
        return items[-1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fp_id": self.fp_id,
            "seed": self.seed,
            "chrome_version": self.chrome_version,
            "platform": self.platform,
            "os": self.os,
            "user_agent": self.user_agent,
            "timezone": self.timezone,
            "webgl_vendor": self.hardware["webgl_vendor"],
            "webgl_renderer": self.hardware["webgl_renderer"],
            "hardware_concurrency": self.hardware["cores"],
            "device_memory": self.hardware["memory"],
            "screen_width": self.hardware["screen_res"][0],
            "screen_height": self.hardware["screen_res"][1],
            "pixel_ratio": self.hardware["pixel_ratio"],
            "canvas_seed": self.canvas_seed,
            "audio_seed": self.audio_seed,
        }

def generate_fingerprint(**kwargs) -> Dict[str, Any]:
    return ConsistentFingerprint().to_dict()





# CLOUDSCRAPER INTEGRATION
# ═══════════════════════════════════════════════════════════════

_CLOUDSCRAPER_AVAILABLE = False
try:
    import cloudscraper as _cloudscraper_module
    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    pass


class CloudflareSolver:
    """
    Cloudflare JS challenge solver. Handles CF v1/v2/v3 + Turnstile.
    Use as fallback when Playwright route-blocking isn't enough.
    """

    def __init__(self):
        self._scraper = None
        if _CLOUDSCRAPER_AVAILABLE:
            self._scraper = _cloudscraper_module.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True},
                delay=5,
            )
            logger.info("cloudscraper ready")
        else:
            logger.warning("cloudscraper not installed: pip install cloudscraper")

    def solve(self, url: str, method: str = "GET", **kwargs) -> Optional[Dict[str, Any]]:
        """
        Solve Cloudflare challenge and return response.
        Runs in thread executor to not block async loop.
        """
        if not self._scraper:
            return None
        try:
            if method.upper() == "POST":
                resp = self._scraper.post(url, **kwargs)
            else:
                resp = self._scraper.get(url, **kwargs)

            return {
                "status_code": resp.status_code,
                "text": resp.text,
                "cookies": dict(resp.cookies),
                "headers": dict(resp.headers),
                "url": resp.url,
                "cf_solved": resp.status_code == 200,
            }
        except Exception as e:
            logger.error(f"cloudscraper failed for {url[:60]}: {e}")
            return None

    def get_clearance_cookies(self, url: str) -> Optional[Dict]:
        """Get cf_clearance cookies for reuse in Playwright."""
        if not self._scraper:
            return None
        try:
            resp = self._scraper.get(url)
            if resp.status_code == 200:
                return {
                    "cookies": dict(resp.cookies),
                    "cf_clearance": resp.cookies.get("cf_clearance"),
                    "user_agent": self._scraper.headers.get("User-Agent"),
                }
        except Exception as e:
            logger.error(f"CF cookie extraction failed: {e}")
        return None

    @property
    def available(self) -> bool:
        return _CLOUDSCRAPER_AVAILABLE


# ═══════════════════════════════════════════════════════════════
# UNIFIED EVASION ENGINE
# ═══════════════════════════════════════════════════════════════

class EvasionEngine:
    """
    Coordinates all evasion layers:

    - TLS: curl_cffi for HTTP requests, CDP spoofing for Playwright
    - Fingerprint: Randomized per-session generation + JS injection
    - Cloudflare: cloudscraper fallback for CF challenges
    """

    def __init__(self):
        # TLS engine (curl_cffi)
        from src.core.tls_spoof import TLSFingerprintEngine
        try:
            self.tls = TLSFingerprintEngine()
        except ImportError:
            self.tls = None
            logger.warning("TLS engine unavailable (install curl_cffi)")

        # Cloudflare solver
        self.cloudflare = CloudflareSolver()

        # Active fingerprints (page_id → fingerprint)
        self._fingerprints: Dict[str, Dict] = {}

    def generate_fingerprint(
        self,
        os_target: Optional[str] = None,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Generate and store a new fingerprint for a page."""
        if os_target is None:
            os_target = random.choice(["windows", "windows", "windows", "mac", "linux"])

        fp = ConsistentFingerprint().to_dict()
        self._fingerprints[page_id] = fp
        return fp

    def get_fingerprint(self, page_id: str = "main") -> Optional[Dict]:
        return self._fingerprints.get(page_id)

    def list_fingerprints(self) -> Dict[str, str]:
        """Summary of active fingerprints."""
        return {
            pid: f"{fp['os']} Chrome {fp['chrome_version']} / {fp['webgl_renderer'][:30]}"
            for pid, fp in self._fingerprints.items()
        }

    @property
    def status(self) -> Dict:
        return {
            "tls_engine": self.tls.stats if self.tls else {"available": False},
            "cloudflare": {"available": self.cloudflare.available},
            "active_fingerprints": len(self._fingerprints),
        }
