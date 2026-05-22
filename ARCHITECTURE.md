# Agent-OS — Architecture Reference

> **Purpose:** Internal reference for AI assistant (x). No need to re-read the full codebase every time.
> Last updated: 2026-04-10

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent-OS v3.0                          │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Connectors  │  Agent Server│  Debug UI    │  Auth Layer    │
│  (MCP/OpenAI │  (WS + REST) │  (Dashboard) │  (JWT/API Key) │
│   /OpenClaw) │              │              │                │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                    Core Engine Layer                         │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │ Browser  │ │  Stealth  │ │  Session  │ │  Persistent │  │
│  │ (Playwright│ │ (Anti-   │ │  Manager  │ │  Browser    │  │
│  │ Chromium)│ │  Detection)│ │           │ │  Manager    │  │
│  └──────────┘ └───────────┘ └───────────┘ └─────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      Tools Layer                             │
│  smart_finder │ workflow │ network_capture │ page_analyzer  │
│  smart_wait   │ auto_heal│ auto_retry      │ scanner        │
│  session_recording│ form_filler │ proxy_rotation │ multi_agent│
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│  Database (PostgreSQL/SQLAlchemy) │ Redis │ Logging │ Config │
└─────────────────────────────────────────────────────────────┘
```

**Stack:** Python 3.10+ / Playwright (Chromium) / aiohttp + websockets / SQLAlchemy + Redis

---

## 📁 Directory Structure

```
Agent-OS/
├── main.py                    # 🚀 Entry point — AgentOS class, CLI args, startup/shutdown
├── qwen_bridge.py             # Qwen AI bridge connector
├── human_demo.py              # Demo script
├── stress_test.py             # Load testing
├── requirements.txt           # Dependencies
├── docker-compose.yml         # Docker deployment
├── Dockerfile                 # Container build
├── nginx.conf                 # Nginx reverse proxy config
├── setup.sh                   # Installation script
├── alembic.ini                # DB migration config
├── .env.example               # Environment variable template
│
├── src/
│   ├── core/                  # 🧠 Core engine (the heart)
│   │   ├── config.py          #   YAML config management, token generation
│   │   ├── browser.py         #   AgentBrowser — Playwright wrapper, 74+ commands
│   │   ├── session.py         #   SessionManager — lifecycle, auto-wipe, sandboxing
│   │   ├── stealth.py         #   Anti-detection JS, bot-blocking URLs, fake responses
│   │   └── persistent_browser.py  # Long-running Chromium with per-user contexts
│   │
│   ├── agents/
│   │   └── server.py          # 🌐 AgentServer — WebSocket (8000) + REST (8001)
│   │                             Command router, auth, rate limiting, 130+ handlers
│   │
│   ├── auth/                  # 🔐 Authentication system
│   │   ├── jwt_handler.py     #   JWT creation, verification, refresh tokens
│   │   ├── api_key_manager.py #   API key CRUD (prefix: aos_)
│   │   ├── user_manager.py    #   User registration, login, password hashing
│   │   └── middleware.py      #   Auth middleware chain for HTTP requests
│   │
│   ├── security/              # 🛡️ Security tools
│   │   ├── auth_handler.py    #   Auto-login, credential vault (AES-256)
│   │   └── captcha_bypass.py  #   CAPTCHA detection & bypass strategies
│   │
│   ├── tools/                 # 🔧 Feature tools (all lazy-loaded from server.py)
│   │   ├── smart_finder.py    #   Find elements by visible text (no CSS needed)
│   │   ├── smart_wait.py      #   Intelligent waits (network idle, DOM stable, etc.)
│   │   ├── auto_heal.py       #   Self-healing selectors when elements change
│   │   ├── auto_retry.py      #   Retry with backoff, circuit breakers
│   │   ├── workflow.py        #   Multi-step workflows with variables/retries
│   │   ├── network_capture.py #   HTTP request capture, API discovery, HAR export
│   │   ├── page_analyzer.py   #   Page summary, table extraction, SEO, accessibility
│   │   ├── scanner.py         #   XSS, SQLi, sensitive data scanners
│   │   ├── form_filler.py     #   Smart form filling (job applications, etc.)
│   │   ├── session_recording.py # Record/replay browser sessions
│   │   ├── multi_agent.py     #   AgentHub — multi-agent coordination, locks, tasks
│   │   ├── proxy_rotation.py  #   Proxy pool management, rotation strategies
│   │   └── transcriber.py     #   Video transcription (Whisper integration)
│   │
│   ├── debug/
│   │   └── server.py          # 📊 Debug UI server (port 8002)
│   │
│   ├── validation/
│   │   └── schemas.py         #   Input validation (Pydantic)
│   │
│   └── infra/                 # 🏗️ Infrastructure
│       ├── database.py        #   SQLAlchemy async engine, session factory
│       ├── redis_client.py    #   Redis wrapper with fallback
│       ├── models.py          #   DB models (users, api_keys, usage, audit)
│       └── logging.py         #   Structured logging (structlog)
│
├── connectors/                # 🔌 External integrations
│   ├── mcp_server.py          #   MCP protocol (Claude Desktop / Codex)
│   ├── openai_connector.py    #   OpenAI function calling
│   └── openclaw_connector.py  #   OpenClaw integration
│
├── tools/                     # (Top-level tools, separate from src/tools)
│
├── tests/                     # 🧪 Tests
│   ├── test_all.py
│   ├── test_connectors.py
│   └── test_extended.py
│
├── docs/                      # 📖 Documentation
└── proof/                     # Proof/evidence files
```

---

## 🔑 Key Files — What They Do

### Entry Point
| File | Purpose | Key Class |
|------|---------|-----------|
| `main.py` | App bootstrap, CLI parsing, startup/shutdown sequence | `AgentOS` |

### Core Engine (`src/core/`)
| File | Purpose | Key Class |
|------|---------|-----------|
| `config.py` | YAML config with dotted-key access (`browser.max_ram_mb`), token generation | `Config` |
| `browser.py` | **Main Playwright wrapper** — stealth, cookies, device emulation, 40+ browser methods | `AgentBrowser` |
| `session.py` | Session lifecycle, auto-cleanup every 30s, max 3 concurrent | `SessionManager`, `Session` |
| `stealth.py` | Anti-detection JS injection, bot-blocking URL patterns, fake responses | Constants/Functions |
| `persistent_browser.py` | Long-running Chromium, per-user isolated contexts, health monitoring | `PersistentBrowserManager` |

### Server (`src/agents/`)
| File | Purpose | Key Class |
|------|---------|-----------|
| `server.py` | **Command router** — WebSocket + REST, auth, rate limiting, 130+ command handlers | `AgentServer` |

### Auth (`src/auth/`)
| File | Purpose |
|------|---------|
| `jwt_handler.py` | JWT create/verify/refresh (HS256, configurable expiry) |
| `api_key_manager.py` | API key CRUD, prefix-based (`aos_`), hash storage |
| `user_manager.py` | User create/authenticate, bcrypt passwords |
| `middleware.py` | HTTP auth middleware chain |

### Tools (`src/tools/`)
| File | Purpose | Commands |
|------|---------|----------|
| `smart_finder.py` | Find by visible text, no CSS selector needed | `smart-find`, `smart-click`, `smart-fill` |
| `smart_wait.py` | Network idle, DOM stable, element ready, JS condition | `smart-wait`, `smart-wait-*` |
| `auto_heal.py` | Self-healing broken selectors via fingerprinting | `heal-click`, `heal-fill`, `heal-selector` |
| `auto_retry.py` | Exponential backoff, circuit breakers | `retry-execute`, `retry-navigate` |
| `workflow.py` | Multi-step with variables, save/load templates | `workflow`, `workflow-save`, `workflow-template` |
| `network_capture.py` | Intercept HTTP, discover APIs, HAR export | `network-start/stop/get/apis/export` |
| `page_analyzer.py` | Summary, tables, emails, phones, SEO, accessibility | `page-summary`, `page-tables`, `page-seo` |
| `scanner.py` | XSS, SQL injection, sensitive data detection | `scan-xss`, `scan-sqli`, `scan-sensitive` |
| `form_filler.py` | Smart form filling for job apps, etc. | `fill-job` |
| `session_recording.py` | Record, replay, analyze browser sessions | `record-*`, `replay-*`, `analyze` |
| `multi_agent.py` | AgentHub — locks, tasks, shared memory, handoff | `hub-*` (20+ commands) |
| `proxy_rotation.py` | Proxy pool, rotation strategies, health checks | `proxy-*` (15+ commands) |
| `transcriber.py` | Video/audio transcription via Whisper | `transcribe` |

---

## 🔄 Request Flow

```
Agent (AI) ──► WebSocket/HTTP ──► Auth Check ──► Rate Limit ──► Validate
                                                                      │
                                                                      ▼
                                                              Command Router
                                                                      │
                                        ┌───────────┬────────────────┤
                                        ▼           ▼                ▼
                                   Browser     Tools            Infra
                                   (navigate,  (workflow,      (DB/Redis)
                                    click,     scanner,
                                    screenshot etc.)
                                    etc.)
```

### Authentication Flow
1. **WebSocket:** First message must contain `token` → tries API key (`aos_*`) → JWT → legacy token
2. **HTTP:** Middleware checks `Authorization` header → API key → JWT → legacy token in body
3. **Legacy token fallback:** Controlled by `security.allow_legacy_token_auth` (default: true)

### Command Processing
1. `AgentServer._process_command()` → gets/creates session
2. Routes to `_execute_command()` → dispatches to handler map (130+ entries)
3. Most tools are **lazy-loaded** on first use
4. Result includes `session_id` for tracking

---

## ⚙️ Configuration

**Config file:** `~/.agent-os/config.yaml` (auto-created with defaults)
**Env vars:** `.env` file (see `.env.example`)

### Key Config Sections
```yaml
server:          # Host, ports (WS:8000, HTTP:8001, Debug:8002), CORS, rate limits
browser:         # Headless, viewport, user agent, proxy, device, timeout
session:         # Timeout (15min), auto-wipe, max concurrent (3)
security:        # captcha_bypass, human_mimicry, JWT, API key auth
database:        # PostgreSQL DSN, pool size (disabled by default)
redis:           # Redis URL (disabled by default, has fallback)
jwt:             # Secret key, HS256, token expiry
persistent:      # Long-running Chromium settings
scanner:         # Rate limits for security scans
transcription:   # Whisper model selection
logging:         # Level, JSON format, service name
```

### Config Access Pattern
```python
config.get("browser.max_ram_mb")     # Dotted key
config.set("server.ws_port", 9000)   # Set value
config.set("x.y", val, save=True)    # Set + persist to YAML
```

---

## 🛡️ Stealth System

**File:** `src/core/stealth.py` (shared by browser.py + persistent_browser.py)

### What it does:
- **Anti-detection JS** injected on every page via `context.add_init_script()`:
  - Removes `navigator.webdriver`
  - Spoofs plugins, languages, platform, hardware (8 cores, 8GB RAM)
  - Injects `chrome.runtime` object (required for real Chrome detection)
  - Overrides WebGL renderer/vendor strings
  - Masks iframe contentWindow automation flags
  - Randomizes canvas/WebGL/audio fingerprints

- **Bot Detection URL Blocking** — network-level blocks for:
  - reCAPTCHA, hCaptcha, Cloudflare Turnstile
  - PerimeterX, DataDome, Imperva, Akamai, Kasada
  - Faked success responses for reCAPTCHA (score: 0.9) and hCaptcha (pass)

- **Human Mimicry** (`src/security/human_mimicry.py`):
  - Bezier curve mouse movements
  - Realistic typing delays (WPM-based)
  - Natural scroll behavior
  - Typo simulation

---

## 🔌 Connectors

| Connector | File | Protocol | Use Case |
|-----------|------|----------|----------|
| MCP Server | `connectors/mcp_server.py` | MCP (Model Context Protocol) | Claude Desktop, Codex |
| OpenAI | `connectors/openai_connector.py` | OpenAI function calling | GPT-4, GPT-4o |
| OpenClaw | `connectors/openclaw_connector.py` | OpenClaw | OpenClaw agents |

All connectors expose the same tool set — they're just different transport layers.

---

## 🚀 Deployment

### Docker (Recommended)
```bash
docker run -d -p 8000:8000 -p 8001:8001 --name agent-os factspark23-hash/agent-os
```

### Local Development
```bash
pip install -r requirements.txt
playwright install chromium
python main.py
python main.py --headed          # Show browser
python main.py --persistent      # Production mode
python main.py --database "postgresql+asyncpg://..." --redis "redis://..."
```

### CLI Arguments
```
--headed          Show browser window
--port PORT       WS port (HTTP=port+1, Debug=port+2)
--max-ram MB      RAM cap
--proxy URL       Proxy
--device NAME     Mobile emulation preset
--persistent      Long-running Chromium mode
--debug           Enable debug UI (disabled by default)
--database DSN    PostgreSQL connection
--redis URL       Redis connection
--agent-token     Custom auth token
--log-level       DEBUG/INFO/WARNING/ERROR
--json-logs       Structured JSON logging (default: on)
--create-tables   Init DB tables on startup
```

### Ports
| Port | Service |
|------|---------|
| 8000 | WebSocket (agent connections) |
| 8001 | HTTP REST API |
| 8002 | Debug UI dashboard |

---

## 📊 Device Presets

| Preset | Type | Viewport |
|--------|------|----------|
| `iphone_se` | Mobile | 375×667 |
| `iphone_14` | Mobile | 390×844 |
| `iphone_14_pro_max` | Mobile | 430×932 |
| `galaxy_s23` | Mobile | 360×780 |
| `pixel_8` | Mobile | 412×915 |
| `ipad` | Tablet | 768×1024 |
| `ipad_pro` | Tablet | 1024×1366 |
| `galaxy_tab_s9` | Tablet | 800×1280 |
| `desktop_1080` | Desktop | 1920×1080 |
| `desktop_1440` | Desktop | 2560×1440 |
| `desktop_4k` | Desktop | 3840×2160 |

---

## 🧪 Testing

```bash
pytest tests/test_all.py -v
pytest tests/test_connectors.py -v
pytest tests/test_extended.py -v
```

---

## 🔍 How to Approach Feature/Bug Work

### Adding a new feature:
1. **New tool** → Create in `src/tools/`, add command handler in `src/agents/server.py` (`_execute_command` map + `_cmd_*` method), lazy-init getter
2. **New connector** → Create in `connectors/`, follow existing pattern
3. **New config option** → Add to `DEFAULT_CONFIG` in `src/core/config.py`
4. **New browser method** → Add to `AgentBrowser` in `src/core/browser.py`

### Debugging:
1. Check `src/agents/server.py` → command routing
2. Check `src/core/browser.py` → browser operations
3. Check `src/core/stealth.py` → if anti-detection related
4. Debug UI at `http://localhost:8002` for live inspection

### Common patterns:
- **Lazy loading:** Tools are `None` until first use, then `import` + instantiate
- **All commands return:** `{"status": "success/error", ...}`
- **Sessions:** Auto-created per token, 15min timeout, auto-wipe
- **Error handling:** `_safe_execute()` wraps browser ops with crash recovery

---

## 📝 Notes

- Version: 3.0.0 (Production Edition)
- No GPU required — runs on CPU with Playwright Chromium
- Zero telemetry — everything runs locally
- Config at `~/.agent-os/config.yaml`
- Cookies encrypted with Fernet (AES-256) at `~/.agent-os/cookies/`
- Sessions stored at `~/.agent-os/sessions/`
