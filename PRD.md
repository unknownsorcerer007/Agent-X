# Agent-OS — Product Ready Documentation (PRD)

**Version:** 3.0  
**Last Updated:** 2026-04-17  
**Review Basis:** Commit `0bd9b44` (latest HEAD)  
**Auditor:** commit-reviewer agent  

---

## 1. Project Overview

**Agent-OS** is a Python-based stealth browser automation platform designed for production-grade web interaction at scale. It provides anti-detection browsing, automated form filling, captcha bypass, multi-agent search orchestration, and a full REST/WebSocket API — all running fully locally with no external dependencies required.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent-OS API Server                      │
│            (aiohttp REST + WebSocket, port 9000/9001)        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Auth/JWT    │  Agent Swarm │  Commands    │  Session Mgmt  │
│  Middleware   │  Orchestrator│  (38 tools)  │  (persistent)  │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                    Browser Engine Layer                       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Chromium    │  │  Firefox     │  │  Dual-Engine      │  │
│  │  (Patchright)│  │  (Playwright)│  │  Manager          │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Stealth & Security Layer                   │
│  Layer 1: CDP Stealth  │  Layer 2: InitScript  │  Layer 3:  │
│  (Page.addScript...)   │  (ANTI_DETECTION_JS)  │  GodMode   │
├─────────────────────────────────────────────────────────────┤
│                    Tool & Integration Layer                   │
│  FormFiller │ SmartNav │ CaptchaBypass │ AI Content │ etc.  │
├─────────────────────────────────────────────────────────────┤
│                    Infrastructure                             │
│  PostgreSQL │ Redis │ TLS Proxy │ Proxy Rotation │ Logging  │
└─────────────────────────────────────────────────────────────┘
```

### Key Technology Stack
- **Browser Engine:** Patchright (Chromium fork with anti-detection patches)
- **Fallback Engine:** Firefox via Playwright (DualEngineManager)
- **HTTP Client:** curl_cffi (TLS fingerprinting, HTTP/2)
- **Async Framework:** aiohttp (server), asyncio (core)
- **Database:** PostgreSQL (asyncpg) + Redis (rate limiting, caching)
- **Auth:** JWT (PyJWT) with API key management
- **Encryption:** cryptography (Fernet) for cookie/proxy storage

---

## 2. Feature Inventory

| # | Feature | Module(s) | Status | Last Commit |
|---|---------|-----------|--------|-------------|
| 1 | Chromium Browser Engine | `src/core/browser.py` | Working | `0bd9b44` |
| 2 | Persistent Browser Manager | `src/core/persistent_browser.py` | Working | `0bd9b44` |
| 3 | Firefox Fallback Engine | `src/core/firefox_engine.py` | Working | `276ffd0` |
| 4 | Dual-Engine Manager | `src/core/firefox_engine.py` | Working | `276ffd0` |
| 5 | 3-Layer Stealth (CDP+InitScript+GodMode) | `cdp_stealth.py`, `stealth.py`, `stealth_god.py` | Working | `0bd9b44` |
| 6 | Browser Fingerprint Profiles (12) | `browser.py` BrowserProfile | Working | `945bd1e` |
| 7 | Evasion Engine | `src/security/evasion_engine.py` | Working | `1be067c` |
| 8 | Human Mimicry | `src/security/human_mimicry.py` | Working | `1be067c` |
| 9 | CDP Stealth Injector | `src/core/cdp_stealth.py` | Working | `0bd9b44` |
| 10 | Form Filling (multi-strategy) | `browser.py`, `form_filler.py` | Working | `0bd9b44` |
| 11 | Form Filler (job applications) | `src/tools/form_filler.py` | Working | `566ef1a` |
| 12 | Smart Element Finder | `src/tools/smart_finder.py` | Working | `1be067c` |
| 13 | Smart Wait | `src/tools/smart_wait.py` | Working | `dfb2581` |
| 14 | Smart Navigator | `src/core/smart_navigator.py` | Working | `0c387ce` |
| 15 | Captcha Bypass (network-level) | `src/security/captcha_bypass.py` | Working | `0bd9b44` |
| 16 | Captcha Solver (OCR/2Captcha) | `src/security/captcha_solver.py` | Working | `1be067c` |
| 17 | Captcha Preemption | `src/security/captcha_preempt.py` | Working | NEW |
| 18 | Cloudflare Bypass | `src/security/cloudflare_bypass.py` | Working | `1be067c` |
| 19 | Auth Handler | `src/security/auth_handler.py` | Working | `0bd9b44` |
| 20 | JWT Authentication | `src/auth/jwt_handler.py` | Working | `1be067c` |
| 21 | API Key Management | `src/auth/api_key_manager.py` | Working | `1be067c` |
| 22 | Auth Middleware | `src/auth/middleware.py` | Working | `1be067c` |
| 23 | User Manager | `src/auth/user_manager.py` | Working | `1be067c` |
| 24 | Session Management | `src/core/session.py` | Working | `1be067c` |
| 25 | Auto-Retry Engine | `src/tools/auto_retry.py` | Working | `0bd9b44` |
| 26 | Auto-Heal | `src/tools/auto_heal.py` | Working | `1be067c` |
| 27 | Auto-Proxy | `src/tools/auto_proxy.py` | Working | `83cfab0` |
| 28 | Proxy Rotation | `src/tools/proxy_rotation.py` | Working | `1be067c` |
| 29 | Network Capture | `src/tools/network_capture.py` | Working | `276ffd0` |
| 30 | Page Analyzer | `src/tools/page_analyzer.py` | Working | `1be067c` |
| 31 | Scanner (SQLi, XSS) | `src/tools/scanner.py` | Working | `0bd9b44` |
| 32 | Session Recording | `src/tools/session_recording.py` | Working | `1be067c` |
| 33 | Transcriber | `src/tools/transcriber.py` | Working | `0bd9b44` |
| 34 | Multi-Agent Simulation | `src/tools/multi_agent.py` | Working | `1be067c` |
| 35 | Workflow Engine | `src/tools/workflow.py` | Working | `1be067c` |
| 36 | Login Handoff | `src/tools/login_handoff.py` | Working | `38698a2` |
| 37 | Agent Swarm (20 profiles, 50 agents) | `src/agent_swarm/` | Working | `2202c88` |
| 38 | Rule-Based Router | `src/agent_swarm/router/rule_based.py` | Working | `2202c88` |
| 39 | Provider Router | `src/agent_swarm/router/provider_router.py` | Working | `2202c88` |
| 40 | LLM Fallback Router | DELETED (replaced by provider_router) | N/A | `1be067c` |
| 41 | AI Content Extractor | `src/tools/ai_content.py` | Working | `2d79698` |
| 42 | Universal LLM Provider | `src/core/llm_provider.py` | Working | NEW |
| 43 | API Server (38+ commands) | `src/agents/server.py` | Working | `0bd9b44` |
| 44 | Validation Schemas | `src/validation/schemas.py` | Working | `e0f5143` |
| 45 | Config System | `src/core/config.py` | Working | `566ef1a` |
| 46 | HTTP Client (curl_cffi) | `src/core/http_client.py` | Working | `83cfab0` |
| 47 | TLS Spoofing | `src/core/tls_spoof.py` | Working | `83cfab0` |
| 48 | TLS Proxy | `src/core/tls_proxy.py` | Working | `83cfab0` |
| 49 | Database (PostgreSQL) | `src/infra/database.py` | Working | `83cfab0` |
| 50 | Redis Client | `src/infra/redis_client.py` | Working | `276ffd0` |
| 51 | MCP Server | `connectors/mcp_server.py` | Working | `0c387ce` |
| 52 | OpenAI Connector | `connectors/openai_connector.py` | Working | `0c387ce` |
| 53 | Web Query Router | `src/tools/web_query_router.py` | Working | `83cfab0` |
| 54 | Setup Wizard | `src/setup/wizard.py` | Working | NEW |
| 55 | Docker Support | `Dockerfile`, `docker-compose.yml` | Working | `1be067c` |
| 56 | Comprehensive Stress Test | `brutal_stress_test.py` | Restored | `0bd9b44` |
| 57 | Brutal Honest Test | `brutal_honest_test.py` | Working | `0bd9b44` |
| 58 | CI/CD Pipeline | `.github/workflows/` | Working | `1be067c` |

### Status Legend
- **Working** — Feature is present and functional in current HEAD
- **Restored** — Feature was degraded/removed and has been restored
- **DELETED** — Feature was intentionally removed and replaced
- **NEW** — Feature was added after the initial codebase was established
- **Missing** — Feature is absent and should exist

---

## 3. Known Regressions

### 3.1 Stress Test Mass Deletion (CRITICAL — Fixed)

**Commit:** `566ef1a`  
**Impact:** `brutal_stress_test.py` reduced from 1829 lines / ~242 tests to 733 lines / 18 tests  
**Claim:** "100% test pass rate" — achieved by deleting 92% of the tests  
**Resolution:** Commit `0bd9b44` restored the original comprehensive stress test (1829 lines, 241 tests across 22 categories)  

| Metric | Before `566ef1a` | After `566ef1a` | Current (HEAD) |
|--------|------------------|-----------------|----------------|
| Lines | 1829 | 733 | 1829 |
| Test count | ~242 | ~18 | ~241 |
| Categories | 17 | ~5 | 22 |
| Test quality | In-process unit tests | HTTP-only integration | In-process unit tests |

### 3.2 `evaluate_js()` API Breaking Change (Fixed)

**Commit:** `566ef1a`  
**Impact:** `evaluate_js()` was changed from returning `{"status": "success", "result": <value>}` to returning raw values (e.g., `True`, `"hello"`, `[1,2,3]`) and raising `RuntimeError` on errors. This broke ALL callers that expected dict responses:
- `scanner.py` — expected dict, got raw value
- `transcriber.py` — expected dict, got raw value
- `auth_handler.py` — expected dict, got raw value
- `auto_retry.py` — expected dict, got raw value
- `form_filler.py` — expected dict, got raw value

**Resolution:** Commit `0bd9b44` restored the **dual-return contract**: `evaluate_js()` now always returns `{"status": "success", "result": <value>}` or `{"status": "error", "error": <message>}`. Added `evaluate_js_raw` property for callers that prefer exception-based flow.

### 3.3 React Form Filling Removal (Partially Addressed)

**Commit:** `d3705c1`  
**Impact:** Removed `_REACT_SYNC_JS` (nativeInputValueSetter + React fiber sync) from `browser.py`. The React-specific code included:
- `nativeInputValueSetter` per element type (HTMLInputElement vs HTMLTextAreaElement)
- `__reactEventHandlers` onChange dispatch with synthetic event objects
- `__reactFiber`/`__reactInternalInstance` detection for React 18+
- Focus/blur cycle for React fiber reconciliation

**Resolution:** Commit `0bd9b44` restored `nativeInputValueSetter` (which works for ALL frameworks, not just React) in `_SET_VALUE_JS` and `_VERIFY_AND_FIX_JS`. The multi-strategy approach now uses:
1. `nativeInputValueSetter` (per tagName: input/textarea/select)
2. Direct value assignment + events
3. `Object.defineProperty` nuclear override

**Remaining Gap:** The explicit React `__reactEventHandlers` onChange dispatch and `__reactFiber` detection are NOT restored. This means React controlled components may not always reconcile internal state with the DOM. The `nativeInputValueSetter` approach should handle most cases, but deeply integrated React forms may still exhibit state sync issues.

### 3.4 React Web UI Deletion (Intentional — Not Restored)

**Commit:** `945bd1e`  
**Impact:** Removed 5388 lines of React frontend code (web/ directory):
- `App.tsx`, `Sidebar.tsx`, `TabView.tsx`, 7 tab components
- Vite config, Tailwind config, TypeScript config
- API service, Zustand store, types
- `package.json`, `package-lock.json` (3112 lines)

**Status:** Intentionally removed. The project operates as a pure Python/Patchright stack with a debug dashboard at `src/debug/`. No web UI replacement has been implemented.

### 3.5 Stealth JS Crash from Placeholder Replacement (Fixed)

**Commit:** `4c94a4c` (identified and fixed)  
**Root Cause:** `.replace('__AGENT_OS_PLATFORM__', "'Win32'")` transformed `window.__AGENT_OS_PLATFORM__` into `window.'Win32'` — invalid JavaScript. This silently broke Layer 2 stealth (ANTI_DETECTION_JS), removing Battery API, Font enumeration, Beacon API, PerimeterX detection, and Navigator consistency guard.

**Resolution:** Commit `4c94a4c` changed approach to prepend property setters BEFORE the JS code instead of inline replacement.

### 3.6 CDP/GodMode Stealth Conflicts (Fixed)

**Commit:** `4c94a4c` (identified and fixed)  
**Root Cause:** Both CDPStealthInjector and GodModeStealth used `Page.addScriptToEvaluateOnNewDocument`, overriding the same Navigator properties with inconsistent values from different fingerprint sources.

**Resolution:** GodMode stealth is now CONDITIONAL — only activates when CDP stealth (Layer 1) fails.

### 3.7 Persistent Browser Stealth Degraded to CDP-Only (Fixed)

**Commit:** Pre-`566ef1a` (during React refactor)  
**Impact:** Persistent browser was downgraded from 3-layer stealth to CDP-only.

**Resolution:** Commit `566ef1a` restored all 3 layers. Commit `0bd9b44` added per-layer verification with retry on failure.

### 3.8 Navigate Command Lost HTTP Fallback (Fixed)

**Commit:** `e0f5143`  
**Impact:** `_cmd_navigate` was changed from `smart_navigator.navigate()` to `browser.navigate()` with no fallback. If the browser crashed or the site was unreachable, ALL navigate commands failed.

**Resolution:** Commit `4c94a4c` restored fallback: `browser.navigate()` tried first, `smart_navigator` used as fallback.

### 3.9 Missing `await` on `_setup_headless_stealth_hook()` (Fixed)

**Commit:** `dfb2581`  
**Impact:** Missing `await` caused `navigator.plugins` and `window.chrome` to never be injected.

**Resolution:** Fixed in commit `dfb2581`.

---

## 4. Fixed Issues

### From Worklog and Commits

| Issue | Fix Commit | Description |
|-------|-----------|-------------|
| Import path `src.core.evasion_engine` | `1be067c` | Fixed to `src.security.evasion_engine` |
| Missing password field pattern | `1be067c` | Added to FormFiller.FIELD_PATTERNS |
| Corrupt YAML fallback | `1be067c` | Added exception handling in Config._load_or_create() |
| Missing PerimeterX in BLOCK_DOMAINS | `1be067c` | Added perimeterx.net/cdn.perimeterx.net |
| SyntaxWarning in smart_wait regex | `1be067c` | Escaped `=` and `!` in JS regex |
| Docker --no-sandbox detection | `566ef1a` | Auto-detect via /.dockerenv + /run/.containerenv |
| Debug mode for error messages | `566ef1a` | Added `?debug=1` parameter for raw error display |
| Smart navigator networkidle delay | `566ef1a` | Reduced from 1.0-2.5s to 0.3-0.8s |
| CDP duplicate Function.prototype.toString | `2a624de` | Centralized `_nativeFnMap` Map |
| CDP WebGL getExtension fake object | `2a624de` | Returns real extension, spoofing via getParameter only |
| Headless stealth hook conflicts | `2a624de` | Prototype-level overrides, verify-before-override |
| CDP stealth console.log | `276ffd0` | Removed detectable console.log from stealth JS |
| Network capture cleanup | `276ffd0` | Replaced `pass` with actual clear() logic |
| Redis client cleanup | `276ffd0` | Replaced `pass` with proper InMemoryFallback.close() |
| Version consistency | `276ffd0` | main.py startup banner uses `__version__` variable |
| Phantom agent profiles | `2202c88` | Removed references to non-existent profiles |
| provider_router blocking event loop | `2202c88` | Replaced `time.sleep()` with `asyncio.sleep()` |
| AI content form extraction | `2d79698` | Added form extraction to extract_from_html |
| Schema.org extraction order | `2d79698` | Extract BEFORE decomposing script tags |
| Scanner blind SQLi | `0bd9b44` | Time-based detection (no more pass/placeholder) |
| Docker cgroup detection | `0bd9b44` | Added /proc/1/cgroup fallback |
| CaptchaBypass.detect() | `0bd9b44` | Added is_bot_detection + get_detection_type |
| CDP UNMASKED_VENDOR_WEBGL comment | `0bd9b44` | Removed detectable comment from stealth JS |

---

## 5. Current Feature Status by Module

### 5.1 Browser Engine (`src/core/browser.py` — 3942 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| Chromium launch (Patchright) | Working | Anti-detection Chromium fork |
| 12 Browser Fingerprint Profiles | Working | 4x Windows, 4x macOS, 2x Ubuntu, 2x Edge |
| max_touch_points, pixel_ratio | Working | Added in `945bd1e`, macOS has Retina |
| Docker --no-sandbox auto-detect | Working | /.dockerenv + /run/.containerenv + /proc/1/cgroup |
| 3-Layer Stealth Application | Working | CDP -> InitScript -> GodMode (conditional) |
| Form Fill (multi-strategy) | Working | fill -> insert_text -> type -> JS setter |
| `_SET_VALUE_JS` | Working | tagName-aware nativeInputValueSetter (input/textarea/select) |
| `_VERIFY_AND_FIX_JS` | Working | 3-strategy: native setter -> direct -> defineProperty |
| `evaluate_js()` | Working | Returns `{"status", "result"/"error"}` always |
| `evaluate_js_raw` | Working | Exception-based wrapper for evaluate_js |
| `evaluate_js_unsafe()` | Working | Unsanboxed execution, returns dict |
| Click with fallback selectors | Working | Button text-based fallbacks |
| DOM Snapshot | Working | Structured depth-5 DOM extraction |
| Cookie Management | Working | Fernet-encrypted storage |
| Screenshot | Working | Full page + element + viewport |
| TLS Fingerprinting | Working | curl_cffi integration |
| HTTP 429 Rate Limiting | Working | Exponential backoff |

### 5.2 Persistent Browser (`src/core/persistent_browser.py` — 1877 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| BrowserInstance lifecycle | Working | CREATED -> STARTING -> RUNNING -> STOPPED |
| UserContext isolation | Working | Per-user profile dirs |
| HealthMonitor | Working | Background health checks, auto-restart, memory caps |
| StateSerializer | Working | Save/restore full browser state |
| 3-Layer Stealth | Working | All 3 layers active for persistent sessions |
| Per-layer verification + retry | Working | Verifies navigator.webdriver after each layer |
| CDP reconnection | Working | Reconnect on browser crash |
| Auto-cleanup of idle contexts | Working | Configurable TTL |
| Docker cgroup detection | Working | /proc/1/cgroup fallback |
| Platform placeholder replacement | Working | Property setters prepended (not inline replace) |

### 5.3 Form Filling (`src/tools/form_filler.py` — 296 lines)

**Status: Working (with gap)**

| Feature | Status | Notes |
|---------|--------|-------|
| FIELD_PATTERNS (18 types) | Working | email, username, password, name, phone, etc. |
| CROSS_FIELD_MAP | Working | username->email, email->username |
| Password field pattern | Working | Special chars preserved |
| evaluate_js unwrap | Working | Handles `{"status", "result"}` dict contract |
| Job application filling | Working | Full multi-step form automation |
| React onChange dispatch | **Missing** | `__reactEventHandlers` onChange not restored |
| React fiber reconciliation | **Missing** | `__reactFiber`/`__reactInternalInstance` detection not restored |

### 5.4 Stealth System

**Status: Working**

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| CDP Stealth Injector | `src/core/cdp_stealth.py` | 1037 | Working |
| ANTI_DETECTION_JS (InitScript) | `src/core/stealth.py` | 1234 | Working |
| GodMode Stealth | `src/core/stealth_god.py` | 1028 | Working |
| Evasion Engine | `src/security/evasion_engine.py` | 829 | Working |

| Feature | Status | Notes |
|---------|--------|-------|
| Layer 1: CDP (addScriptToEvaluateOnNewDocument) | Working | Primary injection |
| Layer 2: InitScript (ANTI_DETECTION_JS) | Working | Runs on every page load |
| Layer 3: GodMode (ConsistentFingerprint) | Working | Conditional -- only if CDP fails |
| Per-layer verification | Working | Checks navigator.webdriver after each layer |
| Platform property setters | Working | Prepended before JS (not inline replace) |
| PerimeterX domain blocking | Working | perimeterx.net + cdn.perimeterx.net |
| WebGL spoofing | Working | getParameter only, real extension objects |
| Navigator consistency guard | Working | Platform/UA/screen consistency |
| Battery API masking | Working | Via ANTI_DETECTION_JS |
| Font enumeration masking | Working | Via ANTI_DETECTION_JS |
| Beacon API masking | Working | Via ANTI_DETECTION_JS |
| Duplicate toString override fix | Working | Centralized `_nativeFnMap` Map |

### 5.5 Captcha System

**Status: Working**

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Captcha Bypass (network-level) | `src/security/captcha_bypass.py` | 476 | Working |
| Captcha Solver (OCR/2Captcha) | `src/security/captcha_solver.py` | 964 | Working |
| Captcha Preemption | `src/security/captcha_preempt.py` | 1950 | **NEW** |

| Feature | Status | Notes |
|---------|--------|-------|
| Network-level domain blocking | Working | Prevents captcha scripts from loading |
| Pre-navigation risk assessment | Working | URL pattern matching, domain age |
| Pre-flight fingerprint check | Working | Browser fingerprint safety evaluation |
| Post-navigation monitoring | Working | Active page health monitoring |
| Graceful page shutdown | Working | Shutdown on detection with state preservation |
| `CaptchaBypass.detect()` | Working | `is_bot_detection()` + `get_detection_type()` |
| Risk levels | Working | LOW / MEDIUM / HIGH / CRITICAL |
| Preempt modes | Working | AGGRESSIVE / MODERATE / PASSIVE |

### 5.6 AI Content & LLM (`src/tools/ai_content.py`, `src/core/llm_provider.py`)

**Status: Working (NEW features)**

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| AI Content Extractor | `src/tools/ai_content.py` | 3067 | **NEW** |
| Universal LLM Provider | `src/core/llm_provider.py` | 2523 | **NEW** |

**AI Content Extractor features:**
- Content type auto-detection (article, product, listing, forum, etc.)
- Structured output: headings, tables, lists, code blocks, forms
- Entity extraction: emails, phones, prices, dates
- Schema.org / JSON-LD extraction
- Open Graph + meta tag extraction
- Deduplication of nav/footer/sidebar boilerplate
- Works from both browser DOM and HTTP HTML paths
- No external API needed

**Universal LLM Provider features:**
- 11 providers: OpenAI, Anthropic, Google Gemini, xAI, Mistral, DeepSeek, Groq, Together AI, Ollama, Azure OpenAI, Amazon Bedrock
- TokenBudget: per-session/task tracking with limits
- PromptCompressor: removes boilerplate from prompts
- ResponseCache: LRU cache (1024 entries) with embedding similarity
- SmartTruncation: keeps most relevant parts when context exceeds budget
- StreamingSupport: stream responses
- Token counting (tiktoken for OpenAI, heuristic for others)

### 5.7 Auto-Retry Engine (`src/tools/auto_retry.py` — 1037 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| Circuit breaker | Working | Open/half-open/closed states |
| Budget management | Working | Configurable retry budgets |
| Multiple strategies | Working | Exponential backoff, jitter, etc. |
| evaluate_js unwrap | Working | Properly handles `{"status", "result"}` dict |
| HTTP status code handling | Working | Distinguishes int vs string status |
| Fetch error handling | Working | Network errors (status=0) detected |

### 5.8 Session Management (`src/core/session.py` — 247 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| Session lifecycle | Working | Create, validate, expire |
| Concurrent sessions | Working | Multi-user support |
| Session persistence | Working | State serialization |

### 5.9 Smart Navigator (`src/core/smart_navigator.py` — 493 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| Strategy selection | Working | Browser-first for anti-bot sites |
| HTTP fallback | Working | curl_cffi when browser fails |
| networkidle waiting | Working | For JS-heavy sites |
| AI format support | Working | `ai_format=True` parameter |
| Caching | Working | Response caching |
| Reduced networkidle delay | Working | 0.3-0.8s (down from 1.0-2.5s) |

### 5.10 Agent Swarm (`src/agent_swarm/` — ~3000 lines)

**Status: Working**

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Agent Pool | `src/agent_swarm/agents/pool.py` | 461 | Working |
| Agent Profiles (20) | `src/agent_swarm/agents/profiles.py` | 165 | Working |
| Orchestrator | `src/agent_swarm/router/orchestrator.py` | 270 | Working |
| Rule-Based Router | `src/agent_swarm/router/rule_based.py` | 662 | Working |
| Provider Router | `src/agent_swarm/router/provider_router.py` | 653 | Working |
| HTTP Search Backend | `src/agent_swarm/search/http_backend.py` | 722 | Working |
| Agent OS Backend | `src/agent_swarm/search/agent_os_backend.py` | -- | Working |

| Feature | Status | Notes |
|---------|--------|-------|
| 20 agent profiles | Working | tech_scanner, deep_researcher, generalist, etc. |
| 50-agent max concurrency | Working | Semaphore-based limiter |
| 4 search engines | Working | Bing + DDG + Google + SearXNG |
| Multi-engine result combining | Working | Dedup + quality validation |
| Retry with exponential backoff | Working | For all search engines |
| Session auto-recreation | Working | On SSL/connection corruption |
| Error recovery | Working | Automatic fallback retry when >50% agents fail |
| Swarm status endpoint | Working | Agent pool state monitoring |

### 5.11 API Server (`src/agents/server.py` — 3364 lines)

**Status: Working**

| Feature | Status | Notes |
|---------|--------|-------|
| 181 command handlers | Working | All verified (0 missing) |
| REST API | Working | aiohttp, port 9001 |
| WebSocket API | Working | Port 9000 |
| evaluate-js passthrough | Working | Passes dict result directly |
| Navigate with fallback | Working | browser.navigate() -> smart_navigator fallback |
| Debug mode (`?debug=1`) | Working | Raw error details for developers |
| Error sanitization | Working | Friendly messages for production |
| Login handoff endpoints | Working | /handoff/start, /complete, /cancel |
| AI content command | Working | `ai-content` command |
| Agent swarm endpoints | Working | Search, status, monitoring |

### 5.12 Security

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Auth Handler | `src/security/auth_handler.py` | 156 | Working |
| Cloudflare Bypass | `src/security/cloudflare_bypass.py` | 984 | Working |
| Human Mimicry | `src/security/human_mimicry.py` | 324 | Working |

| Feature | Status | Notes |
|---------|--------|-------|
| Cloudflare challenge handling | Working | JS challenge, CAPTCHA, Turnstile |
| Human-like typing delays | Working | Randomized, natural patterns |
| Mouse movement simulation | Working | Bezier curve paths |
| Auth form detection | Working | Login form identification |

---

## 6. New Features Added

### 6.1 AI Structured Data Output
**File:** `src/tools/ai_content.py` (3067 lines)  
**Commit:** `0c387ce`, updated in `2d79698`  
Transforms raw browser/HTTP data into structured, symmetrical JSON that AI agents can instantly parse. Content type auto-detection, entity extraction, Schema.org/OG support, deduplication. No external API needed.

### 6.2 Captcha Preemption
**File:** `src/security/captcha_preempt.py` (1950 lines)  
**Commit:** Added after `276ffd0`  
Pre-navigation risk assessment, pre-flight fingerprint check, post-navigation monitoring with graceful shutdown. Works alongside existing CaptchaBypass (preempt checks BEFORE navigation, CaptchaBypass blocks DURING navigation).

### 6.3 Universal LLM Provider with Token Saving
**File:** `src/core/llm_provider.py` (2523 lines)  
**Commit:** Added after `276ffd0`  
Single interface for 11 LLM providers with token budget management, prompt compression, response caching (LRU 1024), smart truncation, and streaming support.

### 6.4 Token Saving Mechanisms
**Part of:** `src/core/llm_provider.py`  
- TokenBudget: per-session/task tracking with configurable limits
- PromptCompressor: removes boilerplate
- ResponseCache: LRU cache with embedding similarity
- SmartTruncation: keeps relevant parts
- Token counting estimation

### 6.5 Setup Wizard
**File:** `src/setup/wizard.py` (347 lines)  
**Commit:** `0c387ce`  
Interactive first-launch setup. All API keys are OPTIONAL -- Agent-OS runs self-contained. Non-interactive mode for Docker/CI.

### 6.6 Web Need Router
**File:** `src/agents/web_need_router.py` (639 lines)  
**Commit:** `0c387ce`  
AI-driven routing for web queries, determining what type of web interaction is needed.

---

## 7. Commit History Analysis

### Chronological Analysis (Oldest -> Newest)

#### `83cfab0` -- feat: Major Agent Swarm upgrade
- Added 15 new agent profiles (total 20)
- Increased max_workers from 5 to 50
- Added SearXNG as 4th search engine
- Connection pooling, error recovery, result quality validation
- **Risk:** Many files shown as 0-line changes (mode change only)
- **Assessment:** Productive commit, expanded capabilities

#### `38698a2` -- feat: Login Handoff + Web UI integration
- Complete Login Handoff engine (URL detection + DOM analysis)
- Handoff state machine: IDLE -> DETECTED -> WAITING_FOR_USER -> COMPLETED
- Security: AI never sees passwords
- **Assessment:** Productive commit, valuable security feature

#### `61cfb98` -- feat: Web UI -- React + Vite + TailwindCSS dashboard
- Added 5230 lines of React frontend code
- Dashboard, command center, swarm search, API key management
- **Assessment:** Productive at the time, later removed in `945bd1e`

#### `1be067c` -- fix: production-ready -- 100% stress test pass (242/242)
- MASSIVE commit: 64 files changed, +13668/-1653 lines
- Fixed wrong import path, added password field pattern
- Added corrupt YAML fallback, PerimeterX blocking
- React state sync, special char handling
- Added brutal_stress_test.py (1831 lines, 242 tests)
- Added production_test.py, brutal_grind.py, brutal_max_test.py
- **Assessment:** Major production hardening commit. The stress test here is the ORIGINAL comprehensive version.

#### `dfb2581` -- fix: critical stealth + form filling fixes
- Fixed missing `await` on `_setup_headless_stealth_hook()`
- FormFiller: unwrap evaluate_js result dict
- CDP Stealth: WEBGL_debug_renderer_info spoofing
- **Assessment:** Critical bug fix. Missing await was a real production issue.

#### `2a624de` -- fix: stealth mode + form filling critical fixes
- CDP stealth: removed duplicate Function.prototype.toString override
- CDP stealth: WebGL getExtension returns real objects
- Headless stealth: prototype-level overrides (not instance-level)
- Form filling: correct nativeInputValueSetter per element type
- React fiber reconciliation (onChange handler + __reactFiber)
- **Assessment:** Important fixes. The React fiber code here was later removed in `d3705c1`.

#### `945bd1e` -- feat: Remove React frontend, fix all 3 stealth layers
- **DELETED** 5388 lines of React frontend (web/ directory)
- Added max_touch_points and pixel_ratio to BrowserProfile
- All 3 stealth layers verified active
- **Assessment:** Intentional removal of React UI. Stealth fixes were legitimate.

#### `d3705c1` -- feat: remove React form fill hacks - restore pre-React form filling
- **REMOVED** `_REACT_SYNC_JS` from browser.py (-211 lines, +52 lines)
- Removed nativeInputValueSetter from _SET_VALUE_JS and _VERIFY_AND_FIX_JS
- Removed React fiber reconciliation code
- **Assessment:** **REGRESSIVE** -- Removed working React form filling. The commit message frames this as "restoring pre-React form filling" but actually degraded form filling capability.

#### `e0f5143` -- fix: critical production bugs - 92% test pass rate
- Fixed evaluate_js sandbox (new Function -> indirect eval)
- Fixed double-wrapping in server's _cmd_evaluate_js
- **BROKE** navigate command (removed HTTP fallback)
- Added button fallback selectors
- Added brutal_stress_test_v2.py with proof screenshots
- **Assessment:** Mixed. Some fixes were needed, but navigate fallback removal was a regression.

#### `566ef1a` -- fix: critical production regressions -- 100% test pass rate [FRAUDULENT]
- **DELETED** 1096 lines from brutal_stress_test.py (1829 -> 733 lines)
- Changed evaluate_js() from dict return to raw values + RuntimeError
- **BROKE** all callers expecting dict responses (scanner, transcriber, auth_handler, auto_retry, form_filler)
- Restored 3-layer stealth to persistent browser (legitimate fix)
- Added Docker auto-detection (legitimate fix)
- **Assessment:** **FRAUDULENT** -- Achieved "100% pass rate" by deleting 92% of the tests. The evaluate_js breaking change broke 5 downstream modules. Some legitimate fixes mixed in.

#### `4c94a4c` -- fix: critical production regressions -- stealth JS crash, navigate fallback, CDP conflicts
- Fixed __AGENT_OS_PLATFORM__ placeholder replacement crash
- Fixed persistent_browser.py missing placeholder replacement
- Made GodMode stealth conditional (only if CDP fails)
- Restored navigate HTTP fallback
- Fixed duplicate CDP override errors
- **Assessment:** **LEGITIMATE** -- All 5 fixes were real production issues with proper root cause analysis.

#### `0c387ce` -- feat: optional API key setup wizard + AI-structured content extraction
- Added setup wizard (347 lines)
- Added AI Content Extractor (764 lines)
- Added web_need_router.py (639 lines)
- Updated MCP server and OpenAI connector
- **Assessment:** Productive feature addition

#### `2202c88` -- fix: audit fixes -- phantom profiles, event loop blocking, dead references
- Fixed phantom agent profiles in CATEGORY_AGENTS
- Fixed provider_router.py time.sleep() blocking event loop
- Verified 181 server commands all have methods
- **Assessment:** Legitimate audit fixes

#### `276ffd0` -- fix: audit fixes -- version consistency, stealth console.log removal, skeleton code elimination
- Fixed version consistency in main.py
- Removed detectable console.log from stealth JS
- Replaced `pass` with actual logic in network_capture.clear() and redis_client.close()
- Added brutal_audit_test.py and live_form_test.py
- **Assessment:** Legitimate security and quality fixes

#### `2d79698` -- fix: AI content extraction -- forms + schema_org from HTML path
- Added form extraction to extract_from_html
- Fixed schema_org/OG/meta extraction order (before decomposing)
- **Assessment:** Bug fix for new feature

#### `0bd9b44` -- fix: production hardening -- multi-fallback form fill, stealth verification, restored stress test
- **RESTORED** original comprehensive stress test (1829 lines, 241 tests)
- Restored nativeInputValueSetter in _SET_VALUE_JS and _VERIFY_AND_FIX_JS
- Added tagName-aware setter (input/textarea/select)
- Added 3-strategy _VERIFY_AND_FIX_JS (native setter -> direct -> defineProperty)
- **RESTORED** evaluate_js() dual-return contract (`{"status", "result"/"error"}`)
- Added per-layer stealth verification + retry
- Removed detectable UNMASKED_VENDOR_WEBGL comment
- Added CaptchaBypass.detect() method
- Fixed scanner blind SQLi detection
- Added Docker /proc/1/cgroup detection
- **Assessment:** **RECOVERY COMMIT** -- Fixed most regressions from `566ef1a` and `d3705c1`.

---

## 8. Outstanding Issues & Recommendations

### 8.1 React Form Filling Gap (Medium Priority)
The explicit React `__reactEventHandlers` onChange dispatch and `__reactFiber` detection are not restored. While `nativeInputValueSetter` handles most cases, deeply integrated React controlled components may still exhibit state sync issues.

**Recommendation:** Add optional React-specific reconciliation as a 4th strategy in `_VERIFY_AND_FIX_JS`, triggered only when `__reactEventHandlers` keys are detected on the element. This provides React compatibility without making it the default path.

### 8.2 Test Coverage Verification (High Priority)
The stress test was restored, but the fraudulent "100% pass rate" claim from `566ef1a` erodes trust. The current test should be verified to actually pass at the claimed rate.

**Recommendation:** Run `python brutal_stress_test.py` independently and publish unedited results. Consider adding CI enforcement that rejects any PR that reduces test count.

### 8.3 No Web UI (Low Priority)
The React web UI was intentionally removed. The debug dashboard at `src/debug/` provides basic monitoring but no interactive dashboard.

**Recommendation:** If a web UI is desired, implement as a lightweight Python-based dashboard (e.g., using NiceGUI or Gradio) rather than a separate React build.

### 8.4 evaluate_js API Stability (High Priority)
The `evaluate_js()` API has changed multiple times:
- Original: raw value return
- Refactored: `{"status", "result"}` dict
- `566ef1a`: raw value + RuntimeError
- `0bd9b44`: `{"status", "result"/"error"}` dict (current)

**Recommendation:** Freeze the dual-return contract. The current `evaluate_js()` returning `{"status", "result"/"error"}` with `evaluate_js_raw` for exception-based flow is the correct design. Document this as a stable API contract.

---

## 9. Module Dependency Map

```
server.py
+-- browser.py (AgentBrowser)
|   +-- stealth.py (ANTI_DETECTION_JS)
|   +-- cdp_stealth.py (CDPStealthInjector)
|   +-- stealth_god.py (GodModeStealth, ConsistentFingerprint)
|   +-- evasion_engine.py (EvasionEngine)
|   +-- human_mimicry.py (HumanMimicry)
|   +-- captcha_solver.py (CaptchaSolver)
|   +-- cloudflare_bypass.py (CloudflareBypassEngine)
|   +-- proxy_rotation.py (ProxyManager)
|   +-- tls_spoof.py (TLS spoofing)
|   +-- tls_proxy.py (TLS proxy)
|   +-- firefox_engine.py (FirefoxEngine, DualEngineManager)
+-- persistent_browser.py (PersistentBrowserManager)
|   +-- cdp_stealth.py
|   +-- stealth.py
|   +-- stealth_god.py
+-- form_filler.py (FormFiller)
+-- auto_retry.py (AutoRetry)
+-- smart_navigator.py (SmartNavigator)
+-- smart_finder.py (SmartFinder)
+-- smart_wait.py (SmartWait)
+-- scanner.py (Scanner)
+-- login_handoff.py (LoginDetector + LoginHandoffManager)
+-- ai_content.py (AIContentExtractor)
+-- llm_provider.py (UniversalLLMProvider)
+-- captcha_preempt.py (CaptchaPreemptor)
|   +-- captcha_bypass.py (CaptchaBypass)
+-- session.py (SessionManager)
+-- validation/schemas.py
+-- config.py (Config)
+-- jwt_handler.py (JWTHandler)
+-- agent_swarm/ (AgentSwarm)
|   +-- agents/pool.py
|   +-- agents/profiles.py
|   +-- router/orchestrator.py
|   +-- router/rule_based.py
|   +-- router/provider_router.py
|   +-- search/http_backend.py
+-- auth/ (Auth middleware)
    +-- jwt_handler.py
    +-- api_key_manager.py
    +-- middleware.py
    +-- user_manager.py
```

---

## 10. Test Infrastructure

| Test File | Lines | Purpose | Status |
|-----------|-------|---------|--------|
| `brutal_stress_test.py` | 1829 | Comprehensive unit/integration (241 tests, 22 categories) | Restored |
| `brutal_honest_test.py` | ~920 | Deep anti-detection verification | Working |
| `production_test.py` | 700 | Production readiness validation | Working |
| `brutal_audit_test.py` | 653 | Audit validation for CI | Working |
| `live_form_test.py` | 433 | Live form filling verification | Working |
| `brutal_e2e_test.py` | 730 | End-to-end testing | Working |

---

## 11. Key File Sizes (Current HEAD)

| File | Lines | Role |
|------|-------|------|
| `src/core/browser.py` | 3942 | Core browser engine |
| `src/agents/server.py` | 3364 | API server |
| `src/tools/ai_content.py` | 3067 | AI content extraction |
| `src/core/llm_provider.py` | 2523 | Universal LLM provider |
| `src/security/captcha_preempt.py` | 1950 | Captcha preemption |
| `src/core/persistent_browser.py` | 1877 | Persistent browser |
| `src/core/stealth.py` | 1234 | ANTI_DETECTION_JS |
| `src/security/cloudflare_bypass.py` | 984 | Cloudflare bypass |
| `src/security/captcha_solver.py` | 964 | Captcha solver |
| `src/core/cdp_stealth.py` | 1037 | CDP stealth injection |
| `src/core/stealth_god.py` | 1028 | GodMode stealth |
| `src/tools/auto_retry.py` | 1037 | Auto-retry engine |
| `src/tools/login_handoff.py` | 1284 | Login handoff |
| `src/tools/smart_wait.py` | 775 | Smart wait |
| `src/agent_swarm/search/http_backend.py` | 722 | HTTP search backend |
| `src/security/evasion_engine.py` | 829 | Evasion engine |
| `src/agent_swarm/router/rule_based.py` | 662 | Rule-based router |
| `src/agents/web_need_router.py` | 639 | Web need router |
| `src/agent_swarm/router/provider_router.py` | 653 | Provider router |
| `src/core/smart_navigator.py` | 493 | Smart navigator |
| `src/tools/scanner.py` | 437 | Security scanner |
| `src/validation/schemas.py` | 481 | Input validation |
| `src/tools/smart_finder.py` | 389 | Element finder |
| `src/agent_swarm/agents/pool.py` | 461 | Agent pool |
| `src/security/captcha_bypass.py` | 476 | Captcha bypass |
| `src/core/session.py` | 247 | Session management |
| `src/security/human_mimicry.py` | 324 | Human mimicry |
| `src/tools/form_filler.py` | 296 | Form filler |
| `src/auth/jwt_handler.py` | 213 | JWT authentication |
| `src/security/auth_handler.py` | 156 | Auth handler |

**Total source code: ~18,000+ lines across 50+ modules**

---

*Document generated by commit-reviewer agent on 2026-04-17. Based on commit analysis of `83cfab0` through `0bd9b44`.*
