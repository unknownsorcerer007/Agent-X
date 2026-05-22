# Bug Tracker — Agent-OS Deep Analysis
## Status: 🟢 = Fixed, 🔴 = Not Fixed

### CRITICAL BUGS — ALL FIXED

1. 🟢 **Engine conflict: 3 stealth engines overriding same properties** — FIXED
   - Rewrote `stealth.py`: now `SUPPLEMENTARY_STEALTH_JS` (7KB) with ONLY supplementary features
   - Removed all conflicting overrides: webdriver, plugins, chrome, WebGL, canvas, audio, etc.
   - CDP stealth (26KB) is now SOLE owner of core anti-detection
   - GodMode (26KB) only activates if CDP fails

2. 🟢 **stealth.py instance-level navigator overrides** — FIXED
   - New SUPPLEMENTARY_STEALTH_JS uses only `Navigator.prototype` (consistent with CDP)
   - No more `Object.defineProperty(navigator, ...)` instance-level overrides

3. 🟢 **`__AGENT_OS_*__` detectable global variables** — FIXED
   - Removed all `window.__AGENT_OS_PLATFORM__`, `__AGENT_OS_CORES__`, etc.
   - Supplementary JS is self-contained with no global state

4. 🟢 **Adaptive scraper `arguments[0]` misuse** — FIXED
   - Changed from `(threshold) => { const stored = arguments[0]; }` 
   - To `(args) => { const stored = args.fp; const threshold = args.threshold; }`
   - Now properly passes both fingerprint AND threshold to JS

5. 🟢 **`_cmd_adaptive_cleanup` calls non-existent `cleanup_expired()`** — FIXED
   - Changed to `scraper.cleanup()` which is the actual method name

6. 🟢 **Screenshot format hardcoded to "png"** — FIXED
   - Now reads `data.get("format", "png")` and `data.get("quality", 80)`
   - Passes both to `browser.screenshot()`

7. 🟢 **15+ server commands missing `page_id` support** — FIXED
   - Added `page_id=data.get("page_id", "main")` to:
     fill-form, click, type, press, screenshot, get-content, get-dom,
     scroll, hover, select, upload, wait, evaluate-js, back, forward,
     reload, get-links, get-images, right-click, context-action,
     drag-drop, drag-offset, double-click, clear-input, checkbox,
     get-text, get-attr

8. 🟢 **PageAnalyzer instantiated fresh on every command** — FIXED
   - Added lazy-init `_get_page_analyzer()` with `asyncio.Lock`
   - All 7 page analyzer commands now use shared instance

9. 🟢 **CaptchaPreemptor + CaptchaBypass instantiated on every captcha command** — FIXED
   - Added lazy-init `_get_captcha_preemptor()` with `asyncio.Lock`
   - All 6 captcha commands now use shared instance
   - Fixed `__dict__` serialization to filter SQLAlchemy internal fields

10. 🟢 **GodMode Chrome versions outdated (116-136)** — FIXED
    - Updated to: 146(30%), 145(25%), 144(20%), 143(15%), 136(5%), 133(3%), 131(2%)
    - Now consistent with browser profiles (Chrome 143-146)

11. 🟢 **persistent_browser.py had conflicting stealth injection** — FIXED
    - Removed placeholder replacement logic
    - Now uses CDP primary + supplementary add_init_script (same as browser.py)

12. 🟢 **Test assertions checking for removed features** — FIXED
    - Updated `test_all.py` to check for supplementary features (Notification, Battery, sendBeacon)
    - Removed assertions for webdriver/plugins/chrome in supplementary JS
