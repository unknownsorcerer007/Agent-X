# Browser Engine v2.1 — Production Anti-Detection Browser

Production-ready TypeScript browser engine with anti-detection, smart mode selection, session persistence, and social media automation. Built on Playwright with CDP support.

## Features

| Feature | Description | Endpoints |
|---------|-------------|-----------|
| **CDP Connection** | Connect to user's Chrome via Chrome DevTools Protocol | 6 |
| **Smart Browser Modes** | Full (CDP+Chrome), Light (headless), Ghost (API-only) | 5 |
| **Dual-Layer State Persistence** | Cookies + localStorage + IndexedDB with Fernet encryption | 6 |
| **Handoff Controller** | Pause automation for 2FA/CAPTCHA, SSE screenshot streaming | 4 |
| **Auto Tab Management** | Memory tracking, idle timeouts, force cleanup | 5 |
| **20-Point Stealth** | Proxy patterns, timezone override, fingerprint spoofing | — |
| **Platform Adapters** | Instagram, Twitter, LinkedIn, Facebook with typed returns | — |
| **Rate Limiting** | 100 requests/IP/minute with 429 responses | — |
| **Graceful Shutdown** | State auto-save on SIGINT/SIGTERM | — |

## Quick Start

```bash
# One-command install
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS/browser-engine
chmod +x install.sh
./install.sh

# Start the server
./start.sh

# Verify
curl http://localhost:3003/api/health
```

## API Reference

### Health & Info
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health, memory, sessions, uptime |

### CDP Connection
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cdp/check` | Check if CDP port is available |
| GET | `/api/cdp/discover` | Auto-discover CDP port |
| GET | `/api/cdp/version` | Get Chrome version info |
| GET | `/api/cdp/targets` | List CDP targets |
| POST | `/api/cdp/connect` | Connect to Chrome via CDP |
| GET | `/api/cdp/launch-instruction` | Get Chrome launch command |

### Smart Browser Modes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/modes/decide` | Decide browser mode for a task |
| POST | `/api/modes/detect-task` | Detect task category from description |
| POST | `/api/smart/launch` | Launch a smart session |
| POST | `/api/smart/close` | Close a smart session (auto-saves state) |
| GET | `/api/smart/mode` | Get session mode info |

### Browser Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/browser/launch` | Launch legacy browser session |
| POST | `/api/browser/close` | Close browser session |
| POST | `/api/browser/navigate` | Navigate to URL |
| POST | `/api/browser/snapshot` | Get accessibility tree |
| POST | `/api/browser/screenshot` | Take screenshot (JPEG base64) |
| POST | `/api/browser/evaluate` | Execute JavaScript |
| POST | `/api/browser/click` | Click element by ref |
| POST | `/api/browser/fill` | Fill input by ref |
| POST | `/api/browser/upload-file` | Upload file via CDP |
| POST | `/api/browser/wait` | Wait for element/URL/text |
| POST | `/api/browser/press` | Press keyboard key |

### State Persistence
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/state/save` | Save browser state (cookies, localStorage, IndexedDB) |
| POST | `/api/state/load` | Load saved state into session |
| GET | `/api/state/list` | List all saved states |
| GET | `/api/state/info` | Get state metadata |
| GET | `/api/state/has-auth` | Check if platform has auth cookies |
| DELETE | `/api/state/delete` | Delete saved state |

### Handoff Controller (2FA/CAPTCHA)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/handover/start` | Pause automation, start SSE screenshot stream |
| GET | `/api/handover/:sessionId/stream` | SSE screenshot stream (every 500ms) |
| POST | `/api/handover/interact` | Send click/type during handover |
| POST | `/api/handover/end` | Resume automation, auto-save state |

### Tab Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tabs/stats` | Memory stats, pressure level, tab counts |
| GET | `/api/tabs/list` | List all active tabs |
| GET | `/api/tabs/can-launch` | Check if new session can be launched |
| POST | `/api/tabs/force-cleanup` | Force-close idle tabs |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3003` | Server port |
| `BROWSER_STATES_DIR` | `~/.agent-os/browser-states` | State persistence directory |
| `TWITTER_BEARER_TOKEN` | — | Twitter API bearer token |
| `IG_APP_ID` | `936619743392459` | Instagram web app ID |
| `IG_CREATE_POST_DOC_ID` | `6511191288958346` | Instagram GraphQL doc ID |

## Architecture

```
┌─────────────────────────────────────────────┐
│            Browser Engine v2.1              │
│              (HTTP + WS :3003)              │
├─────────────────────────────────────────────┤
│                                             │
│  ┌───────────┐  ┌───────────┐  ┌─────────┐ │
│  │   FULL    │  │   LIGHT   │  │  GHOST  │ │
│  │ CDP+Chrome│  │  Headless │  │ API-only│ │
│  │ 300-500MB │  │  50-80MB  │  │   0MB   │ │
│  └─────┬─────┘  └─────┬─────┘  └────┬────┘ │
│        │              │              │       │
│  ┌─────▼──────────────▼──────────────▼────┐ │
│  │         Mode Decision Engine           │ │
│  │  Task → Category → Mode + Auth Check  │ │
│  └────────────────┬──────────────────────┘ │
│                   │                         │
│  ┌────────────────▼──────────────────────┐ │
│  │         Shared Services               │ │
│  │  • State Persistence (dual-layer)     │ │
│  │  • Handoff Controller (SSE)           │ │
│  │  • Tab Manager (memory + idle)        │ │
│  │  • Stealth Engine (20-point)          │ │
│  │  • Fingerprint Generator              │ │
│  │  • Rate Limiter (100/min)             │ │
│  └───────────────────────────────────────┘ │
│                   │                         │
│  ┌────────────────▼──────────────────────┐ │
│  │       Platform Adapters               │ │
│  │  Instagram │ Twitter │ LinkedIn │ FB  │ │
│  └───────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

## Browser Mode Selection

| Task | Platform | URL Pattern | Mode |
|------|----------|-------------|------|
| Login/Signup | Any | `/login`, `/auth` | **FULL** |
| Post/Upload | Instagram, Twitter, etc. | Social domains | **FULL** |
| Scrape/Research | Any | General sites | **LIGHT** |
| API Call/Webhook | Any | — | **GHOST** |

## Stealth Features (20-Point)

1. `navigator.webdriver` → undefined
2. `window.chrome` → true with runtime
3. `navigator.plugins` → 3 realistic plugins (Proxy)
4. `navigator.mimeTypes` → matched mimetypes (Proxy)
5. `navigator.vendor` → "Google Inc."
6. `navigator.platform` → fingerprint-based (Win32/MacIntel)
7. `navigator.languages` → multi-language array
8. `navigator.hardwareConcurrency` → fingerprint-based (4-8)
9. `navigator.deviceMemory` → fingerprint-based (4-8)
10. `screen` dimensions → fingerprint-based
11. `Intl.DateTimeFormat` → timezone override matching fingerprint
12. User-Agent → Chrome 131/132 with matching platform
13. `toString()` patching → native-looking for overridden functions
14. iframe `contentWindow` override
15. CDP artifact cleanup
16. `Permissions.query` override
17. `WebGL` vendor/renderer spoofing
18. Error stack trace cleaning
19. `navigator.userAgent` override (dual-layer)
20. Deterministic fingerprints from seed (username-based)

## Test Results

```
29/29 tests PASSED, 0 failures

Phase 1: API Tests — 12/12 ✅
Phase 2: Ghost Session — 3/3 ✅
Phase 3: Light Session — 9/9 ✅ (navigate, screenshot, evaluate, state, handover)
Phase 4: Stealth — 4/4 ✅ (webdriver hidden, chrome present, vendor correct, platform spoofed)
```

## License

MIT
