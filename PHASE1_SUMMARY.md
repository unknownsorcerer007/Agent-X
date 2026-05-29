# Phase 1: Architecture Summary & README Checklist

## Architecture Overview

Agent X is an autonomous AI browser engine built on a **layered architecture** with the following major components:

### Core Architecture (5 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT X v4.0.0                           │
├─────────────────────────────────────────────────────────────┤
│  CONNECTOR LAYER    │ MCP, WebSocket, HTTP REST, SSE        │
├─────────────────────┼───────────────────────────────────────┤
│  AGENT LAYER        │ Swarm orchestrator, Multi-agent,      │
│                     │ Web Need Router                         │
├─────────────────────┼───────────────────────────────────────┤
│  TOOL LAYER         │ 209+ tools (AI content, DOM snapshot, │
│                     │ visual testing, token optimizer, etc.)  │
├─────────────────────┼───────────────────────────────────────┤
│  BROWSER LAYER      │ Multi-tab manager, Session recording, │
│                     │ Smart navigator, Proxy rotation         │
├─────────────────────┼───────────────────────────────────────┤
│  STEALTH LAYER      │ CDP Stealth, God Mode, Adaptive,      │
│  (5-layer defense)  │ Evasion engine, Human mimicry, CAPTCHA│
├─────────────────────┼───────────────────────────────────────┤
│  SECURITY LAYER     │ Cloudflare bypass, Auth (JWT+API key),│
│                     │ TLS spoofing, Firefox fallback          │
├─────────────────────┼───────────────────────────────────────┤
│  INFRA LAYER        │ Database (SQLAlchemy), Redis,         │
│                     │ Logging (structlog)                     │
└─────────────────────┴───────────────────────────────────────┘
```

### Key Data Flows

1. **Agent Request Flow**: 
   Client → WebSocket/HTTP → AgentServer → AgentBrowser → Playwright/Patchright → Target Site
   
2. **Stealth Injection Flow**:
   Browser Launch → CDPStealthInjector → Page.addScriptToEvaluateOnNewDocument → JS runs BEFORE page scripts
   Supplementary Stealth JS → add_init_script → Runs after CDP
   Request Interception → Blocks bot detection URLs at network level
   
3. **Cloudflare Bypass Flow**:
   Block detected → ClearanceStore check → CloudflareBypassEngine.solve() → cloudscraper → curl_cffi
   → Domain bypass memory records successful strategy

4. **Auth Flow**:
   Client → AuthMiddleware → JWTHandler / APIKeyManager / Legacy Token → Protected Endpoint

5. **Session Flow**:
   Browser Context → Encrypted Cookie Storage (Fernet) → Periodic Flush → SQLite/PostgreSQL metadata

### File Inventory (143 files, ~50,000+ lines of code)

| Module | Files | Key Files |
|--------|-------|-----------|
| Core Engine | 12 | browser.py (4344 lines), config.py, session.py |
| Stealth | 6 | cdp_stealth.py (1203 lines), stealth_god.py (969 lines), stealth.py, adaptive_stealth.py |
| Security | 6 | cloudflare_bypass.py (1031 lines), captcha_preempt.py (1950 lines), captcha_solver.py, evasion_engine.py, human_mimicry.py |
| Tools | 27 | multi_tab_manager.py, proxy_rotation.py, visual_testing.py, token_optimizer.py, ai_content.py (3242 lines) |
| Agent Swarm | 6 | orchestrator.py, agents/, search/, router/ |
| Auth | 4 | jwt_handler.py, api_key_manager.py, user_manager.py, middleware.py |
| Infra | 4 | database.py, logging.py, models.py, redis_client.py |
| Connectors | 7 | mcp_passthrough.py, mcp_sse_server.py, mcp_server.py, openai_connector.py |
| Browser Engine (TS) | 7 | index.ts (2520 lines), stealth.ts, tab-manager.ts |
| Setup | 1 | wizard.py (418 lines) |
| Tests | 4 | test_all.py, test_connectors.py, test_extended.py |

## README Claim → Code Verification Checklist

| # | README Claim | Code Location | Status |
|---|-------------|---------------|--------|
| 1 | 209+ production tools | connectors/_tool_registry.py (1017 lines), src/tools/ (27 files) | ✅ CONFIRMED |
| 2 | 5-layer stealth defense | cdp_stealth.py, stealth_god.py, adaptive_stealth.py, tls_spoof.py, evasion_engine.py | ✅ CONFIRMED |
| 3 | Multi-tab handling | src/tools/multi_tab_manager.py (919 lines) | ✅ CONFIRMED |
| 4 | AI Visual Testing | src/tools/visual_testing.py (779 lines) | ✅ CONFIRMED |
| 5 | Token Optimizer (90%+ reduction) | src/tools/token_optimizer.py (622 lines) | ✅ CONFIRMED |
| 6 | Smart Navigator | src/core/smart_navigator.py (509 lines) | ✅ CONFIRMED |
| 7 | CAPTCHA Solver | src/security/captcha_solver.py (964 lines), captcha_preempt.py (1950 lines) | ✅ CONFIRMED |
| 8 | Agent Swarm | src/agent_swarm/ (6 files), src/tools/multi_agent.py (1248 lines) | ✅ CONFIRMED |
| 9 | Session Manager | src/core/session.py (259 lines), session_recording.py (1421 lines) | ✅ CONFIRMED |
| 10 | Proxy Rotation | src/tools/proxy_rotation.py (1118 lines), auto_proxy.py (927 lines) | ✅ CONFIRMED |
| 11 | Cloudflare Bypass v1/v2/v3 | src/security/cloudflare_bypass.py (1031 lines) | ✅ CONFIRMED |
| 12 | JWT Auth | src/auth/jwt_handler.py (282 lines), api_key_manager.py (287 lines) | ✅ CONFIRMED |
| 13 | Docker Ready | Dockerfile, docker-compose.yml | ✅ CONFIRMED |
| 14 | MCP Support | connectors/mcp_passthrough.py (1078 lines), mcp_sse_server.py (730 lines) | ✅ CONFIRMED |
| 15 | CDP Runtime Injection | src/core/cdp_stealth.py (1203 lines) | ✅ CONFIRMED |
| 16 | TLS Fingerprint Spoofing | src/core/tls_spoof.py (391 lines), tls_proxy.py (676 lines) | ✅ CONFIRMED |
| 17 | Firefox Fallback | src/core/firefox_engine.py (959 lines) | ✅ CONFIRMED |
| 18 | Human Input Emulation | src/security/human_mimicry.py (324 lines) | ✅ CONFIRMED |
| 19 | Setup Wizard | src/setup/wizard.py (418 lines) | ✅ CONFIRMED |
| 20 | Browser Engine (TypeScript) | browser-engine/index.ts (2520 lines), stealth.ts (498 lines) | ✅ CONFIRMED |
| 21 | Claude Web Direct Connect | connectors/mcp_sse_server.py + tunnel_manager reference | ✅ CONFIRMED |
| 22 | Persistent Browser Profiles | src/core/persistent_browser.py (1886 lines) | ✅ CONFIRMED |

### Browser Profile Consistency Check

| Profile Element | Source | Consistency |
|----------------|--------|-------------|
| User-Agent | browser.py BROWSER_PROFILES | ✅ 12 profiles with matching UA/platform/viewport |
| Client Hints (sec-ch-ua) | browser.py BROWSER_PROFILES | ✅ Matches UA Chrome version |
| navigator.platform | browser.py BROWSER_PROFILES | ✅ Matches UA OS |
| Timezone | browser.py BROWSER_PROFILES | ✅ Matched to locale region |
| Locale | browser.py BROWSER_PROFILES | ✅ Used for Accept-Language |
| Viewport | browser.py BROWSER_PROFILES | ✅ Consistent with screen size |
| WebGL vendor/renderer | cdp_stealth.py default params | ⚠️ Hardcoded to "Intel Inc." / "Intel Iris OpenGL Engine" |

### Potential Issues Identified (Pre-Phase 2)

1. **WebGL vendor/renderer mismatch**: All 12 profiles use different platforms (Windows, macOS, Linux) but CDP stealth defaults to Intel GPU. macOS profiles should use Apple GPU, some Windows/Linux could use AMD/NVIDIA.

2. **sec-ch-ua-mobile**: Always set to "?0" in _build_headers(), even for mobile device presets.

3. **Setup wizard env file path**: wizard.py writes to `Path(__file__).parent.parent.parent / ".env"` which resolves correctly, BUT if the app is installed as a package, this may not write to the expected location.

4. **database.enabled default**: config.py sets `database.enabled: False` by default, but main.py auto-creates SQLite database. Inconsistent defaults.

5. **Browser profile screen vs viewport**: Some profiles (e.g. macOS 2560x1600) have screen_size matching viewport, but real Retina displays have different logical vs physical resolutions.
