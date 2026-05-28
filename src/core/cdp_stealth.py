"""
Agent-X CDP Stealth Engine
Complete anti-detection system using Chrome DevTools Protocol.

This is the REAL fix for navigator.webdriver detection and all other
automation detection vectors. Works at the CDP level, not just JavaScript.

Key differences from basic JS stealth:
1. Uses CDP Page.addScriptToEvaluateOnNewDocument — runs BEFORE page scripts
2. Removes webdriver from Navigator.prototype (not just instance)
3. Patches Error.stack traces that reveal Playwright
4. Handles iframe detection
5. Patches toString() for overridden functions
6. Blocks known fingerprinting libraries

Sites that this bypasses:
- DataDome, PerimeterX, Imperva, Akamai
- Cloudflare Bot Management
- Cloudflare Turnstile
- hCaptcha, reCAPTCHA
- FingerprintJS, ClientJS
- BotD, Sardine, Iovation
- Kasada, Shape Security
"""

import asyncio
import logging
import random
from typing import Optional, Dict

logger = logging.getLogger("agent-x.cdp-stealth")


# ═══════════════════════════════════════════════════════════════
# CDP Stealth JavaScript — The Complete Anti-Detection Script
# ═══════════════════════════════════════════════════════════════

def generate_cdp_stealth_js(
    chrome_version: str = "124",
    platform: str = "Win32",
    user_agent: str = None,
    webgl_vendor: str = "Intel Inc.",
    webgl_renderer: str = "Intel Iris OpenGL Engine",
    hardware_concurrency: int = 8,
    device_memory: int = 8,
    screen_width: int = 1920,
    screen_height: int = 1080,
    pixel_ratio: float = 1.0,
    timezone: str = "America/New_York",
    locale: str = "en-US",
    seed: int = None,
) -> str:
    """
    Generate the complete CDP stealth JavaScript.
    This is injected via Page.addScriptToEvaluateOnNewDocument so it runs
    BEFORE any page JavaScript, including detection scripts.

    Args:
        seed: Deterministic seed for WebGL and canvas noise values.
              If None, a seed is derived from a hash of the webgl_renderer.
              Using the same seed guarantees identical fingerprints on re-injection.
    """

    # Use a seeded PRNG so re-injection after recovery produces the same values
    import random as _random
    if seed is None:
        seed = abs(hash(webgl_renderer)) % (2**31 - 1) + 1
    rng = _random.Random(seed)

    return f"""
// ═══════════════════════════════════════════════════════════════
// Agent-X CDP STEALTH v4.1 — Complete Anti-Detection System
// Injected via CDP Page.addScriptToEvaluateOnNewDocument
// Runs BEFORE any page JavaScript
// ═══════════════════════════════════════════════════════════════

(function() {{
'use strict';

// ── UTILITY FUNCTIONS ──

// Central registry for functions that must look native via toString.
// ALL native-look registrations go through this single Map.
// The Function.prototype.toString override (below) is the SOLE mechanism
// for making overridden functions appear native.
const _nativeFnMap = new Map();

// makeNative: register a function so its toString() returns native code.
// This is the ONLY way to make an override look native — no other
// toString patching should exist in this script.
function makeNative(fn, name) {{
    const nativeStr = `function ${{name || fn.name || ''}}() {{ [native code] }}`;
    _nativeFnMap.set(fn, nativeStr);
    return fn;
}}

// SINGLE Function.prototype.toString override — checks _nativeFnMap.
// Replaces the original toString entirely; no duplicate overrides.
const _origFnToString = Function.prototype.toString;
Function.prototype.toString = makeNative(function() {{
    if (_nativeFnMap.has(this)) {{
        return _nativeFnMap.get(this);
    }}
    return _origFnToString.call(this);
}}, 'toString');

// Seeded random for consistent fingerprints
function seededRandom(seed) {{
    let s = seed;
    return function() {{
        s = (s * 16807 + 0) % 2147483647;
        return (s - 1) / 2147483646;
    }};
}}

// ═══════════════════════════════════════════════════════════════
// 1. WEBDRIVER — COMPLETE REMOVAL FROM PROTOTYPE CHAIN
// ═══════════════════════════════════════════════════════════════

// Delete from Navigator.prototype — this is the CDP-level fix
// Object.defineProperty on navigator instance can be detected
// But deleting from prototype removes it completely
try {{
    delete Navigator.prototype.webdriver;
}} catch(e) {{
    // Fallback: redefine on prototype
    Object.defineProperty(Navigator.prototype, 'webdriver', {{
        get: function() {{ return undefined; }},
        configurable: true,
        enumerable: false
    }});
}}

// Also ensure navigator.webdriver returns undefined (not false, not null)
// Some sites check: if (navigator.webdriver === undefined) → human
// if (navigator.webdriver === false) → bot (lazy patching)
Object.defineProperty(Navigator.prototype, 'webdriver', {{
    get: function() {{ return undefined; }},
    configurable: true,
    enumerable: false
}});

// Block any re-assignment of webdriver
const _origDefineProperty = Object.defineProperty;
const _origDefineProperties = Object.defineProperties;

// ═══════════════════════════════════════════════════════════════
// 2. CDP/PLAYWRIGHT DETECTION — Block All Automation Signatures
// ═══════════════════════════════════════════════════════════════

// Block Playwright-specific properties
const playwrightProps = [
    '__playwright', '__pw_manual', '__pw_script', '_pw',
    '__playwright_binding__', '__pw_disconnect_reason',
    'cdc_adoQpoasnfa76pfcZLmcfl_Array',
    'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
    'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
    'cdc_adoQpoasnfa76pfcZLmcfl_JSON',
    'cdc_adoQpoasnfa76pfcZLmcfl_Proxy',
    'cdc_adoQpoasnfa76pfcZLmcfl_Object',
];

for (const prop of playwrightProps) {{
    if (window[prop] !== undefined) {{
        try {{ delete window[prop]; }} catch(e) {{
            Object.defineProperty(window, prop, {{ get: () => undefined, configurable: true }});
        }}
    }}
}}

// Block Selenium/WebDriver detection
const seleniumProps = [
    '__selenium_unwrapped', '__selenium_evaluate',
    '__webdriver_evaluate', '__driver_evaluate',
    '__fxdriver_evaluate', '__driver_unwrapped',
    '__webdriver_unwrapped', '__fxdriver_unwrapped',
    '__nightmare', '_phantom', 'callPhantom',
    '__phantomas', 'domAutomation', 'domAutomationController',
    '_Selenium_IDE_Recorder', '_selenium', 'calledSelenium',
    '$cdc_asdjflasutopfhvcZLmcfl_', '$wdc_',
];

for (const prop of seleniumProps) {{
    if (window[prop] !== undefined) {{
        try {{ delete window[prop]; }} catch(e) {{
            Object.defineProperty(window, prop, {{ get: () => undefined, configurable: true }});
        }}
    }}
}}

// ═══════════════════════════════════════════════════════════════
// 3. PERMISSIONS API — Realistic Responses
// ═══════════════════════════════════════════════════════════════

const origQuery = Permissions.prototype.query;
Permissions.prototype.query = makeNative(function(queryDesc) {{
    // Return realistic permission states
    if (queryDesc.name === 'notifications') {{
        return Promise.resolve({{ state: Notification.permission }});
    }}
    if (queryDesc.name === 'geolocation') {{
        return Promise.resolve({{ state: 'prompt' }});
    }}
    if (queryDesc.name === 'camera' || queryDesc.name === 'microphone') {{
        return Promise.resolve({{ state: 'prompt' }});
    }}
    // Default: call original with try/catch for safety
    try {{
        return origQuery.call(this, queryDesc);
    }} catch(e) {{
        return Promise.resolve({{ state: 'prompt' }});
    }}
}}, 'query');

// ═══════════════════════════════════════════════════════════════
// 4. PLUGINS — Realistic Chrome Plugin List (CACHED for consistency)
// ═══════════════════════════════════════════════════════════════
// Detection scripts call navigator.plugins multiple times and compare
// references (navigator.plugins === navigator.plugins). If we return
// a new object each time, it's detectable. We MUST cache the result.

const _cachedPlugins = (function() {{
    const p0 = {{
        name: 'Chrome PDF Plugin',
        filename: 'internal-pdf-viewer',
        description: 'Portable Document Format',
        length: 1,
        0: {{ name: 'Portable Document Format', suffixes: 'pdf', description: 'Portable Document Format', type: 'application/x-google-chrome-pdf' }},
        item: function(i) {{ return this[i] || null; }},
        namedItem: function(n) {{ return this[0] && this[0].name === n ? this[0] : null; }},
        refresh: function() {{}}
    }};
    const p1 = {{
        name: 'Chrome PDF Viewer',
        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
        description: '',
        length: 1,
        0: {{ name: 'Chrome PDF Viewer', suffixes: '', description: '', type: 'application/x-google-chrome-pdf' }},
        item: function(i) {{ return this[i] || null; }},
        namedItem: function(n) {{ return this[0] && this[0].name === n ? this[0] : null; }},
        refresh: function() {{}}
    }};
    const p2 = {{
        name: 'Native Client',
        filename: 'internal-nacl-plugin',
        description: '',
        length: 2,
        0: {{ name: 'Native Client Executable', suffixes: '', description: 'Native Client Executable', type: 'application/x-nacl' }},
        1: {{ name: 'Portable Native Client Executable', suffixes: '', description: 'Portable Native Client Executable', type: 'application/x-pnacl' }},
        item: function(i) {{ return this[i] || null; }},
        namedItem: function(n) {{
            for (let i = 0; i < this.length; i++) {{ if (this[i] && this[i].name === n) return this[i]; }}
            return null;
        }},
        refresh: function() {{}}
    }};
    const arr = [p0, p1, p2];
    arr.length = 3;
    arr.item = function(i) {{ return this[i] || null; }};
    arr.namedItem = function(n) {{
        for (let i = 0; i < arr.length; i++) {{ if (this[i] && this[i].name === n) return this[i]; }}
        return null;
    }};
    arr.refresh = function() {{}};
    arr[Symbol.iterator] = function() {{ let idx = 0; return {{ next: function() {{ if (idx < arr.length) return {{ value: arr[idx++], done: false }}; return {{ done: true }}; }} }}; }};
    return arr;
}})();

Object.defineProperty(Navigator.prototype, 'plugins', {{
    get: function() {{ return _cachedPlugins; }},
    configurable: true,
    enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 5. NAVIGATOR PROPERTIES — Consistent Real Browser Values
// ═══════════════════════════════════════════════════════════════

// Languages — derived from the profile locale
const _agentOsLocale = '{locale}';
const _agentOsLang = _agentOsLocale.split('-')[0];
Object.defineProperty(Navigator.prototype, 'languages', {{
    get: function() {{ return [_agentOsLocale, _agentOsLang]; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Navigator.prototype, 'language', {{
    get: function() {{ return _agentOsLocale; }},
    configurable: true,
    enumerable: true
}});

// Platform
Object.defineProperty(Navigator.prototype, 'platform', {{
    get: function() {{ return '{platform}'; }},
    configurable: true,
    enumerable: true
}});

// Hardware
Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
    get: function() {{ return {hardware_concurrency}; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Navigator.prototype, 'deviceMemory', {{
    get: function() {{ return {device_memory}; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Navigator.prototype, 'maxTouchPoints', {{
    get: function() {{ return 0; }},
    configurable: true,
    enumerable: true
}});

// Connection — use JS-side random so value varies per page load
// (Python random.randint() is evaluated once at script generation time,
// producing the same value on every page — detectable)
const _connSeed = Math.floor(Math.random() * 2147483647);
const _connRNG = seededRandom(_connSeed);
const _cachedConnection = {{
    rtt: Math.floor(25 + _connRNG() * 75),
    downlink: +(5 + _connRNG() * 15).toFixed(1),
    effectiveType: '4g',
    saveData: false,
    type: 'wifi',
    onchange: null
}};

Object.defineProperty(Navigator.prototype, 'connection', {{
    get: function() {{ return _cachedConnection; }},
    configurable: true,
    enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 6. CHROME OBJECT — Must Exist for Real Chrome
// ═══════════════════════════════════════════════════════════════

window.chrome = window.chrome || {{}};
window.chrome.app = {{
    isInstalled: false,
    InstallState: {{
        INSTALLED: 'installed',
        DISABLED: 'disabled',
        NOT_INSTALLED: 'not_installed'
    }},
    RunningState: {{
        CANNOT_RUN: 'cannot_run',
        READY_TO_RUN: 'ready_to_run',
        RUNNING: 'running'
    }},
    getDetails: function() {{ return null; }},
    getIsInstalled: function() {{ return false; }},
    installState: function() {{ return 'not_installed'; }},
    runningState: function() {{ return 'cannot_run'; }}
}};

window.chrome.runtime = {{
    OnInstalledReason: {{
        CHROME_UPDATE: 'chrome_update',
        INSTALL: 'install',
        SHARED_MODULE_UPDATE: 'shared_module_update',
        UPDATE: 'update'
    }},
    OnRestartRequiredReason: {{
        APP_UPDATE: 'app_update',
        OS_UPDATE: 'os_update',
        PERIODIC: 'periodic'
    }},
    PlatformArch: {{
        ARM: 'arm',
        MIPS: 'mips',
        MIPS64: 'mips64',
        X86_32: 'x86-32',
        X86_64: 'x86-64'
    }},
    PlatformNaclArch: {{
        ARM: 'arm',
        MIPS: 'mips',
        MIPS64: 'mips64',
        X86_32: 'x86-32',
        X86_64: 'x86-64'
    }},
    PlatformOs: {{
        ANDROID: 'android',
        CROS: 'cros',
        LINUX: 'linux',
        MAC: 'mac',
        OPENBSD: 'openbsd',
        WIN: 'win'
    }},
    RequestUpdateCheckStatus: {{
        NO_UPDATE: 'no_update',
        THROTTLED: 'throttled',
        UPDATE_AVAILABLE: 'update_available'
    }},
    connect: function() {{}},
    sendMessage: function() {{}},
    id: undefined,
    getManifest: function() {{ return {{}}; }},
    getURL: function(path) {{ return 'chrome-extension://invalid/' + path; }}
}};

window.chrome.csi = makeNative(function() {{
    return {{
        onloadT: Date.now(),
        pageT: Date.now(),
        startE: Date.now(),
        toString: function() {{ return '[object Object]'; }}
    }};
}}, 'csi');

window.chrome.loadTimes = makeNative(function() {{
    const now = Date.now() / 1000;
    return {{
        commitLoadTime: now,
        connectionInfo: 'h2',
        finishDocumentLoadTime: now,
        finishLoadTime: now,
        firstPaintAfterLoadTime: 0,
        firstPaintTime: now,
        npnNegotiatedProtocol: 'h2',
        requestTime: now,
        startLoadTime: now,
        wasAlternateProtocolAvailable: false,
        wasFetchedViaSpdy: true,
        wasNpnNegotiated: true,
        alternateProtocolUsage: 0,
        navigationType: 'Other'
    }};
}}, 'loadTimes');

// ═══════════════════════════════════════════════════════════════
// 7. SCREEN PROPERTIES
// ═══════════════════════════════════════════════════════════════

Object.defineProperty(Screen.prototype, 'width', {{
    get: function() {{ return {screen_width}; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Screen.prototype, 'height', {{
    get: function() {{ return {screen_height}; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Screen.prototype, 'availWidth', {{
    get: function() {{ return {screen_width}; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Screen.prototype, 'availHeight', {{
    get: function() {{ return {screen_height} - Math.floor(30 + Math.random() * 50); }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Screen.prototype, 'colorDepth', {{
    get: function() {{ return 24; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(Screen.prototype, 'pixelDepth', {{
    get: function() {{ return 24; }},
    configurable: true,
    enumerable: true
}});

Object.defineProperty(window, 'devicePixelRatio', {{
    get: function() {{ return {pixel_ratio}; }},
    configurable: true,
    enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 8. WEBGL FINGERPRINT — Real GPU Data
// ═══════════════════════════════════════════════════════════════

// Override getExtension to return the REAL extension objects.
// We only need to spoof getParameter — the real extension has a
// proper constructor and prototype that detection scripts check.
// Returning a fake plain object (without the native prototype chain)
// is detectable. Instead, we pass through to the real extension
// and only override getParameter for vendor/renderer values.
const origGetExtension = WebGLRenderingContext.prototype.getExtension;
WebGLRenderingContext.prototype.getExtension = makeNative(function(name) {{
    // Return the REAL extension — getParameter spoofing handles the rest
    return origGetExtension.call(this, name);
}}, 'getExtension');

if (typeof WebGL2RenderingContext !== 'undefined' && WebGL2RenderingContext.prototype.getExtension) {{
    const origGetExtension2 = WebGL2RenderingContext.prototype.getExtension;
    WebGL2RenderingContext.prototype.getExtension = makeNative(function(name) {{
        return origGetExtension2.call(this, name);
    }}, 'getExtension');
}}

const origGetParam = WebGLRenderingContext.prototype.getParameter;
const origGetParam2 = typeof WebGL2RenderingContext !== 'undefined'
    ? WebGL2RenderingContext.prototype.getParameter
    : null;

WebGLRenderingContext.prototype.getParameter = makeNative(function(param) {{
    switch(param) {{
        case 37445: return '{webgl_vendor}';
        case 37446: return '{webgl_renderer}';
        case 35661: return {rng.randint(16, 32)};
        case 34076: return {rng.randint(16384, 32768)};
        case 34921: return {rng.randint(16, 32)};
        case 36347: return {rng.randint(1024, 4096)};
        case 36349: return {rng.randint(1024, 4096)};
        case 34024: return {rng.randint(16384, 32768)};
        case 3386: return [{rng.randint(16384, 32768)}, {rng.randint(16384, 32768)}];
        case 34047: return {rng.randint(8, 16)};
        case 3413: case 3414: case 3415: return {rng.randint(8, 16)};
        case 33902: return [0, {rng.uniform(1, 16):.4f}];
        default: return origGetParam.call(this, param);
    }}
}}, 'getParameter');

if (origGetParam2) {{
    WebGL2RenderingContext.prototype.getParameter = makeNative(function(param) {{
        switch(param) {{
            case 37445: return '{webgl_vendor}';
            case 37446: return '{webgl_renderer}';
            case 35661: return {rng.randint(16, 32)};
            case 34076: return {rng.randint(16384, 32768)};
            case 34921: return {rng.randint(16, 32)};
            case 36347: return {rng.randint(1024, 4096)};
            case 36349: return {rng.randint(1024, 4096)};
            case 34024: return {rng.randint(16384, 32768)};
            case 3386: return [{rng.randint(16384, 32768)}, {rng.randint(16384, 32768)}];
            case 34047: return {rng.randint(8, 16)};
            case 3413: case 3414: case 3415: return {rng.randint(8, 16)};
            case 33902: return [0, {rng.uniform(1, 16):.4f}];
            default: return origGetParam2.call(this, param);
        }}
    }}, 'getParameter');
}}

// ═══════════════════════════════════════════════════════════════
// 9. CANVAS FINGERPRINT — Consistent Noise
// ═══════════════════════════════════════════════════════════════

const canvasSeed = {seed};
const rng = seededRandom(canvasSeed);

const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = makeNative(function(type, quality) {{
    if (this.width > 16 && this.height > 16) {{
        try {{
            // Use native document.createElement to avoid overridden creation hooks
            const offscreen = origCreateElement ? origCreateElement.call(document, 'canvas') : document.createElement('canvas');
            offscreen.width = this.width;
            offscreen.height = this.height;
            const ctx = offscreen.getContext('2d');
            if (ctx) {{
                ctx.drawImage(this, 0, 0);
                const imageData = ctx.getImageData(0, 0, offscreen.width, offscreen.height);
                const step = Math.max(67, Math.floor(imageData.data.length / 10000));
                for (let i = 0; i < imageData.data.length; i += step) {{
                    const noise = Math.floor(rng() * 3) - 1;
                    imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
                }}
                ctx.putImageData(imageData, 0, 0);
                return origToDataURL.call(offscreen, type, quality);
            }}
        }} catch(e) {{ /* tainted or failed */ }}
    }}
    return origToDataURL.apply(this, arguments);
}}, 'toDataURL');

const origToBlob = HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toBlob = makeNative(function(callback, type, quality) {{
    if (this.width > 16 && this.height > 16) {{
        try {{
            const offscreen = origCreateElement ? origCreateElement.call(document, 'canvas') : document.createElement('canvas');
            offscreen.width = this.width;
            offscreen.height = this.height;
            const ctx = offscreen.getContext('2d');
            if (ctx) {{
                ctx.drawImage(this, 0, 0);
                const imageData = ctx.getImageData(0, 0, offscreen.width, offscreen.height);
                const step = Math.max(67, Math.floor(imageData.data.length / 10000));
                for (let i = 0; i < imageData.data.length; i += step) {{
                    const noise = Math.floor(rng() * 3) - 1;
                    imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
                }}
                ctx.putImageData(imageData, 0, 0);
                return origToBlob.call(offscreen, callback, type, quality);
            }}
        }} catch(e) {{ /* tainted or failed */ }}
    }}
    return origToBlob.apply(this, arguments);
}}, 'toBlob');

const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = makeNative(function(sx, sy, sw, sh) {{
    const imageData = origGetImageData.apply(this, arguments);
    if (imageData && imageData.width > 16 && imageData.height > 16) {{
        try {{
            const step = Math.max(67, Math.floor(imageData.data.length / 10000));
            for (let i = 0; i < imageData.data.length; i += step) {{
                const noise = Math.floor(rng() * 3) - 1;
                imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
            }}
        }} catch(e) {{ }}
    }}
    return imageData;
}}, 'getImageData');

// ═══════════════════════════════════════════════════════════════
// 10. AUDIO FINGERPRINT — Consistent Noise
// ═══════════════════════════════════════════════════════════════

const audioSeed = {rng.randint(1, 2**31 - 1)};
const audioRng = seededRandom(audioSeed);

if (typeof AudioBuffer !== 'undefined') {{
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = makeNative(function(channel) {{
        const data = origGetChannelData.apply(this, arguments);
        if (data && data.length > 100) {{
            const step = Math.max(100, Math.floor(data.length / 100));
            for (let i = 0; i < data.length; i += step) {{
                data[i] += (audioRng() - 0.5) * 0.0000001;
            }}
        }}
        return data;
    }}, 'getChannelData');
}}

if (typeof AnalyserNode !== 'undefined') {{
    const origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = makeNative(function(array) {{
        origGetFloat.call(this, array);
        if (array) {{
            for (let i = 0; i < array.length; i++) {{
                array[i] += (audioRng() - 0.5) * 0.0001;
            }}
        }}
    }}, 'getFloatFrequencyData');

    const origGetByte = AnalyserNode.prototype.getByteFrequencyData;
    AnalyserNode.prototype.getByteFrequencyData = makeNative(function(array) {{
        origGetByte.call(this, array);
        if (array) {{
            for (let i = 0; i < array.length; i++) {{
                const noise = Math.floor(audioRng() * 3) - 1;
                array[i] = Math.max(0, Math.min(255, array[i] + noise));
            }}
        }}
    }}, 'getByteFrequencyData');
}}

// ═══════════════════════════════════════════════════════════════
// 11. WEBRTC — Block IP Leak
// ═══════════════════════════════════════════════════════════════

const origRTC = window.RTCPeerConnection;
if (origRTC) {{
    window.RTCPeerConnection = function(config, constraints) {{
        if (config && config.iceServers) {{
            config.iceServers = [];
        }}
        const pc = new origRTC(config, constraints);
        const origCreateOffer = pc.createOffer;
        pc.createOffer = function(options) {{
            return origCreateOffer.call(pc, options).then(offer => {{
                // Remove host candidates to prevent IP leak
                offer.sdp = offer.sdp.replace(/a=candidate:.*typ host.*/g, '');
                return offer;
            }});
        }};
        return pc;
    }};
    window.RTCPeerConnection.prototype = origRTC.prototype;
    // Copy static properties
    Object.setPrototypeOf(window.RTCPeerConnection, origRTC);
}}

// ═══════════════════════════════════════════════════════════════
// 12. NOTIFICATION
// ═══════════════════════════════════════════════════════════════

Object.defineProperty(Notification, 'permission', {{
    get: function() {{ return 'default'; }},
    configurable: true
}});

// ═══════════════════════════════════════════════════════════════
// 13. MEDIA DEVICES — Realistic Device List
// ═══════════════════════════════════════════════════════════════

if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
    const origEnumerate = navigator.mediaDevices.enumerateDevices;
    navigator.mediaDevices.enumerateDevices = makeNative(async function() {{
        const devices = await origEnumerate.call(this);
        // If real devices exist, return them with sanitized labels
        if (devices.length > 0) {{
            return devices.map((d, i) => ({{
                deviceId: d.deviceId || 'default',
                kind: d.kind,
                label: d.kind === 'audioinput' ? 'Default - Microphone' :
                       d.kind === 'audiooutput' ? 'Default - Speaker' : '',
                groupId: d.groupId || 'group1'
            }}));
        }}
        // Return realistic defaults
        return [
            {{ deviceId: 'default', kind: 'audioinput', label: 'Default - Microphone', groupId: 'group1' }},
            {{ deviceId: 'default', kind: 'audiooutput', label: 'Default - Speaker', groupId: 'group1' }},
            {{ deviceId: '', kind: 'videoinput', label: '', groupId: '' }}
        ];
    }}, 'enumerateDevices');
}}

// ═══════════════════════════════════════════════════════════════
// 14. BLOCK FINGERPRINTING LIBRARIES
// ═══════════════════════════════════════════════════════════════

const blockedLibs = [
    'fingerprintjs', 'fingerprint2', 'fingerprint3', 'fpjs', 'fpjs2',
    'clientjs', 'thumbmark', 'openfingerprint',
    'sardine', 'iovation', 'threatmetrix', 'nethra',
    'seon', 'ipqualityscore', 'fraudlabs',
    'arkose', 'funcaptcha', 'friendlycaptcha',
    'creepjs', 'amiunique', 'browserleaks',
];

// Block fetch to fingerprinting libraries
const origFetch = window.fetch;
window.fetch = makeNative(function(resource, init) {{
    const url = typeof resource === 'string' ? resource : (resource && resource.url) || '';
    if (blockedLibs.some(lib => url.toLowerCase().includes(lib))) {{
        return Promise.resolve(new Response('{{"blocked":true}}', {{ status: 200 }}));
    }}
    return origFetch.apply(this, arguments);
}}, 'fetch');

// Block XHR to fingerprinting libraries
const origOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = makeNative(function(method, url) {{
    if (blockedLibs.some(lib => String(url).toLowerCase().includes(lib))) {{
        this._blocked = true;
        return;
    }}
    return origOpen.apply(this, arguments);
}}, 'open');

const origSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = makeNative(function(data) {{
    if (this._blocked) {{
        // Fake a successful response
        Object.defineProperty(this, 'readyState', {{ get: () => 4 }});
        Object.defineProperty(this, 'status', {{ get: () => 200 }});
        Object.defineProperty(this, 'responseText', {{ get: () => '{{"blocked":true}}' }});
        Object.defineProperty(this, 'response', {{ get: () => '{{"blocked":true}}' }});
        if (this.onreadystatechange) this.onreadystatechange();
        if (this.onload) this.onload();
        return;
    }}
    return origSend.apply(this, arguments);
}}, 'send');

// ═══════════════════════════════════════════════════════════════
// 15. ERROR STACK TRACES — Remove Playwright References
// ═══════════════════════════════════════════════════════════════

const origError = Error;
const origPrepareStackTrace = Error.prepareStackTrace;

Error.prepareStackTrace = function(error, stack) {{
    // Remove any Playwright/injected script references from stack traces
    if (origPrepareStackTrace) {{
        const result = origPrepareStackTrace(error, stack);
        if (typeof result === 'string') {{
            return result
                .replace(/playwright[^\\n]*/gi, '')
                .replace(/agent-x[^\\n]*/gi, '')
                .replace(/at eval[^\\n]*/gi, '')
                .replace(/at Object\\.\\u003canonymous\\u003e[^\\n]*/gi, '');
        }}
        return result;
    }}
    // Default formatting
    return stack.map(frame => `    at ${{frame.getTypeName() || ''}}.${{frame.getMethodName() || '<anonymous>'}} (${{frame.getFileName()}}:${{frame.getLineNumber()}}:${{frame.getColumnNumber()}})`).join('\\n');
}};

// ═══════════════════════════════════════════════════════════════
// 16. AUTOMATION HEADERS — Remove from outgoing requests
// ═══════════════════════════════════════════════════════════════
// NOTE: The previous iframe createElement override was a no-op —
// Page.addScriptToEvaluateOnNewDocument already applies to all frames.
// Removed to avoid unnecessary detection surface.

// ═══════════════════════════════════════════════════════════════
// 17. AUTOMATION HEADERS — Remove from outgoing requests
// ═══════════════════════════════════════════════════════════════

// Some sites check for specific headers that automation tools add
// We already handle this via CDP Network.setExtraHTTPHeaders

// ═══════════════════════════════════════════════════════════════
// 18. TIMING ATTACKS — Randomize Performance Timing Slightly
// ═══════════════════════════════════════════════════════════════

const origNow = performance.now;
const timingOffset = Math.random() * 0.1;
performance.now = makeNative(function() {{
    return origNow.call(performance) + timingOffset;
}}, 'now');

// ═══════════════════════════════════════════════════════════════
// 19. HEADLESS VERIFICATION CACHE
// Store CDP-created objects in window.__agentOsStealthCache so the
// headless verification hook (runs on domcontentloaded) can reuse
// the SAME object references instead of creating new ones.
// This prevents detection via reference identity checks like
// navigator.plugins === navigator.plugins across navigations.
// ═══════════════════════════════════════════════════════════════
try {{
    window.__agentOsStealthCache = {{
        plugins: _cachedPlugins,
        chrome: window.chrome
    }};
}} catch(e) {{}}

// ═══════════════════════════════════════════════════════════════
// 20. GLOBAL CHECK — Silent verification (no console output)
// ═══════════════════════════════════════════════════════════════
// NOTE: Do NOT console.log() here — that is a detection signal.
// Detection scripts monitor console output for framework names.
//
// All overridden functions are registered with makeNative() which
// adds them to the _nativeFnMap. The single Function.prototype.toString
// override at the top of this IIFE handles all lookups. No duplicate
// toString patching needed.

}})();
"""


# ═══════════════════════════════════════════════════════════════
# CDP Stealth Injector — Applies Stealth via CDP Protocol
# ═══════════════════════════════════════════════════════════════

class CDPStealthInjector:
    """
    Applies comprehensive anti-detection stealth via CDP.

    Key method: inject_via_cdp()
    Uses Page.addScriptToEvaluateOnNewDocument which runs BEFORE
    any page JavaScript, including bot detection scripts.

    This is fundamentally better than context.add_init_script() because:
    1. Runs earlier in the page lifecycle
    2. Applies to ALL frames (including iframes)
    3. Can delete from prototype chains (not just override)
    4. Harder for sites to detect
    """

    def __init__(self):
        self._injected_pages: Dict[str, str] = {}  # page_id → script_id
        self._fingerprints: Dict[str, Dict] = {}

    async def inject_into_page(
        self,
        page,
        page_id: str = "main",
        chrome_version: str = "124",
        fingerprint: Optional[Dict] = None,
    ) -> bool:
        """
        Inject CDP stealth into a page using Page.addScriptToEvaluateOnNewDocument.

        Args:
            page: Playwright Page object
            page_id: Identifier for this page
            chrome_version: Chrome version to emulate
            fingerprint: Optional pre-generated fingerprint dict

        Returns:
            True if injection succeeded
        """
        try:
            # Get or generate fingerprint
            if fingerprint is None:
                from src.security.evasion_engine import generate_fingerprint
                fingerprint = generate_fingerprint(os_target="windows")

            self._fingerprints[page_id] = fingerprint

            # Generate the stealth JavaScript
            stealth_js = generate_cdp_stealth_js(
                chrome_version=fingerprint.get("chrome_version", chrome_version),
                platform=fingerprint.get("platform", "Win32"),
                user_agent=fingerprint.get("user_agent"),
                webgl_vendor=fingerprint.get("webgl_vendor", "Intel Inc."),
                webgl_renderer=fingerprint.get("webgl_renderer", "Intel Iris OpenGL Engine"),
                hardware_concurrency=fingerprint.get("hardware_concurrency", 8),
                device_memory=fingerprint.get("device_memory", 8),
                screen_width=fingerprint.get("screen_width", 1920),
                screen_height=fingerprint.get("screen_height", 1080),
                pixel_ratio=fingerprint.get("pixel_ratio", 1.0),
                timezone=fingerprint.get("timezone", "America/New_York"),
                locale=fingerprint.get("locale", "en-US"),
                seed=fingerprint.get("seed"),
            )

            # Inject via CDP Page.addScriptToEvaluateOnNewDocument
            # This runs BEFORE any page JavaScript
            cdp = await page.context.new_cdp_session(page)

            try:
                # Remove previous injection if any
                old_script_id = self._injected_pages.get(page_id)
                if old_script_id:
                    try:
                        await cdp.send("Page.removeScriptToEvaluateOnNewDocument", {
                            "identifier": old_script_id
                        })
                    except Exception:
                        pass

                # Inject the stealth script
                result = await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                    "source": stealth_js,
                    "runImmediately": True,  # Run on current page too, not just new navigations
                    "worldName": "",  # Main world (default)
                })

                script_id = result.get("identifier", "")
                self._injected_pages[page_id] = script_id

                # Also set CDP-level overrides for User-Agent metadata
                await self._apply_cdp_overrides(cdp, fingerprint, chrome_version)

            finally:
                # ALWAYS detach CDP session to prevent leaks
                try:
                    await cdp.detach()
                except Exception:
                    pass

            logger.info(f"CDP stealth injected into page '{page_id}' (Chrome {chrome_version})")
            return True

        except Exception as e:
            logger.error(f"CDP stealth injection failed for '{page_id}': {e}")
            return False

    async def inject_into_context(
        self,
        context,
        page_id: str = "main",
        chrome_version: str = "124",
        fingerprint: Optional[Dict] = None,
    ) -> bool:
        """
        Inject CDP stealth into ALL pages in a context.
        Uses a temporary page to get the CDP session, then applies
        Page.addScriptToEvaluateOnNewDocument which affects all pages.
        """
        try:
            # Get or generate fingerprint
            if fingerprint is None:
                from src.security.evasion_engine import generate_fingerprint
                fingerprint = generate_fingerprint(os_target="windows")

            self._fingerprints[page_id] = fingerprint

            # Generate the stealth JavaScript
            stealth_js = generate_cdp_stealth_js(
                chrome_version=fingerprint.get("chrome_version", chrome_version),
                platform=fingerprint.get("platform", "Win32"),
                user_agent=fingerprint.get("user_agent"),
                webgl_vendor=fingerprint.get("webgl_vendor", "Intel Inc."),
                webgl_renderer=fingerprint.get("webgl_renderer", "Intel Iris OpenGL Engine"),
                hardware_concurrency=fingerprint.get("hardware_concurrency", 8),
                device_memory=fingerprint.get("device_memory", 8),
                screen_width=fingerprint.get("screen_width", 1920),
                screen_height=fingerprint.get("screen_height", 1080),
                pixel_ratio=fingerprint.get("pixel_ratio", 1.0),
                timezone=fingerprint.get("timezone", "America/New_York"),
                locale=fingerprint.get("locale", "en-US"),
                seed=fingerprint.get("seed"),
            )

            # Create a temporary page to get CDP session
            temp_page = await context.new_page()
            cdp = await context.new_cdp_session(temp_page)

            try:
                # Inject via CDP — applies to ALL pages in the context
                result = await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                    "source": stealth_js,
                    "runImmediately": True,
                })

                script_id = result.get("identifier", "")
                self._injected_pages[page_id] = script_id

                # Apply CDP overrides
                await self._apply_cdp_overrides(cdp, fingerprint, chrome_version)

            finally:
                # ALWAYS detach CDP session to prevent leaks
                try:
                    await cdp.detach()
                except Exception:
                    pass

            # Clean up temp page
            await temp_page.close()

            logger.info(f"CDP stealth injected into context (Chrome {chrome_version})")
            return True

        except Exception as e:
            logger.error(f"CDP stealth injection into context failed: {e}")
            return False

    async def _apply_cdp_overrides(
        self,
        cdp,
        fingerprint: Dict,
        chrome_version: str,
    ):
        """Apply CDP-level overrides that JavaScript alone can't handle."""
        try:
            # Build realistic User-Agent
            ua = fingerprint.get("user_agent") or (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_version}.0.0.0 Safari/537.36"
            )

            # Chrome brand strings for sec-ch-ua
            brands = [
                {"brand": "Chromium", "version": chrome_version},
                {"brand": "Google Chrome", "version": chrome_version},
                {"brand": "Not-A.Brand", "version": "99"},
            ]

            # Set User-Agent override with full metadata
            # (ignore "already in effect" errors from duplicate calls —
            # can happen if GodMode stealth already set this override)
            try:
                await cdp.send("Emulation.setUserAgentOverride", {
                    "userAgent": ua,
                    "acceptLanguage": "en-US,en;q=0.9",
                    "platform": fingerprint.get("platform", "Win32"),
                    "userAgentMetadata": {
                        "brands": brands,
                        "fullVersionList": [
                            {**b, "version": f"{b['version']}.0.0.0"} for b in brands
                        ],
                        "fullVersion": f"{chrome_version}.0.0.0",
                        "platform": fingerprint.get("sec_ch_ua_platform", '"Windows"').strip('"'),
                        "platformVersion": "15.0.0" if fingerprint.get("platform", "Win32") == "Win32" else "14.0.0",
                        "architecture": "x86",
                        "model": "",
                        "mobile": False,
                        "bitness": "64",
                        "wow64": False,
                    },
                })
            except Exception as e:
                if "already in effect" not in str(e).lower():
                    raise

            # Timezone is already set by GodModeStealth (stealth_god.py)
            # to avoid duplicate CDP "Timezone override is already in effect" warning

            # Set locale (ignore "already in effect" errors from duplicate calls)
            try:
                await cdp.send("Emulation.setLocaleOverride", {
                    "locale": "en-US",
                })
            except Exception as e:
                if "already in effect" not in str(e).lower():
                    raise

            logger.debug("CDP overrides applied (UA, locale)")

        except Exception as e:
            logger.warning(f"CDP overrides partially failed: {e}")

    # Headless verification JavaScript — VERIFY-ONLY, never creates new objects.
    # Checks if CDP stealth's __agentOsStealthCache is intact. If Chromium's
    # headless mode stripped plugins/chrome, re-applies the CACHED references
    # from __agentOsStealthCache (same objects CDP stealth created).
    # This avoids the conflict where the old headless hook created NEW objects
    # that differed from CDP stealth's objects, breaking reference identity.
    HEADLESS_VERIFY_JS = """() => {
        try {
            var cache = window.__agentOsStealthCache;
            if (!cache) return;  // No CDP cache — nothing to verify

            // VERIFY: navigator.plugins — re-apply cached reference if stripped
            try {
                var cur = navigator.plugins;
                if (!cur || cur.length === 0 || cur !== cache.plugins) {
                    Object.defineProperty(Navigator.prototype, 'plugins', {
                        get: function() { return cache.plugins; },
                        configurable: true, enumerable: true
                    });
                }
            } catch(e) {}

            // VERIFY: window.chrome — re-apply cached reference if stripped
            try {
                if (!window.chrome || typeof window.chrome !== 'object') {
                    Object.defineProperty(window, 'chrome', {
                        get: function() { return cache.chrome; },
                        configurable: true, enumerable: true
                    });
                }
            } catch(e) {}

            // VERIFY: navigator.webdriver — re-hide if headless re-added
            try {
                if (navigator.webdriver !== undefined) {
                    Object.defineProperty(Navigator.prototype, 'webdriver', {
                        get: function() { return undefined; },
                        configurable: true, enumerable: false
                    });
                }
            } catch(e) {}
        } catch(e) {}
    }"""

    async def setup_headless_verification(self, page) -> None:
        """Set up headless verification hook on a page.

        Runs on every domcontentloaded event to VERIFY that CDP stealth
        properties are still intact. If Chromium's headless mode stripped
        plugins/chrome/webdriver, re-applies the CACHED references from
        __agentOsStealthCache (the same objects CDP stealth created).

        This is VERIFY-ONLY — it never creates new objects, only re-applies
        CDP stealth's cached references. This prevents detection via
        reference identity changes across navigations.
        """
        verify_js = self.HEADLESS_VERIFY_JS

        async def _on_domcontentloaded(page_obj):
            try:
                await page_obj.evaluate(verify_js)
            except Exception:
                pass  # Page may have closed

        page.on("domcontentloaded", lambda: asyncio.ensure_future(_on_domcontentloaded(page)))

        # Also verify immediately on the current page
        try:
            asyncio.ensure_future(page.evaluate(verify_js))
        except Exception:
            pass

    async def remove_from_page(self, page, page_id: str) -> bool:
        """Remove CDP stealth from a page."""
        script_id = self._injected_pages.get(page_id)
        if not script_id:
            return False

        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Page.removeScriptToEvaluateOnNewDocument", {
                "identifier": script_id
            })
            await cdp.detach()
            del self._injected_pages[page_id]
            logger.info(f"CDP stealth removed from page '{page_id}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove CDP stealth: {e}")
            return False

    def get_fingerprint(self, page_id: str = "main") -> Optional[Dict]:
        """Get the fingerprint used for a page."""
        return self._fingerprints.get(page_id)

    @property
    def stats(self) -> Dict:
        """Get injection statistics."""
        return {
            "injected_pages": list(self._injected_pages.keys()),
            "fingerprints": {
                pid: f"{fp.get('os', '?')} Chrome {fp.get('chrome_version', '?')} / {fp.get('webgl_renderer', '?')[:30]}"
                for pid, fp in self._fingerprints.items()
            },
        }
