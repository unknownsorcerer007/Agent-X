"""
Agent-X Shared Stealth Constants
Single source of truth for bot-blocking patterns, fake responses, and
supplementary anti-detection features.

STEALTH ARCHITECTURE (UNIFIED — NO CONFLICTS):
  Layer 1 (CDP — SOLE AUTHORITY): CDPStealthInjector in cdp_stealth.py
    - Injected via Page.addScriptToEvaluateOnNewDocument (runs BEFORE page scripts)
    - Handles ALL core anti-detection:
      webdriver, plugins, chrome object, WebGL, canvas, audio, WebRTC,
      screen, navigator properties, permissions, media devices, error stacks,
      timing, fingerprint library blocking, CDP/Playwright artifact cleanup
    - Stores objects in window.__agentOsStealthCache for headless verification
    - Provides setup_headless_verification() for post-navigation verify-only hook

  Layer 2 (Supplementary — NON-OVERLAPPING ONLY): SUPPLEMENTARY_STEALTH_JS below
    - ONLY features NOT in CDP stealth:
      Notification API full mock, Battery API mock, Font enumeration block,
      Beacon API interception, sendBeacon interception,
      Challenge detection observer, Navigator consistency guard
    - Does NOT override webdriver, plugins, chrome, WebGL, canvas, etc.

  Layer 3 (Request Interception): BOT_DETECTION_URLS + FAKE_RESPONSES
    - Blocks bot detection scripts at the network level
    - Returns fake human responses to detection endpoints

  Headless Verification (via CDP stealth):
    - Runs on every domcontentloaded event (VERIFY-ONLY, never creates new objects)
    - Checks if CDP stealth's __agentOsStealthCache references are still intact
    - Re-applies CACHED references if Chromium headless stripped them
    - Preserves reference identity across navigations (navigator.plugins === navigator.plugins)

  Cloudflare Bypass (unified flow):
    1. ClearanceStore — cached cf_clearance cookies from prior sessions
    2. CloudflareBypassEngine — Playwright-based challenge solving
    3. cloudscraper — legacy Python-based fallback
    4. curl_cffi — TLS fingerprint matching
    5. Domain bypass memory — tracks which strategy worked per domain
"""

# ─── Supplementary Anti-Detection JavaScript ─────────────────
# Features NOT covered by CDP stealth. Injected via add_init_script.
# This does NOT override webdriver, plugins, chrome, WebGL, canvas,
# audio, WebRTC, screen, navigator properties, or permissions.
# Those are ALL handled by CDPStealthInjector (cdp_stealth.py).

SUPPLEMENTARY_STEALTH_JS = """
// === AGENT-OS SUPPLEMENTARY STEALTH v2.0 ===
// Features NOT in CDP stealth. Runs via add_init_script AFTER CDP injection.
(function() {
'use strict';

// ═══════════════════════════════════════════════════════════════
// 1. NOTIFICATION API FULL MOCK
// CDP stealth only sets Notification.permission = 'default'.
// This provides a complete mock including constructor, requestPermission,
// maxActions, and instance methods — needed by advanced fingerprinters.
// ═══════════════════════════════════════════════════════════════
(function() {
    if (typeof Notification === 'undefined') return;
    var _realPermission = 'default';
    function FakeNotification(title, options) {
        this.title = title || '';
        this.body = '';
        this.tag = '';
        this.icon = '';
        this.data = null;
        this.close = function() {};
        this.addEventListener = function() {};
        this.removeEventListener = function() {};
        this.dispatchEvent = function() { return true; };
    }
    Object.defineProperty(FakeNotification, 'permission', {
        get: function() { return _realPermission; },
        configurable: true
    });
    Object.defineProperty(FakeNotification, 'maxActions', {
        get: function() { return 2; },
        configurable: true
    });
    FakeNotification.requestPermission = function requestPermission(callback) {
        if (typeof callback === 'function') {
            callback(_realPermission);
            return Promise.resolve(_realPermission);
        }
        return Promise.resolve(_realPermission);
    };
    FakeNotification.prototype.close = function() {};
    FakeNotification.prototype.addEventListener = function() {};
    FakeNotification.prototype.removeEventListener = function() {};
    FakeNotification.prototype.dispatchEvent = function() { return true; };
    window.Notification = FakeNotification;
})();

// ═══════════════════════════════════════════════════════════════
// 2. BATTERY API MOCK
// Headless Chromium doesn't expose BatteryManager.
// Real Chrome on desktop shows 'chargingchange' etc.
// ═══════════════════════════════════════════════════════════════
if (navigator.getBattery) {
    navigator.getBattery = function getBattery() {
        return Promise.resolve({
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1.0,
            addEventListener: function() {},
            removeEventListener: function() {},
            dispatchEvent: function() { return true; }
        });
    };
}

// ═══════════════════════════════════════════════════════════════
// 3. FONT ENUMERATION BLOCK
// Advanced fingerprinters enumerate installed fonts via
// document.fonts.check() or measuring element widths.
// We limit the font list to common system fonts.
// ═══════════════════════════════════════════════════════════════
if (document.fonts && document.fonts.forEach) {
    var _origFontsForEach = document.fonts.forEach;
    var _commonFonts = new Set([
        'Arial', 'Arial Black', 'Comic Sans MS', 'Courier New',
        'Georgia', 'Helvetica', 'Impact', 'Lucida Console',
        'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Verdana',
        'sans-serif', 'serif', 'monospace', 'cursive', 'fantasy'
    ]);
    document.fonts.forEach = function(callback, thisArg) {
        return _origFontsForEach.call(this, function(font) {
            if (_commonFonts.has(font.family)) {
                return callback.call(thisArg, font);
            }
        }, thisArg);
    };
}

// ═══════════════════════════════════════════════════════════════
// 4. BEACON API INTERCEPTION
// navigator.sendBeacon can be used for fingerprinting.
// We intercept and allow normal beacons but block fingerprinting URLs.
// ═══════════════════════════════════════════════════════════════
if (navigator.sendBeacon) {
    var _origSendBeacon = navigator.sendBeacon;
    navigator.sendBeacon = function sendBeacon(url, data) {
        var blockedPatterns = ['fingerprint', 'telemetry', 'beacon', 'analytics'];
        var urlLower = (url || '').toLowerCase();
        if (blockedPatterns.some(function(p) { return urlLower.includes(p); })) {
            return true; // Fake success
        }
        return _origSendBeacon.call(this, url, data);
    };
}

// ═══════════════════════════════════════════════════════════════
// 5. CHALLENGE DETECTION OBSERVER
// Detects when a Cloudflare/PerimeterX challenge page appears
// and signals the Agent-X server for automatic bypass.
// ═══════════════════════════════════════════════════════════════
(function() {
    var _challengeDetected = false;
    var _challengeKeywords = [
        'just a moment', 'checking your browser', 'please wait',
        'verify you are human', 'captcha', 'access denied',
        'please enable javascript', 'challenge-platform'
    ];

    function checkForChallenge() {
        if (_challengeDetected) return;
        var title = (document.title || '').toLowerCase();
        var body = (document.body && document.body.textContent || '').substring(0, 1000).toLowerCase();
        var combined = title + ' ' + body;
        for (var i = 0; i < _challengeKeywords.length; i++) {
            if (combined.indexOf(_challengeKeywords[i]) !== -1) {
                _challengeDetected = true;
                window.__agentOsChallengeDetected = true;
                window.__agentOsChallengeType = _challengeKeywords[i];
                break;
            }
        }
    }

    // Check on DOMContentLoaded and after short delays
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkForChallenge);
    } else {
        checkForChallenge();
    }
    setTimeout(checkForChallenge, 2000);
    setTimeout(checkForChallenge, 5000);

    // Also observe DOM changes for dynamic challenge injection
    if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(function() {
            if (!_challengeDetected) checkForChallenge();
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
        // Stop observing after 10 seconds to save resources
        setTimeout(function() { observer.disconnect(); }, 10000);
    }
})();

// ═══════════════════════════════════════════════════════════════
// 6. NAVIGATOR CONSISTENCY GUARD
// Ensures navigator properties stay consistent across page scripts.
// If a page script tries to re-define webdriver back to true,
// our override must survive.
// ═══════════════════════════════════════════════════════════════
try {
    var _origNavDefineProp = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    if (!_origNavDefineProp || _origNavDefineProp.get) {
        // Already overridden by CDP stealth — verify it stays
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: function() { return undefined; },
            configurable: true,
            enumerable: false
        });
    }
} catch(e) {}

})();
""";

# Backward compatibility alias — some code may still reference ANTI_DETECTION_JS
ANTI_DETECTION_JS = SUPPLEMENTARY_STEALTH_JS

BOT_DETECTION_URLS = [
    "recaptcha", "captcha", "hcaptcha", "turnstile",
    "perimeterx", "datadome", "cloudflare-challenge",
    "challenges.cloudflare.com",
    "cloudflare.com/cdn-cgi/challenge",
    "cloudflareinsights.com",
    "managed-challenge",
    "no-connection",
    "check-bot", "verify-human", "bot-detection",
    "akamai-bot", "imperva", "f5-bot",
    "distil", "shape-security", "kasada",
    "botmanager", "radar", "fingerprint",
    "arkoselabs", "funcaptcha", "threatmetrix",
    "iovation", "nethra", "sardine", "seon.io",
    "ipqualityscore", "fraudlabs",
]

# Script URL patterns to block entirely (return empty body)
BOT_DETECTION_SCRIPT_PATTERNS = [
    "recaptcha", "captcha", "botdetect", "fingerprint", "kasada", "perimeterx"
]

# ─── Fake Human Verification Responses ──────────────────────

FAKE_RESPONSES = {
    "recaptcha": {"success": True, "score": 0.95, "action": "login", "challenge_ts": "2026-04-08T12:00:00Z"},
    "captcha": {"status": "verified", "human": True, "score": 0.92},
    "perimeterx": {"status": 0, "uuid": "fake-uuid-agent-x", "vid": "fake-vid", "risk_score": 5},
    "datadome": {"status": 200, "headers": {"x-datadome": "pass"}, "cookie": "human-verified"},
    "cloudflare": {"success": True, "cf_clearance": "agent-x-clearance-token"},
    "bot-detection": {"human": True, "verified": True, "timestamp": 1700000000},
    "kasada": {"verified": True, "token": "agent-x-kasada-token"},
    "arkose": {"solved": True, "session_token": "agent-x-arkose-token"},
    "threatmetrix": {"org_id": "agent-x", "result": "pass", "risk_score": 5},
    "iovation": {"result": "pass", "confidence": 0.95},
    "sardine": {"decision": "approve", "risk_score": 10},
    "seon": {"fraud_score": 10, "decision": "approve"},
    "ipqualityscore": {"success": True, "fraud_score": 10, "message": "Low Risk"},
}


def handle_request_interception(url: str, resource_type: str):
    """
    Shared request handler for bot detection blocking.
    Returns (should_block: bool, fake_response: dict|None).

    Only blocks KNOWN detection endpoints, not any URL containing keywords.
    This prevents blocking legitimate pages that happen to contain words like
    "captcha" or "turnstile" in their content/path.
    """
    url_lower = url.lower()

    # Only block if the URL is a KNOWN detection endpoint
    # Check for specific detection domains/paths, not just keyword presence
    BLOCK_DOMAINS = [
        "google.com/recaptcha",
        "gstatic.com/recaptcha",
        "recaptcha.net",
        "hcaptcha.com",
        "challenges.cloudflare.com",
        "cloudflare.com/cdn-cgi/challenge",
        "captcha.px-cloud.net",
        "perimeterx.net",
        "cdn.perimeterx.net",
        "px-cdn.net",
        "px-client.net",
        "px-captcha.net",
        "captcha.geo.datadome",
        "js.datadome.co",
        "datadome.co",
        "incapdns.net",
        "_Incapsula_Resource",
        "shapesecurity.com",
        "kasada.io",
        "k-i.co",
        "arkoselabs.com",
        "funcaptcha.co",
        "funcaptcha.com",
        "threatmetrix.com",
        "nethra",
        "iovation.com",
        "sardine.com",
        "seon.io",
        "ipqualityscore.com",
        "fingerprintjs.com",
        "fpjs.io",
        "fingerprint.com",
        "botd.fpjs.io",
        "netacea.com",
        "reblaze.com",
    ]

    for domain in BLOCK_DOMAINS:
        if domain in url_lower:
            if "recaptcha" in url_lower or "gstatic.com/recaptcha" in url_lower:
                return True, FAKE_RESPONSES.get("recaptcha", {"human": True})
            elif "hcaptcha" in url_lower:
                return True, FAKE_RESPONSES.get("captcha", {"human": True})
            elif "cloudflare" in url_lower or "turnstile" in url_lower:
                return True, FAKE_RESPONSES.get("cloudflare", {"human": True})
            elif "perimeterx" in url_lower or "px-" in url_lower:
                return True, FAKE_RESPONSES.get("perimeterx", {"human": True})
            elif "datadome" in url_lower:
                return True, FAKE_RESPONSES.get("datadome", {"human": True})
            elif "kasada" in url_lower or "k-i.co" in url_lower:
                return True, FAKE_RESPONSES.get("kasada", {"human": True})
            elif "arkoselabs" in url_lower or "funcaptcha" in url_lower:
                return True, FAKE_RESPONSES.get("arkose", {"human": True})
            elif "threatmetrix" in url_lower or "nethra" in url_lower:
                return True, FAKE_RESPONSES.get("threatmetrix", {"human": True})
            elif "iovation" in url_lower:
                return True, FAKE_RESPONSES.get("iovation", {"human": True})
            elif "sardine" in url_lower:
                return True, FAKE_RESPONSES.get("sardine", {"human": True})
            elif "seon" in url_lower:
                return True, FAKE_RESPONSES.get("seon", {"human": True})
            elif "ipqualityscore" in url_lower:
                return True, FAKE_RESPONSES.get("ipqualityscore", {"human": True})
            elif "fingerprint" in url_lower or "fpjs" in url_lower or "botd" in url_lower:
                return True, {"human": True, "fingerprint": "blocked"}
            elif "netacea" in url_lower or "reblaze" in url_lower:
                return True, {"human": True}
            else:
                return True, {"human": True}

    # Block bot detection scripts by domain (not by keyword)
    if resource_type == "script":
        SCRIPT_BLOCK_DOMAINS = [
            "recaptcha",
            "hcaptcha",
            "botdetect",
            "perimeterx",
            "kasada",
            "datadome",
            "arkoselabs",
            "funcaptcha",
            "threatmetrix",
            "iovation",
            "sardine",
            "seon.io",
            "ipqualityscore",
            "fingerprintjs",
            "fpjs.io",
            "botd",
            "netacea",
            "reblaze",
        ]
        for pattern in SCRIPT_BLOCK_DOMAINS:
            if pattern in url_lower:
                return True, None  # Return empty body

    return False, None
