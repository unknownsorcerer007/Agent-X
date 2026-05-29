# Agent X — Stealth System Documentation

**Version:** 4.0.0
**Date:** 2026-05-29
**Classification:** Internal — Stealth Layer Audit & Validation

---

## 1. Full Inventory of Stealth Techniques

### Layer 1: CDP Stealth (`src/core/cdp_stealth.py` — 1203 lines)

Injected via `Page.addScriptToEvaluateOnNewDocument` — runs **BEFORE** any page scripts.

| # | Technique | Target | Line Range |
|---|-----------|--------|------------|
| 1 | `navigator.webdriver` deletion | Bot detection (DataDome, Cloudflare) | L118-L141 |
| 2 | Playwright property cleanup (`__playwright`, `cdc_*`) | Playwright detection | L151-L169 |
| 3 | Selenium property cleanup | Legacy bot detection | L171-L189 |
| 4 | Permissions API spoofing | Permission fingerprinting | L192-L210 |
| 5 | Plugins array mock | Navigator.plugins check | L212-L245 |
| 6 | `window.chrome` object mock | Chrome-only feature test | L247-L278 |
| 7 | WebGL vendor/renderer spoofing | GPU fingerprinting | L280-L320 |
| 8 | Canvas 2D noise injection | Canvas fingerprinting | L322-L365 |
| 9 | AudioContext fingerprint noise | Audio fingerprinting | L367-L395 |
| 10 | WebRTC IP leak prevention | IP leak detection | L397-L420 |
| 11 | Screen object spoofing | Screen fingerprinting | L422-L445 |
| 12 | Navigator properties spoofing | Navigator fingerprinting | L447-L470 |
| 13 | `Notification.permission` mock | Permission check bypass | L472-L485 |
| 14 | Error stack trace cleaning | Playwright stack detection | L487-L510 |
| 15 | Timing attack mitigation | Performance-based detection | L512-L530 |
| 16 | FingerprintJS/ClientJS blocking | Popular fingerprint libraries | L532-L555 |
| 17 | CDP/Playwright artifact cleanup | CDP detection vectors | L557-L580 |
| 18 | Iframe protection | Recursive iframe injection | L582-L600 |
| 19 | `toString()` native-look | Function inspection | L86-L105 |

### Layer 2: God Mode Stealth (`src/core/stealth_god.py` — 969 lines)

Advanced evasion for high-security targets.

| # | Technique | Target |
|---|-----------|--------|
| 1 | Runtime bytecode obfuscation | Code inspection |
| 2 | Variable name randomization | Pattern detection |
| 3 | Anti-debugger traps | DevTools detection |
| 4 | Timing randomization | Consistency-based detection |
| 5 | MutationObserver protection | DOM change monitoring |

### Layer 3: Adaptive Stealth (`src/core/adaptive_stealth.py` — 74 lines)

Dynamic layer selection based on target site security level.

| # | Technique | Target |
|---|-----------|--------|
| 1 | Site security level detection | Adaptive response |
| 2 | CDP vs God Mode selection | Performance vs evasion trade-off |
| 3 | Per-domain strategy memory | Learning from past successes |

### Layer 4: Supplementary Stealth JS (`src/core/stealth.py` — 221 lines)

Features NOT covered by CDP stealth, injected via `add_init_script`.

| # | Technique | Target | CDP Overlap? |
|---|-----------|--------|-------------|
| 1 | Notification API full mock | Advanced fingerprinters | ❌ No — CDP only sets `permission` |
| 2 | Battery API mock | Battery fingerprinting | ❌ No — not in CDP |
| 3 | Font enumeration block | Font-based fingerprinting | ❌ No — not in CDP |
| 4 | Beacon API interception | Telemetry blocking | ❌ No — not in CDP |
| 5 | Challenge detection observer | Dynamic challenge detection | ❌ No — not in CDP |
| 6 | Navigator consistency guard | Re-definition protection | ✅ Partial — reinforces CDP |

### Layer 5: Request Interception (`src/core/stealth.py` — 157 lines)

Network-level blocking of detection scripts.

| # | Technique | Domains Blocked |
|---|-----------|----------------|
| 1 | Bot detection script blocking | 28 domains (recaptcha, hcaptcha, perimeterx, datadome, kasada, etc.) |
| 2 | Fake human verification responses | 12 services (recaptcha, perimeterx, datadome, cloudflare, kasada, arkose, etc.) |

---

## 2. Overlap / Conflict Audit

### Finding: Duplicate `navigator.webdriver` Override

**Location:**
- `cdp_stealth.py` L137-L141: Defines `get: () => undefined` on `Navigator.prototype`
- `supplementary_stealth.js` L208-L218: Also defines `get: () => undefined` on `Navigator.prototype`

**Impact:** LOW — Both set identical values (`undefined`), so the effective behavior is the same. The second is a no-op reinforcer.

**Decision:** Keep both. CDP stealth is the primary authority. The supplementary guard acts as a defense-in-depth in case headless Chromium strips the CDP override post-navigation.

### Finding: `Notification.permission` in Both CDP and Supplementary

**Location:**
- `cdp_stealth.py` L472-L485: Sets `Notification.permission = 'default'`
- `supplementary_stealth.js` L54-L93: Full Notification constructor mock

**Impact:** LOW — CDP sets the static property. Supplementary provides a full mock with constructor, methods, and instance properties.

**Decision:** Keep both. They serve different purposes — CDP handles the simple check, supplementary handles advanced fingerprinters that test the constructor.

### Finding: `toString()` Override — Single Source of Truth

**Status:** ✅ NO CONFLICT

The `_nativeFnMap` pattern in CDP stealth is the SOLE mechanism for making overridden functions look native. No other `toString` overrides exist in the codebase.

---

## 3. Breakage Audit

### Finding: WebGL vendor/renderer Defaults Applied to All Platforms

**Severity:** 🔴 CRITICAL
**Location:** `cdp_stealth.py` default params

**Before Fix:**
```python
webgl_vendor="Intel Inc."       # Hardcoded
webgl_renderer="Intel Iris OpenGL Engine"  # Hardcoded
```

**Problem:** All 12 browser profiles (including 4 macOS profiles) reported an Intel GPU. Apple Silicon Macs do not have Intel GPUs — this is an immediate bot signal.

**After Fix:**
```python
webgl_vendor=None   # Auto-selected based on platform
webgl_renderer=None # Auto-selected based on platform
```

Platform mapping:
| Platform | GPU Vendor | GPU Renderer |
|----------|-----------|--------------|
| macOS | Apple Inc. | Apple GPU |
| Windows | Rotated (Intel/NVIDIA/AMD/Google ANGLE) | Rotated |
| Linux | Rotated (Intel/NVIDIA/AMD) | Rotated |

### Finding: `sec-ch-ua-mobile` Always `?0`

**Severity:** 🟠 HIGH
**Location:** `browser.py` `_build_headers()`

**Before Fix:** Always `?0` regardless of device type.

**After Fix:** Derived from User-Agent:
```python
is_mobile = "Mobile" in profile.user_agent or "Android" in profile.user_agent
headers["sec-ch-ua-mobile"] = "?1" if is_mobile else "?0"
```

### Finding: No Duplicate Overrides of Core Properties

All CDP-level properties (webdriver, plugins, chrome, WebGL, canvas, audio, screen, navigator) are ONLY set in `cdp_stealth.py`. The supplementary JS explicitly does NOT override any of these.

---

## 4. Coherence Audit

### User-Agent ↔ Client Hints ↔ Platform Coherence

| Profile | User-Agent | sec-ch-ua | platform | Status |
|---------|-----------|-----------|----------|--------|
| Win Chrome 146 | `Windows NT 10.0; Win64; x64` | `"Chromium";v="146"` | `Win32` | ✅ Coherent |
| macOS Chrome 146 | `Macintosh; Intel Mac OS X 10_15_7` | `"Chromium";v="146"` | `MacIntel` | ✅ Coherent |
| Linux Chrome 146 | `X11; Linux x86_64` | `"Chromium";v="146"` | `Linux x86_64` | ✅ Coherent |
| Win Edge 146 | `Windows NT 10.0; Win64; x64 Edg/146` | `"Microsoft Edge";v="146"` | `Win32` | ✅ Coherent |

### GPU ↔ OS Coherence (After Fix)

| OS | GPU | Coherence |
|----|-----|-----------|
| macOS | Apple GPU | ✅ Apple Silicon Macs use Apple GPU |
| Windows | Intel/NVIDIA/AMD | ✅ Common Windows GPUs |
| Linux | Intel/NVIDIA/AMD | ✅ Common Linux GPUs |

### Screen/Viewport Consistency

All profiles have `screen_width` and `screen_height` matching the `viewport` dimensions. This is intentional — the viewport represents the browser window size, which typically matches the screen resolution on desktop.

⚠️ **Note:** On high-DPI displays (Retina), the physical resolution differs from the logical/CSS resolution. `device_scale_factor` (pixel_ratio) handles this correctly.

### Canvas/Audio Noise Stability

The seed for canvas and audio noise is derived from `hash(webgl_renderer)`, ensuring:
1. **Same renderer → same noise pattern** (consistent per profile)
2. **Different renderer → different noise pattern** (diversity across sessions)
3. **Survives re-injection** after browser crash recovery

---

## 5. Live Verification Notes

### Recommended Test Targets

| Target | URL | Purpose |
|--------|-----|---------|
| Sannysoft | `bot.sannysoft.com` | Basic bot detection |
| Pixelscan | `pixelscan.net` | Browser fingerprinting |
| CreepJS | `abrahamjuliot.github.io/creepjs` | Advanced fingerprinting |
| Browserleaks Canvas | `browserleaks.com/canvas` | Canvas fingerprinting |
| Browserleaks WebGL | `browserleaks.com/webgl` | WebGL fingerprinting |
| FingerprintJS Demo | `fingerprint.com/demo` | Commercial fingerprinting |
| Bot Detection | `deviceandbrowserinfo.com/are_you_a_bot` | Bot-or-not test |
| Cloudflare Turnstile | `dash.cloudflare.com/turnstile` | Turnstile challenge |
| DataDome Protected | `www.leboncoin.fr` | DataDome protection |

### Expected Results (After All Fixes)

| Check | Expected Result |
|-------|----------------|
| navigator.webdriver | `undefined` |
| navigator.plugins | Array with 3+ items |
| window.chrome | Present with runtime property |
| WebGL vendor | Matches claimed OS |
| Canvas fingerprint | Stable per session, different across sessions |
| Audio fingerprint | Stable per session |
| Screen size | Matches viewport |
| sec-ch-ua | Matches User-Agent Chrome version |
| sec-ch-ua-mobile | `?1` for mobile, `?0` for desktop |
| Notification.permission | `default` |

---

## 6. Known Limitations & Trade-offs

| Limitation | Reason | Trade-off |
|-----------|--------|-----------|
| WebGL vendor is randomly selected per launch | No real GPU info available | Plausible deniability over exact accuracy |
| Canvas noise may affect image quality | Required for fingerprint randomization | Security over pixel-perfect rendering |
| Free proxy fallback adds latency | Ensures IP shielding | Privacy over speed |
| God Mode stealth adds ~200ms per navigation | Advanced evasion takes time | Evasion over speed |
| Headless verification hook runs on every domcontentloaded | Ensures stealth survives | Minor CPU overhead |

---

## 7. Fixes Applied in This Hardening

| ID | Fix | Impact |
|----|-----|--------|
| CRIT-2 | Auto-select WebGL vendor/renderer per platform | Eliminates GPU/OS incoherence |
| HIGH-2 | Derive sec-ch-ua-mobile from User-Agent | Eliminates mobile/desktop contradiction |
| MED-1 | Atomic cookie key write | Prevents key corruption on crash |
| MED-3 | Align database.enabled default with behavior | Eliminates config confusion |

All fixes maintain backward compatibility and do NOT remove or replace any existing stealth techniques.
