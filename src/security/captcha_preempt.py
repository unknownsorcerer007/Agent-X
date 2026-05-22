"""
Agent-OS CAPTCHA Preemption System
Detects and prevents captcha/bot detection BEFORE it loads.

Strategy: Don't wait for captchas to appear — detect the WARNING SIGNS
and shut down the page before detection can complete.

This works ALONGSIDE the existing CaptchaBypass (network-level blocking):
  Flow: Preemptor checks BEFORE navigation
        → CaptchaBypass blocks during navigation
        → Preemptor monitors after navigation

If CaptchaBypass fails and a captcha loads, Preemptor detects and shuts down.

Key components:
  - CaptchaPreemptor: Main class orchestrating all preemption logic
  - RiskAssessment: Pre-navigation URL risk evaluation
  - PreflightResult: Browser fingerprint safety check
  - MonitorHandle: Active monitoring session with shutdown capability
  - HealthStatus: Post-navigation page health evaluation
  - ShutdownResult: Graceful page shutdown outcome
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from src.security.captcha_bypass import CaptchaBypass

logger = logging.getLogger("agent-os.captcha-preempt")


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PreemptMode(str, Enum):
    AGGRESSIVE = "aggressive"   # Shut down on any detection
    MODERATE = "moderate"       # Try stealth first, shut down if fails
    PASSIVE = "passive"         # Log only, never shut down


class RecommendedAction(str, Enum):
    PROCEED = "proceed"
    STEALTH_MODE = "stealth_mode"
    ABORT = "abort"


@dataclass
class RiskAssessment:
    """Result of pre-navigation URL risk assessment."""
    risk_level: str                        # "low" / "medium" / "high" / "critical"
    detection_types: List[str] = field(default_factory=list)
    recommended_action: str = "proceed"    # "proceed" / "stealth_mode" / "abort"
    matched_patterns: List[str] = field(default_factory=list)
    domain_age_risk: str = "unknown"       # "new" / "established" / "unknown"
    known_captcha_site: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "detection_types": self.detection_types,
            "recommended_action": self.recommended_action,
            "matched_patterns": self.matched_patterns,
            "domain_age_risk": self.domain_age_risk,
            "known_captcha_site": self.known_captcha_site,
            "details": self.details,
        }


@dataclass
class PreflightResult:
    """Result of pre-flight browser fingerprint safety check."""
    safe: bool
    issues: List[str] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "safe": self.safe,
            "issues": self.issues,
            "fixes_applied": self.fixes_applied,
            "details": self.details,
        }


@dataclass
class DetectionEvent:
    """A single bot-detection event observed during monitoring."""
    event_type: str          # "dom_mutation", "js_check", "redirect", "network_request"
    severity: str            # "low", "medium", "high", "critical"
    details: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""         # Origin of the detection signal


@dataclass
class MonitorHandle:
    """Handle for an active monitoring session."""
    active: bool = True
    page_url: str = ""
    started_at: float = field(default_factory=time.time)
    events: List[DetectionEvent] = field(default_factory=list)
    shutdown_triggered: bool = False
    shutdown_reason: str = ""
    _monitor_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "page_url": self.page_url,
            "started_at": self.started_at,
            "event_count": len(self.events),
            "shutdown_triggered": self.shutdown_triggered,
            "shutdown_reason": self.shutdown_reason,
            "events": [
                {
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "details": e.details,
                    "timestamp": e.timestamp,
                }
                for e in self.events[-20:]  # Last 20 events
            ],
        }


@dataclass
class HealthStatus:
    """Result of page health check."""
    healthy: bool = True
    detection: Dict[str, Any] = field(default_factory=dict)
    action_taken: str = ""       # "none" / "page_shutdown" / "stealth_applied"
    check_time: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "detection": self.detection,
            "action_taken": self.action_taken,
            "check_time": self.check_time,
        }


@dataclass
class ShutdownResult:
    """Result of graceful page shutdown."""
    shutdown: bool = False
    reason: str = ""
    data_saved: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shutdown": self.shutdown,
            "reason": self.reason,
            "data_saved": self.data_saved,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 1),
        }


# ═══════════════════════════════════════════════════════════════
# KNOWN CAPTCHA-HEAVY SITES
# Sites that are known to always or frequently show captchas.
# ═══════════════════════════════════════════════════════════════

CAPTCHA_HEAVY_DOMAINS: Set[str] = {
    # Ticketing sites
    "ticketmaster.com", "livenation.com", "stubhub.com", "vivaticket.com",
    # Sneaker / limited drop sites
    "footlocker.com", "finishline.com", "nike.com", "adidas.com", "yeezysupply.com",
    # Gaming / account creation
    "epicgames.com", "store.steampowered.com", "blizzard.com", "riotgames.com",
    # Financial / crypto
    "coinbase.com", "binance.com", "kraken.com", "robinhood.com",
    # Social media (aggressive on signup)
    "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    # Government / verification
    "irs.gov", "ssa.gov", "dmv.org",
    # Streaming
    "hulu.com", "disneyplus.com",
    # Job boards (recaptcha on every application)
    "indeed.com", "glassdoor.com",
    # Travel
    "booking.com", "airbnb.com",
    # Marketplaces with aggressive bot protection
    "stockx.com", "goat.com", "ebay.com",
    # Legal / compliance
    "pacourts.us", "courtlistener.com",
}

# Recently-registered TLDs that are more likely to have aggressive bot detection
HIGH_RISK_TLDS: Set[str] = {
    ".xyz", ".top", ".club", ".online", ".site", ".live",
    ".shop", ".store", ".app", ".dev",
}

# Known challenge page URL patterns
CHALLENGE_URL_PATTERNS: List[re.Pattern] = [
    re.compile(r"challenges\.cloudflare\.com", re.IGNORECASE),
    re.compile(r"captcha", re.IGNORECASE),
    re.compile(r"challenge", re.IGNORECASE),
    re.compile(r"verify", re.IGNORECASE),
    re.compile(r"checkpoint", re.IGNORECASE),
    re.compile(r"human[_-]?verification", re.IGNORECASE),
    re.compile(r"bot[_-]?check", re.IGNORECASE),
    re.compile(r"access[_-]?denied", re.IGNORECASE),
    re.compile(r"security[_-]?check", re.IGNORECASE),
    re.compile(r"px-captcha", re.IGNORECASE),
    re.compile(r"datadome[_-]?captcha", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════
# JAVASCRIPT FOR EARLY DETECTION
# Injected via Page.addScriptToEvaluateOnNewDocument
# Monitors the page for early signs of bot detection
# ═══════════════════════════════════════════════════════════════

EARLY_DETECTION_JS = r"""
(function() {
'use strict';

// ═══════════════════════════════════════════════════════════════
// AGENT-OS EARLY BOT-DETECTION MONITOR v1.0
// Monitors for early signs of bot detection and reports them.
// ═══════════════════════════════════════════════════════════════

if (window.__agentOsMonitorActive) return;
window.__agentOsMonitorActive = true;

// Detection events buffer - read by Python side via page.evaluate()
window.__agentOsDetections = [];

function reportDetection(eventType, severity, details, source) {
    var evt = {
        eventType: eventType,
        severity: severity,
        details: details || '',
        source: source || '',
        timestamp: Date.now()
    };
    window.__agentOsDetections.push(evt);
    // Keep only last 100 events
    if (window.__agentOsDetections.length > 100) {
        window.__agentOsDetections.shift();
    }
    // Dispatch a custom event that Python can listen to via page.on('console', ...)
    // We use console.debug with a magic prefix so Python can filter
    console.debug('__AGENT_OS_DETECTION__:' + JSON.stringify(evt));
}

// -- 1. MONITOR document.createElement FOR CAPTCHA IFRAME CREATION --

var _origCreateElement = document.createElement.bind(document);
document.createElement = function(tagName) {
    var el = _origCreateElement.apply(document, arguments);
    var tag = (tagName || '').toLowerCase();

    if (tag === 'iframe') {
        // Monitor src attribute changes on the iframe
        var _origSetAttribute = el.setAttribute.bind(el);
        el.setAttribute = function(name, value) {
            var result = _origSetAttribute(name, value);
            if (name === 'src' && typeof value === 'string') {
                var val = value.toLowerCase();
                if (val.includes('recaptcha') || val.includes('hcaptcha') ||
                    val.includes('turnstile') || val.includes('challenges.cloudflare') ||
                    val.includes('funcaptcha') || val.includes('arkoselabs') ||
                    val.includes('captcha') || val.includes('px-captcha') ||
                    val.includes('datadome')) {
                    reportDetection('dom_mutation', 'critical',
                        'Captcha iframe created: ' + value.substring(0, 120),
                        'createElement(iframe).src');
                }
            }
            return result;
        };

        // Also monitor the src property directly via defineProperty
        try {
            var _srcDescriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'src');
            if (_srcDescriptor && _srcDescriptor.set) {
                var _origSrcSet = _srcDescriptor.set;
                Object.defineProperty(el, 'src', {
                    get: _srcDescriptor.get,
                    set: function(val) {
                        if (typeof val === 'string') {
                            var lval = val.toLowerCase();
                            if (lval.includes('recaptcha') || lval.includes('hcaptcha') ||
                                lval.includes('turnstile') || lval.includes('captcha') ||
                                lval.includes('challenges.cloudflare')) {
                                reportDetection('dom_mutation', 'critical',
                                    'Captcha iframe src set: ' + val.substring(0, 120),
                                    'iframe.src');
                            }
                        }
                        return _origSrcSet.call(this, val);
                    },
                    configurable: true,
                    enumerable: true
                });
            }
        } catch(e) {}
    }

    // Monitor script creation that loads detection libraries
    if (tag === 'script') {
        var _origScriptSetAttr = el.setAttribute ? el.setAttribute.bind(el) : null;
        if (_origScriptSetAttr) {
            el.setAttribute = function(name, value) {
                if (name === 'src' && typeof value === 'string') {
                    var val = value.toLowerCase();
                    var detectionLibs = [
                        'recaptcha', 'hcaptcha', 'turnstile', 'challenges.cloudflare',
                        'funcaptcha', 'arkoselabs', 'perimeterx', 'px-cdn', 'px-cloud',
                        'datadome', 'fingerprintjs', 'fpjs.io', 'botd',
                        'kasada', 'shapesecurity', 'imperva', 'akamai-bot',
                        'ipqualityscore', 'sardine', 'threatmetrix', 'iovation',
                        'netacea', 'reblaze'
                    ];
                    for (var i = 0; i < detectionLibs.length; i++) {
                        if (val.includes(detectionLibs[i])) {
                            reportDetection('dom_mutation', 'high',
                                'Detection script loaded: ' + value.substring(0, 120),
                                'createElement(script).src');
                            break;
                        }
                    }
                }
                return _origScriptSetAttr(name, value);
            };
        }
    }

    return el;
};

// -- 2. MUTATIONOBSERVER FOR DOM CHANGES INDICATING BOT CHALLENGE PAGES --

var _observerActive = false;
try {
    var observer = new MutationObserver(function(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var mutation = mutations[i];

            // Check added nodes
            var addedNodes = mutation.addedNodes;
            if (addedNodes) {
                for (var j = 0; j < addedNodes.length; j++) {
                    var node = addedNodes[j];
                    if (node.nodeType !== 1) continue; // Skip text nodes

                    var tagName = (node.tagName || '').toLowerCase();
                    var nodeId = (node.id || '').toLowerCase();
                    var nodeClass = (node.className || '').toString().toLowerCase();

                    // Detect captcha iframes
                    if (tagName === 'iframe') {
                        var src = (node.src || '').toLowerCase();
                        if (src.includes('recaptcha') || src.includes('hcaptcha') ||
                            src.includes('turnstile') || src.includes('captcha') ||
                            src.includes('challenges.cloudflare')) {
                            reportDetection('dom_mutation', 'critical',
                                'Captcha iframe added to DOM: ' + src.substring(0, 100),
                                'MutationObserver');
                        }
                    }

                    // Detect challenge page elements
                    if (nodeId.includes('captcha') || nodeId.includes('challenge') ||
                        nodeId.includes('cf-turnstile') || nodeId.includes('turnstile') ||
                        nodeId.includes('hcaptcha') || nodeId.includes('g-recaptcha') ||
                        nodeId.includes('px-captcha') || nodeId.includes('datadome')) {
                        reportDetection('dom_mutation', 'high',
                            'Challenge element added: id=' + nodeId.substring(0, 80),
                            'MutationObserver');
                    }

                    if (nodeClass.includes('captcha') || nodeClass.includes('challenge') ||
                        nodeClass.includes('cf-turnstile') || nodeClass.includes('hcaptcha') ||
                        nodeClass.includes('g-recaptcha') || nodeClass.includes('px-captcha')) {
                        reportDetection('dom_mutation', 'high',
                            'Challenge element added: class=' + nodeClass.substring(0, 80),
                            'MutationObserver');
                    }

                    // Check for hidden challenge divs (some frameworks add invisible divs)
                    if (node.getAttribute) {
                        var dataSitekey = node.getAttribute('data-sitekey');
                        if (dataSitekey) {
                            reportDetection('dom_mutation', 'high',
                                'Sitekey element detected: ' + dataSitekey.substring(0, 50),
                                'MutationObserver');
                        }
                    }
                }
            }
        }
    });

    // Start observing when DOM is ready
    function startObserving() {
        if (_observerActive) return;
        _observerActive = true;
        try {
            observer.observe(document.documentElement || document.body, {
                childList: true,
                subtree: true,
                attributes: false
            });
        } catch(e) {
            // Document not ready yet, retry
            _observerActive = false;
            if (document.readyState !== 'complete') {
                setTimeout(startObserving, 100);
            }
        }
    }

    if (document.body) {
        startObserving();
    } else {
        document.addEventListener('DOMContentLoaded', startObserving);
    }
} catch(e) {
    // MutationObserver not available - monitoring degraded
}

// -- 3. INTERCEPT window.location CHANGES TO KNOWN CHALLENGE URLs --

var _origPushState = history.pushState;
var _origReplaceState = history.replaceState;

function checkChallengeURL(url) {
    if (!url || typeof url !== 'string') return false;
    var lowerUrl = url.toLowerCase();
    var challengePatterns = [
        'challenges.cloudflare.com', '/challenge', '/captcha',
        '/verify', '/checkpoint', '/bot-check', '/security-check',
        'px-captcha', 'datadome/captcha', '/access-denied',
        'human-verification', '/bot-detection'
    ];
    for (var i = 0; i < challengePatterns.length; i++) {
        if (lowerUrl.includes(challengePatterns[i])) {
            return true;
        }
    }
    return false;
}

history.pushState = function(state, title, url) {
    if (url && checkChallengeURL(String(url))) {
        reportDetection('redirect', 'critical',
            'Navigation to challenge URL via pushState: ' + String(url).substring(0, 120),
            'history.pushState');
    }
    return _origPushState.apply(this, arguments);
};

history.replaceState = function(state, title, url) {
    if (url && checkChallengeURL(String(url))) {
        reportDetection('redirect', 'high',
            'Navigation to challenge URL via replaceState: ' + String(url).substring(0, 120),
            'history.replaceState');
    }
    return _origReplaceState.apply(this, arguments);
};

// -- 4. MONITOR XHR/FETCH REQUESTS TO DETECTION ENDPOINTS --

var _monitorFetch = window.fetch;
window.fetch = function(resource, init) {
    var url = '';
    if (typeof resource === 'string') {
        url = resource;
    } else if (resource && resource.url) {
        url = resource.url;
    }
    if (url) {
        var lowerUrl = url.toLowerCase();
        var detectionEndpoints = [
            'recaptcha', 'hcaptcha', 'turnstile', 'challenges.cloudflare',
            'perimeterx', 'px-cloud', 'px-cdn', 'px-client',
            'datadome', 'fingerprintjs', 'fpjs.io', 'botd',
            'kasada', 'shapesecurity', 'imperva', 'akamai',
            'ipqualityscore', 'sardine', 'threatmetrix', 'iovation',
            'netacea', 'reblaze', 'funcaptcha', 'arkoselabs'
        ];
        for (var i = 0; i < detectionEndpoints.length; i++) {
            if (lowerUrl.includes(detectionEndpoints[i])) {
                reportDetection('network_request', 'high',
                    'Fetch to detection endpoint: ' + url.substring(0, 120),
                    'fetch');
                break;
            }
        }
    }
    return _monitorFetch.apply(this, arguments);
};

var _monitorXhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    if (url && typeof url === 'string') {
        var lowerUrl = url.toLowerCase();
        var detectionEndpoints = [
            'recaptcha', 'hcaptcha', 'turnstile', 'challenges.cloudflare',
            'perimeterx', 'px-cloud', 'px-cdn', 'px-client',
            'datadome', 'fingerprintjs', 'fpjs.io', 'botd',
            'kasada', 'shapesecurity', 'imperva', 'akamai',
            'ipqualityscore', 'sardine', 'threatmetrix', 'iovation',
            'netacea', 'reblaze', 'funcaptcha', 'arkoselabs'
        ];
        for (var i = 0; i < detectionEndpoints.length; i++) {
            if (lowerUrl.includes(detectionEndpoints[i])) {
                reportDetection('network_request', 'high',
                    'XHR to detection endpoint: ' + url.substring(0, 120),
                    'XMLHttpRequest.open');
                break;
            }
        }
    }
    return _monitorXhrOpen.apply(this, arguments);
};

// -- 5. MONITOR navigator.webdriver ACCESS --

var _webdriverAccessCount = 0;
try {
    var _wdDescriptor = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    if (_wdDescriptor && _wdDescriptor.get) {
        var _origWdGet = _wdDescriptor.get;
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: function() {
                _webdriverAccessCount++;
                if (_webdriverAccessCount >= 2) {
                    reportDetection('js_check', 'medium',
                        'navigator.webdriver accessed ' + _webdriverAccessCount + ' times (possible detection script)',
                        'Navigator.prototype.webdriver');
                }
                return _origWdGet.call(this);
            },
            configurable: true,
            enumerable: false
        });
    }
} catch(e) {
    // Cannot override webdriver getter - may already be patched by stealth
}

// -- 6. MONITOR FOR KNOWN ANTI-BOT GLOBAL VARIABLES --

function checkAntiBotGlobals() {
    var knownGlobals = [
        '_pxAppId', 'PerimeterX', '_pxVid', '_pxUuid',
        'DataDome', 'ddjskey', 'ddoptions',
        'hcaptcha', 'grecaptcha',
        'turnstile', '_cf_chl_opt',
        'ArkoseEnforcement',
        'Kasada',
    ];
    for (var i = 0; i < knownGlobals.length; i++) {
        try {
            if (window[knownGlobals[i]] !== undefined) {
                reportDetection('js_check', 'high',
                    'Anti-bot global detected: ' + knownGlobals[i],
                    'global-scan');
            }
        } catch(e) {}
    }
}

// Run global checks periodically
setInterval(checkAntiBotGlobals, 2000);
setTimeout(checkAntiBotGlobals, 500);

})();
"""


# ═══════════════════════════════════════════════════════════════
# PAGE HEALTH CHECK JAVASCRIPT
# Checks the current page for signs of captcha/bot challenge
# ═══════════════════════════════════════════════════════════════

PAGE_HEALTH_CHECK_JS = r"""
() => {
    const result = {
        healthy: true,
        detections: [],
        page_url: window.location.href,
        page_title: document.title || '',
        timestamp: Date.now()
    };

    const html = document.documentElement ? document.documentElement.outerHTML.toLowerCase() : '';
    const title = (document.title || '').toLowerCase();
    const bodyText = document.body ? document.body.innerText.substring(0, 5000).toLowerCase() : '';

    // -- Cloudflare Challenge Page --
    const cfIndicators = [
        {pattern: 'just a moment', type: 'cloudflare_js_challenge'},
        {pattern: 'checking your browser', type: 'cloudflare_js_challenge'},
        {pattern: 'cf-challenge-running', type: 'cloudflare_managed'},
        {pattern: 'verify you are human', type: 'cloudflare_managed'},
        {pattern: 'performing security verification', type: 'cloudflare_managed'},
        {pattern: 'challenges.cloudflare.com', type: 'cloudflare_turnstile'},
        {pattern: 'cf-turnstile', type: 'cloudflare_turnstile'},
        {pattern: 'ddos protection by cloudflare', type: 'cloudflare_ddos'},
        {pattern: 'ray id', type: 'cloudflare_ray'},
    ];
    for (const ind of cfIndicators) {
        if (html.includes(ind.pattern) || title.includes(ind.pattern)) {
            result.healthy = false;
            result.detections.push({
                type: ind.type,
                confidence: 0.85,
                indicator: ind.pattern,
                source: 'page_content'
            });
        }
    }

    // -- reCAPTCHA --
    const recaptchaSelectors = [
        '.g-recaptcha', '[data-sitekey]', 'iframe[src*="recaptcha"]',
        'script[src*="recaptcha"]', '#g-recaptcha-response',
        'iframe[src*="google.com/recaptcha"]',
    ];
    for (const sel of recaptchaSelectors) {
        try {
            if (document.querySelector(sel)) {
                result.healthy = false;
                result.detections.push({
                    type: 'recaptcha',
                    confidence: 0.95,
                    selector: sel,
                    source: 'dom_selector'
                });
            }
        } catch(e) {}
    }

    // -- hCaptcha --
    const hcaptchaSelectors = [
        '.h-captcha', '[data-hcaptcha-sitekey]', 'iframe[src*="hcaptcha"]',
        'script[src*="hcaptcha"]', '#h-captcha-response',
    ];
    for (const sel of hcaptchaSelectors) {
        try {
            if (document.querySelector(sel)) {
                result.healthy = false;
                result.detections.push({
                    type: 'hcaptcha',
                    confidence: 0.95,
                    selector: sel,
                    source: 'dom_selector'
                });
            }
        } catch(e) {}
    }

    // -- Turnstile --
    const turnstileSelectors = [
        '.cf-turnstile', 'iframe[src*="challenges.cloudflare"]',
        'script[src*="challenges.cloudflare"]', 'script[src*="turnstile"]',
        '[name="cf-turnstile-response"]',
    ];
    for (const sel of turnstileSelectors) {
        try {
            if (document.querySelector(sel)) {
                const alreadyDetected = result.detections.some(d => d.type === 'turnstile');
                if (!alreadyDetected) {
                    result.healthy = false;
                    result.detections.push({
                        type: 'turnstile',
                        confidence: 0.95,
                        selector: sel,
                        source: 'dom_selector'
                    });
                }
            }
        } catch(e) {}
    }

    // -- PerimeterX --
    const pxIndicators = [
        {pattern: 'px-captcha', type: 'perimeterx_captcha'},
        {pattern: '_px', type: 'perimeterx'},
        {pattern: 'captcha.px-cloud', type: 'perimeterx_captcha'},
    ];
    for (const ind of pxIndicators) {
        if (html.includes(ind.pattern) || title.includes(ind.pattern)) {
            result.healthy = false;
            result.detections.push({
                type: ind.type,
                confidence: 0.85,
                indicator: ind.pattern,
                source: 'page_content'
            });
        }
    }

    // -- DataDome --
    const ddIndicators = [
        {pattern: 'datadome', type: 'datadome'},
        {pattern: 'ddjskey', type: 'datadome_js'},
    ];
    for (const ind of ddIndicators) {
        if (html.includes(ind.pattern)) {
            result.healthy = false;
            result.detections.push({
                type: ind.type,
                confidence: 0.80,
                indicator: ind.pattern,
                source: 'page_content'
            });
        }
    }

    // -- "Access Denied" / "Verify Human" Text --
    const denyTexts = [
        'access denied', 'you have been blocked', 'please verify you are human',
        'are you a robot', 'are you human', 'bot detected',
        'unusual traffic', 'automated requests', 'verify your identity',
        'human verification required', 'prove you are human',
        'your request was denied', 'request blocked',
    ];
    for (const txt of denyTexts) {
        if (bodyText.includes(txt) || title.includes(txt)) {
            result.healthy = false;
            result.detections.push({
                type: 'access_denied',
                confidence: 0.75,
                indicator: txt,
                source: 'page_text'
            });
        }
    }

    // -- Check URL for challenge patterns --
    const urlLower = window.location.href.toLowerCase();
    const urlPatterns = [
        {pattern: '/challenge', type: 'challenge_url'},
        {pattern: '/captcha', type: 'captcha_url'},
        {pattern: '/verify', type: 'verify_url'},
        {pattern: '/checkpoint', type: 'checkpoint_url'},
        {pattern: '/bot-check', type: 'bot_check_url'},
        {pattern: '/access-denied', type: 'access_denied_url'},
        {pattern: 'challenges.cloudflare.com', type: 'cf_challenge_url'},
    ];
    for (const p of urlPatterns) {
        if (urlLower.includes(p.pattern)) {
            result.healthy = false;
            result.detections.push({
                type: p.type,
                confidence: 0.90,
                indicator: p.pattern,
                source: 'page_url'
            });
        }
    }

    // -- Check HTTP status via meta tags or error pages --
    if (title.includes('403') || title.includes('503') || title.includes('429')) {
        result.healthy = false;
        result.detections.push({
            type: 'error_status',
            confidence: 0.60,
            indicator: 'Error status in title: ' + title,
            source: 'page_title'
        });
    }

    return result;
}
"""

# ═══════════════════════════════════════════════════════════════
# DATA RESCUE JAVASCRIPT
# Tries to save important data from the page before shutdown
# ═══════════════════════════════════════════════════════════════

DATA_RESCUE_JS = r"""
() => {
    const rescued = [];

    try {
        // Page URL
        rescued.push({type: 'url', data: window.location.href});

        // Page title
        rescued.push({type: 'title', data: document.title});

        // Form data (inputs that have values)
        const inputs = document.querySelectorAll('input, textarea, select');
        const formData = {};
        inputs.forEach(function(el) {
            if (el.name && el.value) {
                formData[el.name] = el.value.substring(0, 500);
            }
        });
        if (Object.keys(formData).length > 0) {
            rescued.push({type: 'form_data', data: formData});
        }

        // Visible text (first 2000 chars)
        if (document.body) {
            const text = document.body.innerText.substring(0, 2000);
            if (text.trim().length > 0) {
                rescued.push({type: 'page_text', data: text});
            }
        }

        // LocalStorage data (non-sensitive keys)
        try {
            const lsData = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && !key.toLowerCase().includes('token') &&
                    !key.toLowerCase().includes('password') &&
                    !key.toLowerCase().includes('secret') &&
                    !key.toLowerCase().includes('key')) {
                    lsData[key] = localStorage.getItem(key).substring(0, 500);
                }
            }
            if (Object.keys(lsData).length > 0) {
                rescued.push({type: 'local_storage', data: lsData});
            }
        } catch(e) {}

        // Cookies
        try {
            rescued.push({type: 'cookies', data: document.cookie});
        } catch(e) {}

    } catch(e) {
        rescued.push({type: 'error', data: 'Rescue error: ' + e.message});
    }

    return rescued;
}
"""


# ═══════════════════════════════════════════════════════════════
# CAPTCHA PREEMPTOR - Main Class
# ═══════════════════════════════════════════════════════════════

class CaptchaPreemptor:
    """
    Preemptive anti-bot/captcha detection and page shutdown system.

    Detects and prevents captcha/bot detection BEFORE it loads.
    Works alongside CaptchaBypass (network-level blocking):

        Flow: Preemptor assesses BEFORE navigation
              -> CaptchaBypass blocks during navigation
              -> Preemptor monitors after navigation

    Configuration:
        preempt_mode: "aggressive" / "moderate" / "passive"
        shutdown_timeout: Seconds before forcing shutdown (default 2s)
        data_rescue: Whether to save page data before shutdown (default True)
        monitor_interval: How often to poll for bot detection (default 500ms)
    """

    def __init__(
        self,
        captcha_bypass: Optional[CaptchaBypass] = None,
        preempt_mode: str = "moderate",
        shutdown_timeout: float = 2.0,
        data_rescue: bool = True,
        monitor_interval: float = 0.5,
    ):
        # Use provided CaptchaBypass or create a default one
        self._bypass = captcha_bypass or CaptchaBypass()

        # Configuration
        self._mode = PreemptMode(preempt_mode)
        self._shutdown_timeout = shutdown_timeout
        self._data_rescue = data_rescue
        self._monitor_interval = monitor_interval

        # State
        self._active_monitors: Dict[str, MonitorHandle] = {}
        self._monitor_lock = asyncio.Lock()
        self._detection_script_injected: Set[str] = set()  # page_id set

        # Statistics
        self._stats: Dict[str, Any] = {
            "urls_assessed": 0,
            "preflights_run": 0,
            "monitors_started": 0,
            "health_checks": 0,
            "shutdowns": 0,
            "shutdowns_by_reason": {},
            "detections_by_type": {},
        }

    # -- CONFIGURATION -----------------------------------------

    @property
    def mode(self) -> str:
        return self._mode.value

    @mode.setter
    def mode(self, value: str):
        self._mode = PreemptMode(value)

    @property
    def config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "preempt_mode": self._mode.value,
            "shutdown_timeout": self._shutdown_timeout,
            "data_rescue": self._data_rescue,
            "monitor_interval": self._monitor_interval,
        }

    def update_config(self, **kwargs) -> Dict[str, Any]:
        """Update configuration parameters.

        Returns:
            {"status": "success", "config": {...}} with updated config.
        """
        if "preempt_mode" in kwargs:
            self._mode = PreemptMode(kwargs["preempt_mode"])
        if "shutdown_timeout" in kwargs:
            self._shutdown_timeout = float(kwargs["shutdown_timeout"])
        if "data_rescue" in kwargs:
            self._data_rescue = bool(kwargs["data_rescue"])
        if "monitor_interval" in kwargs:
            self._monitor_interval = float(kwargs["monitor_interval"])

        return {"status": "success", "config": self.config}

    # -- 1. PRE-NAVIGATION RISK ASSESSMENT ---------------------

    def assess_url_risk(self, url: str) -> RiskAssessment:
        """Assess the risk of navigating to a URL.

        Checks the URL against:
        - Known bot-detection domains (reuses patterns from CaptchaBypass)
        - CAPTCHA-heavy site lists
        - URL age/reputation heuristics
        - Challenge URL patterns

        Args:
            url: The URL to assess.

        Returns:
            RiskAssessment with risk_level, detection_types, and recommended_action.
        """
        self._stats["urls_assessed"] += 1

        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            path = (parsed.path or "").lower()
            full_match_target = hostname + path

            detection_types: List[str] = []
            matched_patterns: List[str] = []
            domain_age_risk = "unknown"
            known_captcha_site = False

            # -- Check against CaptchaBypass detection patterns --
            bypass_result = self._bypass.detect(url)
            if bypass_result:
                detection_types.append(bypass_result)
                matched_patterns.append(f"bypass:{bypass_result}")

            # -- Check against CAPTCHA-heavy domains --
            domain_parts = hostname.split(".")
            for i in range(len(domain_parts)):
                candidate = ".".join(domain_parts[i:])
                if candidate in CAPTCHA_HEAVY_DOMAINS:
                    known_captcha_site = True
                    detection_types.append("captcha_heavy_site")
                    matched_patterns.append(f"heavy_domain:{candidate}")
                    break

            # -- Check domain age/reputation --
            tld = "." + domain_parts[-1] if domain_parts else ""
            if tld in HIGH_RISK_TLDS:
                domain_age_risk = "new"
                detection_types.append("high_risk_tld")
                matched_patterns.append(f"tld:{tld}")
            elif len(domain_parts) == 2 and hostname not in CAPTCHA_HEAVY_DOMAINS:
                domain_age_risk = "unknown"
            else:
                domain_age_risk = "established"

            # -- Check URL path for challenge patterns --
            for pattern in CHALLENGE_URL_PATTERNS:
                if pattern.search(full_match_target):
                    detection_types.append("challenge_url_pattern")
                    matched_patterns.append(f"url_pattern:{pattern.pattern}")
                    break

            # -- Determine risk level and recommended action --
            risk_level = RiskLevel.LOW.value
            recommended_action = RecommendedAction.PROCEED.value

            if detection_types:
                critical_types = {"captcha_heavy_site", "challenge_url_pattern"}
                high_types = {
                    "cloudflare", "perimeterx", "datadome", "imperva",
                    "akamai", "kasada", "fingerprint",
                }
                medium_types = {
                    "recaptcha", "hcaptcha", "turnstile", "arkose",
                    "high_risk_tld",
                }

                has_critical = bool(critical_types & set(detection_types))
                has_high = bool(high_types & set(detection_types))
                has_medium = bool(medium_types & set(detection_types))

                if has_critical or len(detection_types) >= 3:
                    risk_level = RiskLevel.CRITICAL.value
                    recommended_action = RecommendedAction.ABORT.value
                elif has_high or len(detection_types) >= 2:
                    risk_level = RiskLevel.HIGH.value
                    recommended_action = RecommendedAction.STEALTH_MODE.value
                elif has_medium:
                    risk_level = RiskLevel.MEDIUM.value
                    recommended_action = RecommendedAction.STEALTH_MODE.value
                else:
                    risk_level = RiskLevel.MEDIUM.value
                    recommended_action = RecommendedAction.PROCEED.value

                # Known captcha-heavy sites are always at least medium
                if known_captcha_site and risk_level == RiskLevel.LOW.value:
                    risk_level = RiskLevel.MEDIUM.value
                    recommended_action = RecommendedAction.STEALTH_MODE.value

            assessment = RiskAssessment(
                risk_level=risk_level,
                detection_types=list(set(detection_types)),
                recommended_action=recommended_action,
                matched_patterns=matched_patterns,
                domain_age_risk=domain_age_risk,
                known_captcha_site=known_captcha_site,
                details={
                    "hostname": hostname,
                    "path": path,
                    "bypass_detection": bypass_result,
                },
            )

            # Update stats
            for dt in detection_types:
                self._stats["detections_by_type"][dt] = \
                    self._stats["detections_by_type"].get(dt, 0) + 1

            logger.info(
                f"URL risk assessment: {url[:80]} -> {risk_level} "
                f"(types: {detection_types}, action: {recommended_action})"
            )

            return assessment

        except Exception as e:
            logger.error(f"URL risk assessment failed for {url[:60]}: {e}")
            return RiskAssessment(
                risk_level=RiskLevel.MEDIUM.value,
                detection_types=["assessment_error"],
                recommended_action=RecommendedAction.STEALTH_MODE.value,
                details={"error": str(e)},
            )

    # -- 2. PRE-FLIGHT CHECK -----------------------------------

    async def preflight_check(self, page) -> PreflightResult:
        """Run a pre-flight check on the browser fingerprint.

        Tests whether the current browser fingerprint will likely be detected
        by bot detection scripts. Checks navigator.webdriver, chrome.csi,
        plugins consistency, and other common detection vectors.

        Args:
            page: Playwright/Patchright Page object.

        Returns:
            PreflightResult with safe flag, issues list, and fixes applied.
        """
        self._stats["preflights"] += 1

        issues: List[str] = []
        fixes_applied: List[str] = []
        details: Dict[str, Any] = {}

        try:
            # -- Check navigator.webdriver --
            webdriver_result = await page.evaluate(
                "() => navigator.webdriver"
            )
            if webdriver_result is not None and webdriver_result is not False:
                issues.append("navigator.webdriver is detectable")
                details["webdriver_value"] = webdriver_result

                # Attempt fix
                try:
                    await page.evaluate("""
                        () => {
                            try {
                                delete Navigator.prototype.webdriver;
                            } catch(e) {}
                            Object.defineProperty(Navigator.prototype, 'webdriver', {
                                get: function() { return undefined; },
                                configurable: true,
                                enumerable: false
                            });
                        }
                    """)
                    fixes_applied.append("navigator.webdriver set to undefined")
                except Exception as fix_err:
                    logger.debug(f"Could not fix navigator.webdriver: {fix_err}")

            # -- Check chrome.csi existence --
            csi_result = await page.evaluate(
                "() => typeof window.chrome !== 'undefined' && typeof window.chrome.csi === 'function'"
            )
            if not csi_result:
                issues.append("chrome.csi is missing (headless indicator)")
                details["chrome_csi_present"] = False

                # Attempt fix
                try:
                    await page.evaluate("""
                        () => {
                            window.chrome = window.chrome || {};
                            window.chrome.csi = function() {
                                return {
                                    onloadT: Date.now(),
                                    pageT: Date.now(),
                                    startE: Date.now()
                                };
                            };
                        }
                    """)
                    fixes_applied.append("chrome.csi injected")
                except Exception as fix_err:
                    logger.debug(f"Could not fix chrome.csi: {fix_err}")

            # -- Check chrome.loadTimes existence --
            loadtimes_result = await page.evaluate(
                "() => typeof window.chrome !== 'undefined' && typeof window.chrome.loadTimes === 'function'"
            )
            if not loadtimes_result:
                issues.append("chrome.loadTimes is missing (headless indicator)")
                details["chrome_loadtimes_present"] = False

                try:
                    await page.evaluate("""
                        () => {
                            window.chrome = window.chrome || {};
                            window.chrome.loadTimes = function() {
                                const n = Date.now() / 1000;
                                return {
                                    commitLoadTime: n,
                                    connectionInfo: 'h2',
                                    finishDocumentLoadTime: n,
                                    finishLoadTime: n,
                                    firstPaintAfterLoadTime: 0,
                                    firstPaintTime: n,
                                    npnNegotiatedProtocol: 'h2',
                                    requestTime: n,
                                    startLoadTime: n,
                                    wasAlternateProtocolAvailable: false,
                                    wasFetchedViaSpdy: true,
                                    wasNpnNegotiated: true
                                };
                            };
                        }
                    """)
                    fixes_applied.append("chrome.loadTimes injected")
                except Exception as fix_err:
                    logger.debug(f"Could not fix chrome.loadTimes: {fix_err}")

            # -- Check navigator.plugins --
            plugins_result = await page.evaluate("""
                () => {
                    const plugins = navigator.plugins;
                    return {
                        length: plugins ? plugins.length : 0,
                        names: plugins
                            ? Array.from({length: Math.min(plugins.length, 5)},
                                (_, i) => plugins[i] ? plugins[i].name : 'unknown')
                            : []
                    };
                }
            """)
            if plugins_result and plugins_result.get("length", 0) == 0:
                issues.append("navigator.plugins is empty (headless indicator)")
                details["plugins_empty"] = True

                try:
                    await page.evaluate("""
                        () => {
                            const fakePlugins = [
                                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer',
                                 description:'Portable Document Format', length:1},
                                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                                 description:'', length:1},
                                {name:'Native Client', filename:'internal-nacl-plugin',
                                 description:'', length:2}
                            ];
                            fakePlugins.length = 3;
                            fakePlugins.item = function(i) { return this[i] || null; };
                            fakePlugins.namedItem = function(n) {
                                return this.find(x => x.name === n) || null;
                            };
                            fakePlugins.refresh = function() {};
                            Object.defineProperty(navigator, 'plugins', {
                                get: function() { return fakePlugins; },
                                configurable: true,
                                enumerable: true
                            });
                        }
                    """)
                    fixes_applied.append("navigator.plugins populated")
                except Exception as fix_err:
                    logger.debug(f"Could not fix navigator.plugins: {fix_err}")

            # -- Check automation artifact properties --
            artifacts_result = await page.evaluate("""
                () => {
                    const artifacts = [
                        '__selenium_unwrapped', '__selenium_evaluate',
                        '__webdriver_evaluate', '__driver_evaluate',
                        '__fxdriver_evaluate', '__nightmare', '_phantom',
                        'callPhantom', '_Selenium_IDE_Recorder',
                        'cdc_adoQpoasnfa76pfcZLmcfl_Array',
                        'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
                        '__playwright', '__pw_manual'
                    ];
                    const found = artifacts.filter(p => window[p] !== undefined);
                    return found;
                }
            """)
            if artifacts_result and len(artifacts_result) > 0:
                issues.append(
                    f"Automation artifacts detected: {', '.join(artifacts_result[:5])}"
                )
                details["automation_artifacts"] = artifacts_result

                # Attempt to clean up
                try:
                    await page.evaluate("""
                        (artifactNames) => {
                            for (const name of artifactNames) {
                                try { delete window[name]; } catch(e) {
                                    Object.defineProperty(window, name, {
                                        get: () => undefined, configurable: true
                                    });
                                }
                            }
                        }
                    """, artifacts_result)
                    fixes_applied.append(
                        f"Removed {len(artifacts_result)} automation artifacts"
                    )
                except Exception as fix_err:
                    logger.debug(f"Could not clean automation artifacts: {fix_err}")

            # -- Determine overall safety --
            safe = len(issues) == 0 or len(fixes_applied) >= len(issues)

            # If we're in aggressive mode, any unfixed issue means not safe
            if self._mode == PreemptMode.AGGRESSIVE:
                unfixed = len(issues) - len(fixes_applied)
                if unfixed > 0:
                    safe = False

            result = PreflightResult(
                safe=safe,
                issues=issues,
                fixes_applied=fixes_applied,
                details=details,
            )

            logger.info(
                f"Preflight check: safe={safe}, issues={len(issues)}, "
                f"fixes={len(fixes_applied)}"
            )

            return result

        except Exception as e:
            logger.error(f"Preflight check failed: {e}")
            return PreflightResult(
                safe=False,
                issues=[f"preflight_error: {str(e)}"],
                fixes_applied=[],
                details={"error": str(e)},
            )

    # -- 3. EARLY BOT DETECTION MONITOR -------------------------

    async def start_monitoring(
        self,
        page,
        page_id: str = "main",
        on_detection: Optional[Callable] = None,
    ) -> MonitorHandle:
        """Start monitoring a page for early signs of bot detection.

        Monitors:
        - DOM mutations that add captcha iframes
        - JavaScript that checks navigator.webdriver
        - Redirects to challenge pages (Cloudflare, PerimeterX, etc.)
        - XHR/fetch requests to detection endpoints

        When detection is imminent and in aggressive/moderate mode,
        triggers immediate page shutdown.

        Args:
            page: Playwright/Patchright Page object.
            page_id: Unique identifier for this page.
            on_detection: Optional callback invoked on detection events.
                         Receives (page_id: str, event: DetectionEvent).

        Returns:
            MonitorHandle for the active monitoring session.
        """
        self._stats["monitors_started"] += 1

        try:
            async with self._monitor_lock:
                # Stop existing monitor for this page if any
                existing = self._active_monitors.get(page_id)
                if existing and existing.active:
                    await self._stop_monitor_internal(existing)

                handle = MonitorHandle(
                    active=True,
                    page_url=page.url if hasattr(page, "url") else "",
                )

                # Inject early detection JavaScript via CDP if possible
                if page_id not in self._detection_script_injected:
                    try:
                        cdp = await page.context.new_cdp_session(page)
                        try:
                            await cdp.send(
                                "Page.addScriptToEvaluateOnNewDocument",
                                {"source": EARLY_DETECTION_JS},
                            )
                        finally:
                            try:
                                await cdp.detach()
                            except Exception:
                                pass
                        self._detection_script_injected.add(page_id)
                    except Exception:
                        # Fallback: inject via page.evaluate
                        try:
                            await page.evaluate(EARLY_DETECTION_JS)
                            self._detection_script_injected.add(page_id)
                        except Exception as eval_err:
                            logger.warning(
                                f"Could not inject early detection JS: {eval_err}"
                            )

                # Set up console listener for detection events
                detection_queue: asyncio.Queue = asyncio.Queue()

                def on_console(msg):
                    try:
                        text = msg.text if hasattr(msg, "text") else str(msg)
                        if text.startswith("__AGENT_OS_DETECTION__:"):
                            payload = text[len("__AGENT_OS_DETECTION__:"):]
                            try:
                                evt_data = json.loads(payload)
                                detection = DetectionEvent(
                                    event_type=evt_data.get("eventType", "unknown"),
                                    severity=evt_data.get("severity", "low"),
                                    details=evt_data.get("details", ""),
                                    timestamp=evt_data.get("timestamp", time.time()),
                                    source=evt_data.get("source", ""),
                                )
                                detection_queue.put_nowait(detection)
                            except (json.JSONDecodeError, KeyError):
                                pass
                    except Exception:
                        pass

                try:
                    page.on("console", on_console)
                except Exception:
                    pass

                # Also listen for navigation events to challenge pages
                def on_navigation(frame):
                    try:
                        url = frame.url if hasattr(frame, "url") else ""
                        for pattern in CHALLENGE_URL_PATTERNS:
                            if pattern.search(url.lower()):
                                detection_queue.put_nowait(DetectionEvent(
                                    event_type="redirect",
                                    severity="critical",
                                    details=f"Navigation to challenge URL: {url[:120]}",
                                    source="frame_navigation",
                                ))
                                break
                    except Exception:
                        pass

                try:
                    page.on("framenavigated", on_navigation)
                except Exception:
                    pass

                # Create the monitoring task
                monitor_task = asyncio.create_task(
                    self._monitor_loop(
                        page=page,
                        page_id=page_id,
                        handle=handle,
                        detection_queue=detection_queue,
                        on_detection=on_detection,
                    )
                )
                handle._monitor_task = monitor_task

                self._active_monitors[page_id] = handle

                logger.info(
                    f"Monitoring started for page '{page_id}' "
                    f"(mode: {self._mode.value})"
                )

                return handle

        except Exception as e:
            logger.error(f"Failed to start monitoring for page '{page_id}': {e}")
            return MonitorHandle(
                active=False,
                page_url="",
                shutdown_reason=f"monitor_start_error: {str(e)}",
            )

    async def _monitor_loop(
        self,
        page,
        page_id: str,
        handle: MonitorHandle,
        detection_queue: asyncio.Queue,
        on_detection: Optional[Callable],
    ):
        """Internal monitoring loop that processes detection events."""
        consecutive_critical = 0
        consecutive_high = 0

        while handle.active and not handle._stop_event.is_set():
            try:
                # Poll detection events from the queue
                try:
                    event = await asyncio.wait_for(
                        detection_queue.get(),
                        timeout=self._monitor_interval,
                    )
                except asyncio.TimeoutError:
                    # No event in this interval - do a periodic health check
                    # by reading the JS-side detection buffer
                    try:
                        js_detections = await page.evaluate(
                            "() => window.__agentOsDetections || []"
                        )
                        if js_detections:
                            for evt_data in js_detections[-5:]:
                                event = DetectionEvent(
                                    event_type=evt_data.get("eventType", "unknown"),
                                    severity=evt_data.get("severity", "low"),
                                    details=evt_data.get("details", ""),
                                    timestamp=evt_data.get("timestamp", time.time()),
                                    source=evt_data.get("source", ""),
                                )
                                handle.events.append(event)

                            # Clear the JS buffer
                            await page.evaluate(
                                "() => { window.__agentOsDetections = []; }"
                            )
                    except Exception:
                        pass

                    continue

                # Process the detection event
                handle.events.append(event)

                # Notify callback
                if on_detection:
                    try:
                        if asyncio.iscoroutinefunction(on_detection):
                            await on_detection(page_id, event)
                        else:
                            on_detection(page_id, event)
                    except Exception as cb_err:
                        logger.debug(f"Detection callback error: {cb_err}")

                # Track severity
                if event.severity == "critical":
                    consecutive_critical += 1
                    consecutive_high = 0
                elif event.severity == "high":
                    consecutive_high += 1
                    consecutive_critical = 0
                else:
                    # Reset counters on low/medium events
                    consecutive_critical = 0
                    consecutive_high = 0

                # Decide whether to trigger shutdown
                should_shutdown = False
                shutdown_reason = ""

                if self._mode == PreemptMode.AGGRESSIVE:
                    # Any high or critical event triggers shutdown
                    if event.severity in ("high", "critical"):
                        should_shutdown = True
                        shutdown_reason = (
                            f"aggressive_mode: {event.event_type} "
                            f"detection ({event.details[:80]})"
                        )

                elif self._mode == PreemptMode.MODERATE:
                    # Two or more high/critical events triggers shutdown
                    if consecutive_critical >= 1:
                        should_shutdown = True
                        shutdown_reason = (
                            f"moderate_mode: critical detection "
                            f"({event.details[:80]})"
                        )
                    elif consecutive_high >= 2:
                        should_shutdown = True
                        shutdown_reason = (
                            f"moderate_mode: repeated high detections "
                            f"({event.details[:80]})"
                        )

                # PASSIVE mode: never shut down, just log

                if should_shutdown:
                    handle.shutdown_triggered = True
                    handle.shutdown_reason = shutdown_reason
                    handle.active = False

                    logger.warning(
                        f"Bot detection imminent on page '{page_id}': "
                        f"{shutdown_reason}"
                    )

                    # Perform page shutdown
                    shutdown_result = await self.shutdown_page(
                        page, reason=shutdown_reason
                    )

                    # Update stats
                    self._stats["shutdowns"] += 1
                    self._stats["shutdowns_by_reason"][event.event_type] = \
                        self._stats["shutdowns_by_reason"].get(
                            event.event_type, 0
                        ) + 1

                    return

            except Exception as e:
                # Check if the page is still alive
                error_str = str(e).lower()
                if any(kw in error_str for kw in [
                    "page crashed", "target closed",
                    "context was destroyed", "disconnected",
                    "session deleted",
                ]):
                    handle.active = False
                    logger.debug(
                        f"Monitor for page '{page_id}' stopped: page gone"
                    )
                    return

                logger.debug(
                    f"Monitor loop error for page '{page_id}': {e}"
                )
                await asyncio.sleep(self._monitor_interval)

    async def stop_monitoring(self, page_id: str) -> Dict[str, Any]:
        """Stop monitoring a page.

        Args:
            page_id: The page identifier to stop monitoring.

        Returns:
            {"status": "success", "handle": ...} with final monitor state.
        """
        try:
            async with self._monitor_lock:
                handle = self._active_monitors.pop(page_id, None)
                if handle:
                    await self._stop_monitor_internal(handle)
                    return {"status": "success", "handle": handle.to_dict()}
                else:
                    return {
                        "status": "error",
                        "error": f"No active monitor for page '{page_id}'",
                    }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _stop_monitor_internal(self, handle: MonitorHandle):
        """Internal: stop a monitor handle."""
        handle.active = False
        handle._stop_event.set()
        if handle._monitor_task and not handle._monitor_task.done():
            handle._monitor_task.cancel()
            try:
                await handle._monitor_task
            except asyncio.CancelledError:
                pass

    # -- 4. PAGE HEALTH CHECK ----------------------------------

    async def check_page_health(self, page) -> HealthStatus:
        """Check if a page has a captcha/bot challenge loaded.

        Detects:
        - Cloudflare challenge page
        - reCAPTCHA iframe
        - hCaptcha
        - Turnstile
        - "Access Denied" pages
        - "Please verify you are human" text

        If detected in aggressive or moderate mode, immediately shuts down
        the page.

        Args:
            page: Playwright/Patchright Page object.

        Returns:
            HealthStatus with healthy flag and detection details.
        """
        self._stats["health_checks"] += 1

        try:
            result = await page.evaluate(PAGE_HEALTH_CHECK_JS)

            healthy = result.get("healthy", True)
            detections = result.get("detections", [])

            health = HealthStatus(
                healthy=healthy,
                detection={
                    "detections": detections,
                    "page_url": result.get("page_url", ""),
                    "page_title": result.get("page_title", ""),
                    "count": len(detections),
                },
            )

            # If not healthy and not in passive mode, shut down
            if not healthy and self._mode != PreemptMode.PASSIVE:
                # Determine the primary detection type for the reason
                primary = detections[0] if detections else {}
                det_type = primary.get("type", "unknown")
                det_indicator = primary.get(
                    "indicator", primary.get("selector", "")
                )

                reason = (
                    f"Health check failed: {det_type}"
                    f"{' (' + det_indicator[:60] + ')' if det_indicator else ''}"
                )

                logger.warning(f"Page unhealthy, shutting down: {reason}")

                shutdown_result = await self.shutdown_page(page, reason=reason)

                health.action_taken = "page_shutdown"
                health.detection["shutdown_result"] = shutdown_result.to_dict()

                # Update stats
                self._stats["shutdowns"] += 1
                self._stats["shutdowns_by_reason"][det_type] = \
                    self._stats["shutdowns_by_reason"].get(det_type, 0) + 1
            else:
                health.action_taken = "none"

            return health

        except Exception as e:
            logger.error(f"Page health check failed: {e}")
            return HealthStatus(
                healthy=False,
                detection={"error": str(e)},
                action_taken="none",
            )

    # -- 5. GRACEFUL PAGE SHUTDOWN -----------------------------

    async def shutdown_page(
        self, page, reason: str = ""
    ) -> ShutdownResult:
        """Gracefully close a page that has been detected as bot-challenged.

        Steps:
        1. Try to save any important data from the page first
        2. Stop all network requests
        3. Navigate to about:blank
        4. Close the page
        5. If page is part of a tab, close the tab
        6. Log the shutdown reason

        Target: under 500ms from detection to about:blank

        Args:
            page: Playwright/Patchright Page object to shut down.
            reason: Reason for the shutdown.

        Returns:
            ShutdownResult with details of the shutdown operation.
        """
        start_time = time.time()
        data_saved: List[str] = []

        try:
            # -- Step 1: Rescue data --
            if self._data_rescue:
                try:
                    rescued = await asyncio.wait_for(
                        page.evaluate(DATA_RESCUE_JS),
                        timeout=min(self._shutdown_timeout * 0.5, 1.0),
                    )
                    if rescued and isinstance(rescued, list):
                        for item in rescued:
                            data_type = item.get("type", "unknown")
                            data_saved.append(data_type)
                            logger.debug(f"Rescued data: {data_type}")
                except asyncio.TimeoutError:
                    logger.debug("Data rescue timed out")
                except Exception as rescue_err:
                    logger.debug(f"Data rescue failed: {rescue_err}")

            # -- Step 2: Stop all network requests via CDP --
            try:
                cdp = await page.context.new_cdp_session(page)
                try:
                    await cdp.send("Network.disable", {})
                finally:
                    try:
                        await cdp.detach()
                    except Exception:
                        pass
            except Exception:
                pass

            # -- Step 3: Navigate to about:blank --
            try:
                await asyncio.wait_for(
                    page.goto("about:blank", wait_until="commit"),
                    timeout=max(self._shutdown_timeout * 0.3, 0.3),
                )
            except asyncio.TimeoutError:
                # Force navigation by evaluating
                try:
                    await asyncio.wait_for(
                        page.evaluate(
                            "window.location.href = 'about:blank'"
                        ),
                        timeout=0.3,
                    )
                except Exception:
                    pass
            except Exception:
                # Page may already be closed/unresponsive
                pass

            # -- Step 4: Close the page --
            try:
                await asyncio.wait_for(
                    page.close(),
                    timeout=max(self._shutdown_timeout * 0.2, 0.3),
                )
            except asyncio.TimeoutError:
                # Force close via CDP
                try:
                    cdp = await page.context.new_cdp_session(page)
                    try:
                        await cdp.send("Page.close", {})
                    finally:
                        try:
                            await cdp.detach()
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                # Page already closed
                pass

            elapsed_ms = (time.time() - start_time) * 1000

            result = ShutdownResult(
                shutdown=True,
                reason=reason,
                data_saved=data_saved,
                timestamp=time.time(),
                duration_ms=elapsed_ms,
            )

            logger.info(
                f"Page shutdown completed in {elapsed_ms:.0f}ms "
                f"(reason: {reason[:80]}, data_rescued: {data_saved})"
            )

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Page shutdown error: {e}")

            # Last resort: try to close the page
            try:
                await page.close()
            except Exception:
                pass

            return ShutdownResult(
                shutdown=True,
                reason=(
                    f"{reason} (error during shutdown: {str(e)[:60]})"
                ),
                data_saved=data_saved,
                timestamp=time.time(),
                duration_ms=elapsed_ms,
            )

    # -- INTEGRATION WITH CAPTCHA BYPASS -----------------------

    def get_bypass(self) -> CaptchaBypass:
        """Get the associated CaptchaBypass instance."""
        return self._bypass

    def set_bypass(self, bypass: CaptchaBypass):
        """Set the CaptchaBypass instance to work alongside."""
        self._bypass = bypass

    # -- STATISTICS --------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get preemption statistics.

        Returns:
            Dict with all tracking stats.
        """
        return {
            "status": "success",
            "stats": {
                "urls_assessed": self._stats["urls_assessed"],
                "preflights_run": self._stats["preflights_run"],
                "monitors_started": self._stats["monitors_started"],
                "health_checks": self._stats["health_checks"],
                "shutdowns": self._stats["shutdowns"],
                "shutdowns_by_reason": dict(
                    self._stats["shutdowns_by_reason"]
                ),
                "detections_by_type": dict(
                    self._stats["detections_by_type"]
                ),
                "active_monitors": len(self._active_monitors),
                "detection_scripts_injected": len(
                    self._detection_script_injected
                ),
                "config": self.config,
            },
        }

    async def get_monitor_status(
        self, page_id: str
    ) -> Dict[str, Any]:
        """Get status of a specific monitor.

        Args:
            page_id: The page identifier.

        Returns:
            {"status": "success", "monitor": ...} or
            {"status": "error", ...}
        """
        handle = self._active_monitors.get(page_id)
        if handle:
            return {"status": "success", "monitor": handle.to_dict()}
        return {
            "status": "error",
            "error": f"No active monitor for page '{page_id}'",
        }

    async def list_active_monitors(self) -> Dict[str, Any]:
        """List all active monitors.

        Returns:
            {"status": "success", "monitors": {page_id: ...}}
        """
        monitors = {}
        for page_id, handle in self._active_monitors.items():
            monitors[page_id] = handle.to_dict()
        return {"status": "success", "monitors": monitors}

    # -- CLEANUP -----------------------------------------------

    async def cleanup(self) -> Dict[str, Any]:
        """Stop all monitors and clean up resources.

        Returns:
            {"status": "success", "monitors_stopped": int}
        """
        stopped = 0
        async with self._monitor_lock:
            for page_id, handle in list(self._active_monitors.items()):
                await self._stop_monitor_internal(handle)
                stopped += 1
            self._active_monitors.clear()
            self._detection_script_injected.clear()

        logger.info(
            f"CaptchaPreemptor cleanup: stopped {stopped} monitors"
        )
        return {"status": "success", "monitors_stopped": stopped}
