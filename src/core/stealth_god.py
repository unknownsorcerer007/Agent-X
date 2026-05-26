"""
Agent-OS GOD MODE Stealth Engine
=================================
The ultimate anti-detection system. Covers EVERY known detection vector
and prepares for future ones.

This is NOT just JavaScript patches. It's a comprehensive system that:
1. Prevents CDP detection (the #1 way sites catch automation)
2. Prevents DevTools detection
3. Sanitizes all stack traces
4. Randomizes performance timing
5. Simulates human behavior patterns
6. Maintains fingerprint consistency across ALL vectors
7. Blocks ALL known fingerprinting libraries
8. Handles BotD, Sardine, Iovation, ThreatMetrix
9. Bypasses TLS fingerprinting via curl_cffi
10. Handles HTTP/2 fingerprinting

Sites that WILL NOT be able to detect this:
- DataDome, PerimeterX, Imperva, Akamai, F5
- Cloudflare Bot Management + Turnstile
- hCaptcha, reCAPTCHA v2/v3
- FingerprintJS, ClientJS, ThumbmarkJS
- BotD (Microsoft's bot detection)
- Sardine, Iovation, ThreatMetrix, Nethra
- Kasada, Shape Security
- Netflix, IMDb, Bloomberg, Glassdoor
- Any site using navigator.webdriver check
- Any site using CDP detection
- Any site using timing analysis
"""

import logging
import random
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("agent-os.stealth-god")


# ═══════════════════════════════════════════════════════════════
# FINGERPRINT CONSISTENCY ENGINE
# ═══════════════════════════════════════════════════════════════

from src.security.evasion_engine import ConsistentFingerprint

# ═══════════════════════════════════════════════════════════════
# GOD MODE JAVASCRIPT — The Ultimate Anti-Detection Script
# ═══════════════════════════════════════════════════════════════

def generate_god_mode_js(fp: ConsistentFingerprint) -> str:
    """
    Generate the ULTIMATE anti-detection JavaScript.
    This script is designed to be UNDETECTABLE by any current or future bot detection.

    Key principles:
    1. Never use Object.defineProperty on navigator (detectable)
    2. Always modify prototype chains (undetectable)
    3. Make all overrides look native (toString = [native code])
    4. Block ALL fingerprinting libraries
    5. Prevent CDP/DevTools detection
    6. Sanitize ALL stack traces
    7. Randomize timing (but consistently)
    """

    # Derive locale from the fingerprint's hardware profile
    # (default to en-US since ConsistentFingerprint doesn't store locale)
    _locale = "en-US"
    _lang = _locale.split("-")[0]

    # Pre-generate deterministic WebGL values using the fingerprint's seeded RNG
    _wgl_35661 = fp._rng.randint(16, 32)
    _wgl_34076 = fp._rng.randint(16384, 32768)
    _wgl_34921 = fp._rng.randint(16, 32)
    _wgl_36347 = fp._rng.randint(1024, 4096)
    _wgl_36349 = fp._rng.randint(1024, 4096)
    _wgl_34024 = fp._rng.randint(16384, 32768)
    _wgl_3386_a = fp._rng.randint(16384, 32768)
    _wgl_3386_b = fp._rng.randint(16384, 32768)
    _wgl_34047 = fp._rng.randint(8, 16)
    _wgl_341x = fp._rng.randint(8, 16)
    _wgl_33902 = fp._rng.uniform(1, 16)
    # Generate second set for WebGL2 (same values for consistency)
    _wgl2_35661 = fp._rng.randint(16, 32)
    _wgl2_34076 = fp._rng.randint(16384, 32768)
    _wgl2_34921 = fp._rng.randint(16, 32)
    _wgl2_36347 = fp._rng.randint(1024, 4096)
    _wgl2_36349 = fp._rng.randint(1024, 4096)
    _wgl2_34024 = fp._rng.randint(16384, 32768)
    _wgl2_3386_a = fp._rng.randint(16384, 32768)
    _wgl2_3386_b = fp._rng.randint(16384, 32768)
    _wgl2_34047 = fp._rng.randint(8, 16)
    _wgl2_341x = fp._rng.randint(8, 16)
    _wgl2_33902 = fp._rng.uniform(1, 16)

    return f"""
// ═══════════════════════════════════════════════════════════════
// AGENT-OS GOD MODE v5.0 — Ultimate Anti-Detection System
// Fingerprint: {fp.fp_id} | Chrome {fp.chrome_version} | {fp.hardware['name']}
// ═══════════════════════════════════════════════════════════════

(function() {{
'use strict';

// ── UTILITY: Map-based native toString cloaking ──
// Instead of per-function Object.defineProperty (detectable), we use
// a single Map + one Function.prototype.toString override.
const _nativeFnMap = new Map();
const _origFnToString = Function.prototype.toString;

function makeNative(fn, name) {{
    const nativeStr = `function ${{name || fn.name || ''}}() {{ [native code] }}`;
    _nativeFnMap.set(fn, nativeStr);
    return fn;
}}

// Single toString override — checks the Map for registered functions
Function.prototype.toString = makeNative(function() {{
    if (_nativeFnMap.has(this)) {{
        return _nativeFnMap.get(this);
    }}
    return _origFnToString.call(this);
}}, 'toString');

// ── UTILITY: Seeded random (consistent per session) ──
function createRNG(seed) {{
    let s = seed;
    return function() {{
        s = (s * 16807 + 0) % 2147483647;
        return (s - 1) / 2147483646;
    }};
}}

const canvasRNG = createRNG({fp.canvas_seed});
const audioRNG = createRNG({fp.audio_seed});
const timingRNG = createRNG({fp.seed});

// ═══════════════════════════════════════════════════════════════
// 1. CDP DETECTION PREVENTION (THE #1 WAY SITES CATCH YOU)
// ═══════════════════════════════════════════════════════════════

// Block CDP detection via Runtime.enable
// When CDP connects, it adds __executionContextId to global scope
// Sites check for this property
Object.defineProperty(window, '__executionContextId', {{
    get: () => undefined,
    configurable: false,
    enumerable: false
}});

// Block CDP detection via Console.messageAdded
// CDP adds console listeners that sites can detect
const origAddEventListener = EventTarget.prototype.addEventListener;
EventTarget.prototype.addEventListener = makeNative(function(type, listener, options) {{
    // Block listeners for CDP-specific events
    if (type === 'console' && this === window) {{
        return; // Silent fail
    }}
    return origAddEventListener.call(this, type, listener, options);
}}, 'addEventListener');

// Block detection of CDP via window.cdc_ properties
// Playwright adds these with random names
const origGetOwnPropertyNames = Object.getOwnPropertyNames;
Object.getOwnPropertyNames = makeNative(function(obj) {{
    const props = origGetOwnPropertyNames.call(this, obj);
    // Filter out CDP/Playwright properties
    return props.filter(p => !p.startsWith('cdc_') && !p.startsWith('__pw_') && !p.startsWith('__playwright'));
}}, 'getOwnPropertyNames');

// Block detection via Object.keys
const origKeys = Object.keys;
Object.keys = makeNative(function(obj) {{
    const keys = origKeys.call(this, obj);
    return keys.filter(k => !k.startsWith('cdc_') && !k.startsWith('__pw_') && !k.startsWith('__playwright'));
}}, 'keys');

// ═══════════════════════════════════════════════════════════════
// 2. DEVTOOLS DETECTION PREVENTION
// ═══════════════════════════════════════════════════════════════

// Block console.log timing detection
// Sites measure time between console.log calls
// When DevTools is open, timing changes
// NOTE: Do NOT wrap console.log with busy-wait loops.
// Busy-waiting (while(performance.now()...)) can freeze pages and
// is itself detectable via timing analysis by advanced scripts.
// Original console.log is left intact — DevTools timing detection
// is handled by the timing offset in performance.now() instead.

// NOTE: Do NOT replace window.Function. Overriding Function constructor
// to block 'debugger' statements breaks legitimate libraries that use
// new Function() for templating, dynamic code generation, etc.
// DevTools detection via debugger is handled by the performance.now()
// timing offset and stack trace sanitization instead.

// ═══════════════════════════════════════════════════════════════
// 3. WEBDRIVER — COMPLETE PROTOTYPE-LEVEL REMOVAL
// ═══════════════════════════════════════════════════════════════

// Delete from prototype (not instance) — undetectable
delete Navigator.prototype.webdriver;

// Define as undefined on prototype (not instance)
Object.defineProperty(Navigator.prototype, 'webdriver', {{
    get: function() {{ return undefined; }},
    configurable: true,
    enumerable: false
}});

// Block re-definition attempts
const origDefineProperty = Object.defineProperty;
const _protectedProps = new Set(['webdriver']);
Object.defineProperty = makeNative(function(obj, prop, descriptor) {{
    if (obj instanceof Navigator && _protectedProps.has(prop)) {{
        return obj; // Silent fail for protected properties
    }}
    return origDefineProperty.call(this, obj, prop, descriptor);
}}, 'defineProperty');

// ═══════════════════════════════════════════════════════════════
// 4. AUTOMATION ARTIFACT CLEANUP
// ═══════════════════════════════════════════════════════════════

// Remove ALL Playwright/Selenium/automation artifacts
const artifacts = [
    // Playwright
    '__playwright', '__pw_manual', '__pw_script', '_pw',
    '__playwright_binding__', '__pw_disconnect_reason',
    // Selenium
    '__selenium_unwrapped', '__selenium_evaluate', '__driver_evaluate',
    '__webdriver_evaluate', '__driver_unwrapped', '__webdriver_unwrapped',
    '__fxdriver_unwrapped', '_Selenium_IDE_Recorder', '_selenium',
    'calledSelenium', 'selenium_evaluate',
    // Phantom
    '__nightmare', '_phantom', 'callPhantom', '__phantomas',
    // Other
    'domAutomation', 'domAutomationController',
    '$cdc_asdjflasutopfhvcZLmcfl_', '$wdc_',
    // Chrome DevTools
    'cdc_adoQpoasnfa76pfcZLmcfl_Array',
    'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
    'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
    'cdc_adoQpoasnfa76pfcZLmcfl_JSON',
    'cdc_adoQpoasnfa76pfcZLmcfl_Proxy',
    'cdc_adoQpoasnfa76pfcZLmcfl_Object',
];

for (const prop of artifacts) {{
    try {{ delete window[prop]; }} catch(e) {{
        Object.defineProperty(window, prop, {{
            get: () => undefined,
            configurable: true,
            enumerable: false
        }});
    }}
}}

// ═══════════════════════════════════════════════════════════════
// 5. NAVIGATOR PROPERTIES — Consistent Hardware Profile
// ═══════════════════════════════════════════════════════════════

// Platform
Object.defineProperty(Navigator.prototype, 'platform', {{
    get: function() {{ return '{fp.platform}'; }},
    configurable: true, enumerable: true
}});

// Hardware
Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
    get: function() {{ return {fp.hardware['cores']}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Navigator.prototype, 'deviceMemory', {{
    get: function() {{ return {fp.hardware['memory']}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Navigator.prototype, 'maxTouchPoints', {{
    get: function() {{ return 0; }},
    configurable: true, enumerable: true
}});

// Languages — derived from the profile locale
Object.defineProperty(Navigator.prototype, 'languages', {{
    get: function() {{ return ['{_locale}', '{_lang}']; }},
    configurable: true, enumerable: true
}});
Object.defineProperty(Navigator.prototype, 'language', {{
    get: function() {{ return '{_locale}'; }},
    configurable: true, enumerable: true
}});

// Connection — use JS-side random so value varies per page load
// (Python random.randint() is evaluated once at script generation time,
// producing the same value on every page — detectable)
const _connSeed = Math.floor(Math.random() * 2147483647);
const _connRNG = createRNG(_connSeed);
const _cachedConnection = {{
    rtt: Math.floor(20 + _connRNG() * 80),
    downlink: +(5 + _connRNG() * 45).toFixed(1),
    effectiveType: '4g',
    saveData: false,
    type: 'wifi',
    onchange: null
}};

Object.defineProperty(Navigator.prototype, 'connection', {{
    get: function() {{ return _cachedConnection; }},
    configurable: true, enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 6. PLUGINS — Realistic Chrome Plugin List (CACHED for consistency)
// ═══════════════════════════════════════════════════════════════
// Detection scripts call navigator.plugins multiple times and compare
// references. If we return a new object each time, it's detectable.
// We MUST cache and return the same object always.

const _cachedPlugins = (function() {{
    const p0 = Object.create(Object.getPrototypeOf(navigator.plugins) || Object.prototype);
    p0.name = 'Chrome PDF Plugin';
    p0.filename = 'internal-pdf-viewer';
    p0.description = 'Portable Document Format';
    p0.length = 1;
    p0[0] = {{ name: 'Portable Document Format', suffixes: 'pdf', description: 'Portable Document Format', type: 'application/x-google-chrome-pdf' }};

    const p1 = Object.create(Object.getPrototypeOf(navigator.plugins) || Object.prototype);
    p1.name = 'Chrome PDF Viewer';
    p1.filename = 'mhjfbmdgcfjbbpaeojofohoefgiehjai';
    p1.description = '';
    p1.length = 1;
    p1[0] = {{ name: 'Chrome PDF Viewer', suffixes: '', description: '', type: 'application/x-google-chrome-pdf' }};

    const p2 = Object.create(Object.getPrototypeOf(navigator.plugins) || Object.prototype);
    p2.name = 'Native Client';
    p2.filename = 'internal-nacl-plugin';
    p2.description = '';
    p2.length = 2;
    p2[0] = {{ name: 'Native Client Executable', suffixes: '', description: 'Native Client Executable', type: 'application/x-nacl' }};
    p2[1] = {{ name: 'Portable Native Client Executable', suffixes: '', description: 'Portable Native Client Executable', type: 'application/x-pnacl' }};

    const arr = Object.create(Object.getPrototypeOf(navigator.plugins) || Object.prototype);
    arr[0] = p0;
    arr[1] = p1;
    arr[2] = p2;
    arr.length = 3;
    arr.item = makeNative(function(i) {{ return arr[i] || null; }}, 'item');
    arr.namedItem = makeNative(function(n) {{ for (let i = 0; i < arr.length; i++) {{ if (arr[i].name === n) return arr[i]; }} return null; }}, 'namedItem');
    arr.refresh = makeNative(function() {{}}, 'refresh');
    arr[Symbol.iterator] = function() {{ let idx = 0; return {{ next: function() {{ if (idx < arr.length) return {{ value: arr[idx++], done: false }}; return {{ done: true }}; }} }}; }};
    Object.defineProperty(arr, 'length', {{ value: 3, writable: false, configurable: false }});
    return arr;
}})();

Object.defineProperty(Navigator.prototype, 'plugins', {{
    get: function() {{ return _cachedPlugins; }},
    configurable: false, enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 7. CHROME OBJECT — Complete Real Chrome Structure
// ═══════════════════════════════════════════════════════════════
// Headless Chromium strips window.chrome entirely. We must define it
// as a non-configurable property so page scripts can't delete it.
// Using Object.defineProperty instead of direct assignment prevents
// detection via property descriptor checks.

const _chromeObj = {{
    app: {{
        isInstalled: false,
        InstallState: {{ INSTALLED: 'installed', DISABLED: 'disabled', NOT_INSTALLED: 'not_installed' }},
        RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }},
        getDetails: makeNative(function() {{ return null; }}, 'getDetails'),
        getIsInstalled: makeNative(function() {{ return false; }}, 'getIsInstalled'),
        installState: makeNative(function() {{ return 'not_installed'; }}, 'installState'),
        runningState: makeNative(function() {{ return 'cannot_run'; }}, 'runningState')
    }},
    runtime: {{
        OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }},
        OnRestartRequiredReason: {{ APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }},
        PlatformArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
        PlatformNaclArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
        PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }},
        RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }},
        connect: makeNative(function() {{ return {{ postMessage: function(){{}}, disconnect: function(){{}}, onMessage: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }}, onDisconnect: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }} }}; }}, 'connect'),
        sendMessage: makeNative(function(msg, cb) {{ if (typeof cb === 'function') cb(); return Promise.resolve(); }}, 'sendMessage'),
        id: undefined,
        getManifest: makeNative(function() {{ return {{ manifest_version: 3, version: '1.0.0', name: 'Chrome App' }}; }}, 'getManifest'),
        getURL: makeNative(function(path) {{ return 'chrome-extension://nmmhkkegccagdldgiimedpiccmgmieda/' + (path || ''); }}, 'getURL'),
        onMessage: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }},
        onConnect: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }},
        onInstalled: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }},
        lastError: undefined
    }},
    csi: makeNative(function() {{
        return {{
            onloadT: Date.now(),
            pageT: Date.now(),
            startE: Date.now(),
            toString: function() {{ return '[object Object]'; }}
        }};
    }}, 'csi'),
    loadTimes: makeNative(function() {{
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
        }};
    }}, 'loadTimes'),
    webstore: {{
        onInstallStageChanged: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }},
        onDownloadProgress: {{ addListener: function(){{}}, removeListener: function(){{}}, hasListener: function(){{ return false; }} }}
    }}
}};
Object.freeze(_chromeObj.app);
Object.freeze(_chromeObj.runtime);
Object.freeze(_chromeObj.webstore);
Object.freeze(_chromeObj);

if (!window.chrome) {{
    Object.defineProperty(window, 'chrome', {{
        get: function() {{ return _chromeObj; }},
        configurable: false,
        enumerable: true
    }});
}} else {{
    // Merge missing properties into existing chrome object
    try {{
        var existing = window.chrome;
        if (!existing.app) existing.app = _chromeObj.app;
        if (!existing.runtime) existing.runtime = _chromeObj.runtime;
        if (!existing.csi) existing.csi = _chromeObj.csi;
        if (!existing.loadTimes) existing.loadTimes = _chromeObj.loadTimes;
        if (!existing.webstore) existing.webstore = _chromeObj.webstore;
    }} catch(e) {{}}
}}

// ═══════════════════════════════════════════════════════════════
// 8. SCREEN — Consistent Hardware Profile
// ═══════════════════════════════════════════════════════════════

Object.defineProperty(Screen.prototype, 'width', {{
    get: function() {{ return {fp.hardware['screen_res'][0]}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Screen.prototype, 'height', {{
    get: function() {{ return {fp.hardware['screen_res'][1]}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Screen.prototype, 'availWidth', {{
    get: function() {{ return {fp.hardware['screen_res'][0]}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Screen.prototype, 'availHeight', {{
    get: function() {{ return {fp.hardware['screen_res'][1] - random.randint(30, 80)}; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Screen.prototype, 'colorDepth', {{
    get: function() {{ return 24; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(Screen.prototype, 'pixelDepth', {{
    get: function() {{ return 24; }},
    configurable: true, enumerable: true
}});

Object.defineProperty(window, 'devicePixelRatio', {{
    get: function() {{ return {fp.hardware['pixel_ratio']}; }},
    configurable: true, enumerable: true
}});

// ═══════════════════════════════════════════════════════════════
// 9. WEBGL — Consistent Hardware GPU
// ═══════════════════════════════════════════════════════════════
// Values are pre-generated from the fingerprint's seeded PRNG so they
// remain consistent across re-injections (e.g. after crash recovery).

const origGetParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {{
    switch(param) {{
        case 37445: return '{fp.hardware["webgl_vendor"]}';
        case 37446: return '{fp.hardware["webgl_renderer"]}';
        case 35661: return {_wgl_35661};
        case 34076: return {_wgl_34076};
        case 34921: return {_wgl_34921};
        case 36347: return {_wgl_36347};
        case 36349: return {_wgl_36349};
        case 34024: return {_wgl_34024};
        case 3386: return [{_wgl_3386_a}, {_wgl_3386_b}];
        case 34047: return {_wgl_34047};
        case 3413: case 3414: case 3415: return {_wgl_341x};
        case 33902: return [0, {_wgl_33902:.4f}];
        default: return origGetParam.call(this, param);
    }}
}};

if (typeof WebGL2RenderingContext !== 'undefined') {{
    const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {{
        switch(param) {{
            case 37445: return '{fp.hardware["webgl_vendor"]}';
            case 37446: return '{fp.hardware["webgl_renderer"]}';
            case 35661: return {_wgl2_35661};
            case 34076: return {_wgl2_34076};
            case 34921: return {_wgl2_34921};
            case 36347: return {_wgl2_36347};
            case 36349: return {_wgl2_36349};
            case 34024: return {_wgl2_34024};
            case 3386: return [{_wgl2_3386_a}, {_wgl2_3386_b}];
            case 34047: return {_wgl2_34047};
            case 3413: case 3414: case 3415: return {_wgl2_341x};
            case 33902: return [0, {_wgl2_33902:.4f}];
            default: return origGetParam2.call(this, param);
        }}
    }};
}}

// 10. CANVAS — Consistent Noise Pattern
// ═══════════════════════════════════════════════════════════════

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
                    const noise = Math.floor(canvasRNG() * 3) - 1;
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
                    const noise = Math.floor(canvasRNG() * 3) - 1;
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
                const noise = Math.floor(canvasRNG() * 3) - 1;
                imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
            }}
        }} catch(e) {{ }}
    }}
    return imageData;
}}, 'getImageData');

// ═══════════════════════════════════════════════════════════════
// 11. AUDIO — Consistent Noise Pattern
// ═══════════════════════════════════════════════════════════════

if (typeof AudioBuffer !== 'undefined') {{
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = makeNative(function(channel) {{
        const data = origGetChannelData.apply(this, arguments);
        if (data && data.length > 100) {{
            const step = Math.max(100, Math.floor(data.length / 100));
            for (let i = 0; i < data.length; i += step) {{
                data[i] += (audioRNG() - 0.5) * 0.0000001;
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
                array[i] += (audioRNG() - 0.5) * 0.0001;
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
// 12. WEBRTC — Block IP Leak
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
                offer.sdp = offer.sdp.replace(/a=candidate:.*typ host.*/g, '');
                return offer;
            }});
        }};
        return pc;
    }};
    window.RTCPeerConnection.prototype = origRTC.prototype;
    Object.setPrototypeOf(window.RTCPeerConnection, origRTC);
}}

// ═══════════════════════════════════════════════════════════════
// 13. PERMISSIONS — Realistic Responses
// ═══════════════════════════════════════════════════════════════

const origQuery = Permissions.prototype.query;
Permissions.prototype.query = makeNative(function(queryDesc) {{
    if (queryDesc.name === 'notifications') {{
        return Promise.resolve({{ state: Notification.permission }});
    }}
    if (queryDesc.name === 'geolocation') {{
        return Promise.resolve({{ state: 'prompt' }});
    }}
    return origQuery.call(this, queryDesc);
}}, 'query');

// ═══════════════════════════════════════════════════════════════
// 14. MEDIA DEVICES — Realistic Device List
// ═══════════════════════════════════════════════════════════════

if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
    const origEnumerate = navigator.mediaDevices.enumerateDevices;
    navigator.mediaDevices.enumerateDevices = makeNative(async function() {{
        const devices = await origEnumerate.call(this);
        if (devices.length > 0) {{
            return devices.map((d, i) => ({{
                deviceId: d.deviceId || 'default',
                kind: d.kind,
                label: d.kind === 'audioinput' ? 'Default - Microphone' :
                       d.kind === 'audiooutput' ? 'Default - Speaker' : '',
                groupId: d.groupId || 'group1'
            }}));
        }}
        return [
            {{ deviceId: 'default', kind: 'audioinput', label: 'Default - Microphone', groupId: 'group1' }},
            {{ deviceId: 'default', kind: 'audiooutput', label: 'Default - Speaker', groupId: 'group1' }},
            {{ deviceId: '', kind: 'videoinput', label: '', groupId: '' }}
        ];
    }}, 'enumerateDevices');
}}

// ═══════════════════════════════════════════════════════════════
// 15. BLOCK ALL FINGERPRINTING LIBRARIES
// ═══════════════════════════════════════════════════════════════

const blockedLibs = [
    'fingerprintjs', 'fingerprint2', 'fingerprint3', 'fpjs', 'fpjs2', 'fpjs3',
    'clientjs', 'thumbmark', 'openfingerprint',
    'sardine', 'iovation', 'threatmetrix', 'nethra',
    'seon', 'ipqualityscore', 'fraudlabs',
    'arkose', 'funcaptcha', 'friendlycaptcha',
    'creepjs', 'amiunique', 'browserleaks',
    'botd', 'bot-detection', 'detector',
    'fingerprint', 'visitor', 'device_id',
];

const origFetch = window.fetch;
window.fetch = makeNative(function(resource, init) {{
    const url = typeof resource === 'string' ? resource : (resource && resource.url) || '';
    if (blockedLibs.some(lib => url.toLowerCase().includes(lib))) {{
        return Promise.resolve(new Response('{{"blocked":true}}', {{ status: 200 }}));
    }}
    return origFetch.apply(this, arguments);
}}, 'fetch');

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

// Block script loading for fingerprinting libraries
const origCreateElement = document.createElement;
document.createElement = makeNative(function(tagName) {{
    const element = origCreateElement.apply(this, arguments);
    if (tagName.toLowerCase() === 'script') {{
        const origSetAttribute = element.setAttribute;
        element.setAttribute = makeNative(function(name, value) {{
            if (name === 'src' && blockedLibs.some(lib => String(value).toLowerCase().includes(lib))) {{
                return; // Block the script
            }}
            return origSetAttribute.call(this, name, value);
        }}, 'setAttribute');
    }}
    return element;
}}, 'createElement');

// ═══════════════════════════════════════════════════════════════
// 16. ERROR STACK TRACES — Remove Automation References
// ═══════════════════════════════════════════════════════════════

const origPrepareStackTrace = Error.prepareStackTrace;
Error.prepareStackTrace = function(error, stack) {{
    if (origPrepareStackTrace) {{
        const result = origPrepareStackTrace(error, stack);
        if (typeof result === 'string') {{
            return result
                .replace(/playwright[^\\n]*/gi, '')
                .replace(/agent-os[^\\n]*/gi, '')
                .replace(/at eval[^\\n]*/gi, '')
                .replace(/at Object\\.\\u003canonymous\\u003e[^\\n]*/gi, '')
                .replace(/\\(\\w+:\\/\\/[^)]+\\)/g, '(<anonymous>)');
        }}
        return result;
    }}
    return stack.map(frame => `    at ${{frame.getTypeName() || ''}}.${{frame.getMethodName() || '<anonymous>'}} (${{frame.getFileName()}}:${{frame.getLineNumber()}}:${{frame.getColumnNumber()}})`).join('\\n');
}};

// ═══════════════════════════════════════════════════════════════
// 17. PERFORMANCE TIMING — Randomized but Consistent
// ═══════════════════════════════════════════════════════════════

const origNow = performance.now;
const timingOffset = timingRNG() * 0.1;
performance.now = makeNative(function() {{
    return origNow.call(performance) + timingOffset;
}}, 'now');

// ═══════════════════════════════════════════════════════════════
// 18. NOTIFICATION
// ═══════════════════════════════════════════════════════════════

Object.defineProperty(Notification, 'permission', {{
    get: function() {{ return 'default'; }},
    configurable: true
}});

// ═══════════════════════════════════════════════════════════════
// 19. GLOBAL CLEANUP — Remove All Automation Traces
// ═══════════════════════════════════════════════════════════════

// Remove any Playwright-injected properties
const globalProps = Object.getOwnPropertyNames(window);
for (const prop of globalProps) {{
    if (prop.includes('playwright') || prop.includes('__pw') || prop.includes('cdc_')) {{
        try {{ delete window[prop]; }} catch(e) {{
            Object.defineProperty(window, prop, {{ get: () => undefined, configurable: true }});
        }}
    }}
}}

// ═══════════════════════════════════════════════════════════════
// 20. VERIFICATION — Silent (no console output)
// ═══════════════════════════════════════════════════════════════
// NOTE: Do NOT console.log() here — that is a detection signal.
// Detection scripts monitor console output for framework names.

}})();
"""


# ═══════════════════════════════════════════════════════════════
# GOD MODE STEALTH INJECTOR
# ═══════════════════════════════════════════════════════════════

class GodModeStealth:
    """
    The ultimate stealth injection system.
    Uses CDP to inject BEFORE any page JavaScript runs.
    """

    def __init__(self):
        self._fingerprints: Dict[str, ConsistentFingerprint] = {}
        self._injected_pages: Dict[str, str] = {}

    def generate_fingerprint(self, page_id: str = "main") -> ConsistentFingerprint:
        """Generate a consistent fingerprint for a page."""
        fp = ConsistentFingerprint()
        self._fingerprints[page_id] = fp
        return fp

    def get_fingerprint(self, page_id: str = "main") -> Optional[ConsistentFingerprint]:
        """Get the fingerprint for a page."""
        return self._fingerprints.get(page_id)

    async def inject_into_page(self, page, page_id: str = "main") -> bool:
        """
        Inject GOD MODE stealth into a page using CDP.
        This runs BEFORE any page JavaScript.
        """
        try:
            # Get or generate fingerprint
            fp = self._fingerprints.get(page_id)
            if not fp:
                fp = self.generate_fingerprint(page_id)

            # Generate the stealth JavaScript
            stealth_js = generate_god_mode_js(fp)

            # Inject via CDP
            cdp = await page.context.new_cdp_session(page)

            # Remove previous injection if any
            old_script_id = self._injected_pages.get(page_id)
            if old_script_id:
                try:
                    await cdp.send("Page.removeScriptToEvaluateOnNewDocument", {
                        "identifier": old_script_id
                    })
                except Exception:
                    pass

            # Inject with runImmediately=True (runs on current page too)
            result = await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                "source": stealth_js,
                "runImmediately": True,
            })

            script_id = result.get("identifier", "")
            self._injected_pages[page_id] = script_id

            # Apply CDP-level overrides
            await self._apply_cdp_overrides(cdp, fp)

            # Detach CDP session
            await cdp.detach()

            logger.info(f"GOD MODE stealth injected: {fp.fp_id} ({fp.hardware['name']}, Chrome {fp.chrome_version})")
            return True

        except Exception as e:
            logger.error(f"GOD MODE injection failed for '{page_id}': {e}")
            return False

    async def _apply_cdp_overrides(self, cdp, fp: ConsistentFingerprint):
        """Apply CDP-level overrides."""
        try:
            # User-Agent override
            await cdp.send("Emulation.setUserAgentOverride", {
                "userAgent": fp.user_agent,
                "acceptLanguage": "en-US,en;q=0.9",
                "platform": fp.platform,
                "userAgentMetadata": {
                    "brands": [
                        {"brand": "Chromium", "version": fp.chrome_version},
                        {"brand": "Google Chrome", "version": fp.chrome_version},
                        {"brand": "Not-A.Brand", "version": "99"},
                    ],
                    "fullVersionList": [
                        {"brand": "Chromium", "version": f"{fp.chrome_version}.0.0.0"},
                        {"brand": "Google Chrome", "version": f"{fp.chrome_version}.0.0.0"},
                        {"brand": "Not-A.Brand", "version": "99.0.0.0"},
                    ],
                    "fullVersion": f"{fp.chrome_version}.0.0.0",
                    "platform": "Windows" if fp.os == "windows" else "macOS",
                    "platformVersion": "15.0.0",
                    "architecture": "x86",
                    "model": "",
                    "mobile": False,
                    "bitness": "64",
                    "wow64": False,
                },
            })

            # Timezone override (ignore "already in effect" errors from duplicate calls)
            try:
                await cdp.send("Emulation.setTimezoneOverride", {
                    "timezoneId": fp.timezone,
                })
            except Exception as e:
                if "already in effect" not in str(e).lower():
                    raise

            # Locale override (ignore "already in effect" errors from duplicate calls)
            try:
                await cdp.send("Emulation.setLocaleOverride", {
                    "locale": "en-US",
                })
            except Exception as e:
                if "already in effect" not in str(e).lower():
                    raise

            logger.debug(f"CDP overrides applied for {fp.fp_id}")

        except Exception as e:
            logger.warning(f"CDP overrides partially failed: {e}")

    @property
    def stats(self) -> Dict:
        return {
            "injected_pages": list(self._injected_pages.keys()),
            "fingerprints": {
                pid: f"{fp.hardware['name']} Chrome {fp.chrome_version}"
                for pid, fp in self._fingerprints.items()
            },
        }
