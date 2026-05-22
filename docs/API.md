# Agent-OS API Documentation

## Quick Start

```bash
# Install
pip install -r requirements.txt
playwright install chromium

# Run
python main.py --agent-token "my-agent"

# Connect
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -d '{"token":"my-agent","command":"navigate","url":"https://github.com"}'
```

---

## Connection Methods

### WebSocket (Real-time)
```javascript
const ws = new WebSocket('ws://localhost:8000');
ws.onopen = () => {
  ws.send(JSON.stringify({
    token: "my-agent",
    command: "navigate",
    url: "https://example.com"
  }));
};
ws.onmessage = (msg) => console.log(JSON.parse(msg.data));
```

### HTTP REST (Simple)
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -d '{"token":"my-agent","command":"navigate","url":"https://example.com"}'
```

### Python
```python
import requests
r = requests.post("http://localhost:8001/command", json={
    "token": "my-agent",
    "command": "navigate",
    "url": "https://example.com"
})
print(r.json())
```

---

## CLI Arguments

```bash
python3 main.py [options]

Options:
  --headed              Show browser window (non-headless)
  --agent-token TOKEN   Set custom agent authentication token
  --port PORT           WebSocket server port (HTTP port = port + 1)
  --max-ram MB          Maximum RAM usage in MB (default: 500)
  --config PATH         Custom config file path
  --proxy URL           Proxy URL (http://user:pass@host:port or socks5://host:port)
  --device PRESET       Device emulation preset (iphone_14, galaxy_s23, ipad, etc.)
```

---

## HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/command` | POST | Execute any tool command |
| `/status` | GET | Server health check — uptime, active sessions, browser state |
| `/commands` | GET | List all available commands with parameters |
| `/debug` | GET | Debug info — sessions, tabs, blocked requests |
| `/screenshot` | GET | Quick screenshot (returns base64 text) |

---

## Commands Reference

All commands require `token` and `command` fields. Parameters vary by command.

### Navigation

#### navigate
Navigate to a URL with human-like timing delays.

```json
{"token":"my-agent","command":"navigate","url":"https://github.com/login"}
```
**Optional:** `page_id` (default: "main"), `wait_until` (default: "domcontentloaded")
**Response:** `{"status":"success","url":"...","title":"...","status_code":200,"blocked_requests":5}`

#### back
Go back in browser history.
```json
{"token":"my-agent","command":"back"}
```

#### forward
Go forward in browser history.
```json
{"token":"my-agent","command":"forward"}
```

#### reload
Reload the current page.
```json
{"token":"my-agent","command":"reload"}
```

---

### Interaction

#### click
Click an element using CSS selector. Includes Bezier mouse movement simulation.
```json
{"token":"my-agent","command":"click","selector":"button[type='submit']"}
```

#### double-click
Double-click an element (e.g., to edit a cell, open a file).
```json
{"token":"my-agent","command":"double-click","selector":"td.editable"}
```

#### right-click
Right-click an element to open context menu.
```json
{"token":"my-agent","command":"right-click","selector":"#item"}
```

#### context-action
Right-click and select a context menu option by text. Supports keyboard shortcuts as fallback (copy, paste, cut, save, etc.).
```json
{"token":"my-agent","command":"context-action","selector":"#item","action_text":"Copy"}
```

#### type
Type text into the currently focused element with human-like keystroke delays.
```json
{"token":"my-agent","command":"type","text":"Hello World"}
```

#### press
Press a keyboard key.
```json
{"token":"my-agent","command":"press","key":"Enter"}
```
**Supported keys:** Enter, Tab, Escape, Backspace, Delete, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Home, End, PageUp, PageDown, F1-F12, Control+a, etc.

#### hover
Hover the mouse over an element.
```json
{"token":"my-agent","command":"hover","selector":".dropdown-trigger"}
```

#### fill-form
Fill multiple form fields with human-like typing. Keys are CSS selectors, values are text.
```json
{"token":"my-agent","command":"fill-form","fields":{"#email":"user@example.com","input[name='password']":"secret123"}}
```
**Response:** `{"status":"success","filled":["#email","input[name='password']"],"total":2}`

#### clear-input
Clear an input field (select all + backspace).
```json
{"token":"my-agent","command":"clear-input","selector":"#search"}
```

#### checkbox
Set a checkbox to checked or unchecked.
```json
{"token":"my-agent","command":"checkbox","selector":"#agree-terms","checked":true}
```

#### select
Select an option from a dropdown.
```json
{"token":"my-agent","command":"select","selector":"#country","value":"US"}
```

#### upload
Upload a file to a file input element.
```json
{"token":"my-agent","command":"upload","selector":"input[type='file']","file_path":"/path/to/file.pdf"}
```

#### wait
Wait for an element to appear on the page.
```json
{"token":"my-agent","command":"wait","selector":".results","timeout":10000}
```

#### drag-drop
Drag one element and drop it on another.
```json
{"token":"my-agent","command":"drag-drop","source":"#item","target":"#dropzone"}
```

#### drag-offset
Drag an element by a pixel offset.
```json
{"token":"my-agent","command":"drag-offset","selector":"#slider","x":200,"y":0}
```

---

### Smart Element Finder

Find elements by visible text, label, placeholder, aria-label, title, alt text, or description. No CSS selector needed.

#### smart-find
Find an element by natural description. Supports fuzzy matching with confidence scoring.
```json
{"token":"my-agent","command":"smart-find","description":"Sign In","tag":"button","timeout":5000}
```
**Response:** `{"status":"success","found":true,"selector":"button.primary","tag":"button","text":"Sign In","match_type":"button_text","confidence":0.85,"total_matches":2}`

**Search strategies (in priority order):** exact_text → aria_label → placeholder → title_attr → alt_text → link_text → button_text → label_text → fuzzy_text → partial_text → text_nearby

#### smart-find-all
Find ALL matching elements, ranked by relevance.
```json
{"token":"my-agent","command":"smart-find-all","description":"Submit"}
```

#### smart-click
Click an element by its visible text.
```json
{"token":"my-agent","command":"smart-click","text":"Sign In"}
```

#### smart-fill
Find an input by its label/placeholder text and fill it.
```json
{"token":"my-agent","command":"smart-fill","label":"Email address","value":"user@example.com"}
```

---

### Content Extraction

#### get-content
Get current page HTML and extracted text.
```json
{"token":"my-agent","command":"get-content"}
```
**Response:** `{"status":"success","url":"...","title":"...","html":"...","text":"..."}`

#### get-dom
Get structured DOM snapshot for agent analysis (tag, id, class, href, text).
```json
{"token":"my-agent","command":"get-dom"}
```

#### get-links
Get all links on the current page.
```json
{"token":"my-agent","command":"get-links"}
```
**Response:** `{"status":"success","links":["https://..."],"count":42}`

#### get-images
Get all images with src, alt, width, height.
```json
{"token":"my-agent","command":"get-images"}
```

#### get-text
Get text content of a specific element.
```json
{"token":"my-agent","command":"get-text","selector":"h1"}
```

#### get-attr
Get an attribute value from an element.
```json
{"token":"my-agent","command":"get-attr","selector":"a.link","attribute":"href"}
```

#### screenshot
Take a screenshot. Returns base64 PNG.
```json
{"token":"my-agent","command":"screenshot","full_page":true}
```

#### evaluate-js
Execute JavaScript in the page context and return the result.
```json
{"token":"my-agent","command":"evaluate-js","script":"document.querySelectorAll('a').length"}
```

#### scroll
Scroll the page with human-like behavior (multi-step with micro-variations).
```json
{"token":"my-agent","command":"scroll","direction":"down","amount":500}
```

#### viewport
Change the browser viewport size.
```json
{"token":"my-agent","command":"viewport","width":375,"height":812}
```

---

### Browser Control

#### tabs
Manage browser tabs.
```json
{"token":"my-agent","command":"tabs","action":"list"}
{"token":"my-agent","command":"tabs","action":"new","tab_id":"research"}
{"token":"my-agent","command":"tabs","action":"switch","tab_id":"research"}
{"token":"my-agent","command":"tabs","action":"close","tab_id":"research"}
```

#### console-logs
Get captured browser console logs. Each entry has type (log/warn/error/info/debug/pageerror), text, location, and timestamp.
```json
{"token":"my-agent","command":"console-logs","page_id":"main","clear":false}
```
**Response:** `{"status":"success","logs":[{"type":"error","text":"...","location":{"url":"...","line":5}}],"count":3}`

#### get-cookies
Get all cookies for the current context.
```json
{"token":"my-agent","command":"get-cookies"}
```

#### set-cookie
Set a cookie with full control. Domain is auto-inferred from current page URL if not provided.
```json
{"token":"my-agent","command":"set-cookie","name":"session","value":"abc123","domain":"example.com","path":"/","secure":true,"http_only":true,"same_site":"Lax"}
```

#### add-extension
Load a Chrome extension (requires `--headed` mode and browser restart).
```json
{"token":"my-agent","command":"add-extension","extension_path":"/path/to/extension"}
```

---

### Page Analysis

#### page-summary
Full page analysis including: title, meta tags, headings hierarchy, main content paragraphs, navigation links, categorized links (internal/external), forms with fields, images, tables, Open Graph/social metadata, performance timing, detected technologies (jQuery, React, Vue, Angular, Next.js, WordPress, Bootstrap, Tailwind, etc.), and readability metrics (Flesch score).
```json
{"token":"my-agent","command":"page-summary"}
```

#### page-tables
Extract all HTML tables as structured data (headers + rows).
```json
{"token":"my-agent","command":"page-tables"}
```

#### page-structured
Extract JSON-LD and Microdata structured data from the page.
```json
{"token":"my-agent","command":"page-structured"}
```

#### page-emails
Find all email addresses on the page.
```json
{"token":"my-agent","command":"page-emails"}
```

#### page-phones
Find all phone numbers on the page.
```json
{"token":"my-agent","command":"page-phones"}
```

#### page-accessibility
Basic accessibility audit. Checks: images without alt, empty alt on large images, inputs without labels, missing lang attribute, empty links, heading hierarchy skips, missing H1.
```json
{"token":"my-agent","command":"page-accessibility"}
```

#### page-seo
SEO audit with score (0-100). Checks: title tag (length), meta description, H1 tags, images without alt, canonical URL, Open Graph tags, viewport meta, JSON-LD structured data.
```json
{"token":"my-agent","command":"page-seo"}
```

---

### Multi-Step Workflows

#### workflow
Execute a multi-step workflow. Steps are an array of command objects.
```json
{
  "token":"my-agent",
  "command":"workflow",
  "steps":[
    {"command":"navigate","url":"https://google.com"},
    {"command":"fill-form","fields":{"input[name='q']":"{{query}}"}},
    {"command":"press","key":"Enter"},
    {"command":"wait","selector":"#search"},
    {"command":"get-content"}
  ],
  "variables":{"query":"Agent-OS"},
  "on_error":"abort",
  "retry_count":1,
  "step_delay_ms":500
}
```
**Options:**
- `on_error`: `"abort"` (stop), `"skip"` (continue), `"retry"` (retry step)
- `retry_count`: Number of retries per step on failure
- `step_delay_ms`: Delay between steps
- Variables support `{{variable_name}}` substitution in any string field
- Step output is captured as `_step1_url`, `_step1_title`, etc. for later steps

**Built-in templates:** `google_search`, `login`, `screenshot_full`

#### workflow-template
Execute a saved or built-in template.
```json
{"token":"my-agent","command":"workflow-template","template_name":"google_search","variables":{"query":"hello"}}
```

#### workflow-json
Execute workflow from a JSON string.
```json
{"token":"my-agent","command":"workflow-json","json":"{\"steps\":[{\"command\":\"navigate\",\"url\":\"https://example.com\"}]}"}
```

#### workflow-save
Save a workflow as a reusable template.
```json
{"token":"my-agent","command":"workflow-save","name":"my-login","steps":[{"command":"navigate","url":"{{url}}"},{"command":"fill-form","fields":{"#user":"{{user}}","#pass":"{{pass}}"}},{"command":"click","selector":"button[type=submit]"}],"variables":{"url":"","user":"","pass":""},"description":"Generic login flow"}
```

#### workflow-list
List all workflow templates (built-in + saved).
```json
{"token":"my-agent","command":"workflow-list"}
```

#### workflow-status
Get status of a running workflow.
```json
{"token":"my-agent","command":"workflow-status","workflow_id":"wf-1700000000"}
```

---

### Network Capture

#### network-start
Start capturing all network requests on a page.
```json
{"token":"my-agent","command":"network-start","page_id":"main","url_pattern":"api\\.example\\.com","resource_types":["xhr","fetch"],"methods":["GET","POST"],"capture_body":true}
```

#### network-stop
Stop capturing and get summary with counts by type, method, and status.
```json
{"token":"my-agent","command":"network-stop"}
```

#### network-get
Get captured requests with filters and pagination.
```json
{"token":"my-agent","command":"network-get","url_pattern":"/api/","resource_type":"xhr","method":"POST","status_code":200,"api_only":true,"limit":50,"offset":0}
```

#### network-apis
Discover all API endpoints from captured traffic. Groups by base URL with methods, status codes, and content types.
```json
{"token":"my-agent","command":"network-apis"}
```

#### network-detail
Get full details of a captured request by ID (headers, body, response, timing).
```json
{"token":"my-agent","command":"network-detail","request_id":"abc123"}
```

#### network-stats
Get capture statistics (total, failed, avg duration, by type/method/status).
```json
{"token":"my-agent","command":"network-stats"}
```

#### network-export
Export captured requests to file.
```json
{"token":"my-agent","command":"network-export","format":"json","filename":"my-capture.json"}
{"token":"my-agent","command":"network-export","format":"har"}
```

#### network-clear
Clear captured requests.
```json
{"token":"my-agent","command":"network-clear"}
```

---

### Security Scanners

#### scan-xss
Scan a URL for Cross-Site Scripting vulnerabilities. Tests URL parameters and form inputs with 12 payloads.
```json
{"token":"my-agent","command":"scan-xss","url":"https://target.com/search?q=test"}
```
**Response:** `{"status":"success","scanner":"xss","vulnerabilities_found":1,"vulnerabilities":[{"type":"XSS","parameter":"q","payload":"<script>alert(\"XSS\")</script>","confidence":0.85,"severity":"high"}]}`

#### scan-sqli
Scan a URL for SQL injection. Tests URL parameters with 10 SQLi payloads and checks for 25+ SQL error patterns.
```json
{"token":"my-agent","command":"scan-sqli","url":"https://target.com/page?id=1"}
```

#### scan-sensitive
Scan the current page for exposed sensitive data: AWS keys, GitHub tokens, API keys, private keys, JWT tokens, passwords in URLs, emails, IP addresses, internal IPs.
```json
{"token":"my-agent","command":"scan-sensitive"}
```

---

### Authentication

#### save-creds
Save login credentials with AES-256 encryption.
```json
{"token":"my-agent","command":"save-creds","domain":"github.com","username":"user@email.com","password":"secret"}
```

#### auto-login
Auto-login using saved credentials. Detects common login form patterns automatically.
```json
{"token":"my-agent","command":"auto-login","url":"https://github.com/login","domain":"github.com"}
```

---

### Forms

#### fill-job
Auto-fill job application forms with profile data. Detects fields by name/placeholder/label patterns.
```json
{"token":"my-agent","command":"fill-job","url":"https://company.com/apply","profile":{"email":"user@example.com","first_name":"John","last_name":"Doe","phone":"+1234567890"}}
```
**Supported fields:** email, first_name, last_name, full_name, phone, address, city, state, zip, country, linkedin, website, cover_letter, salary, experience

---

### Media

#### transcribe
Transcribe video/audio from a URL. Supports YouTube and direct media URLs. Uses local Whisper (no cloud APIs).
```json
{"token":"my-agent","command":"transcribe","url":"https://youtube.com/watch?v=xxx","language":"en"}
```

---

### Proxy

#### set-proxy
Set proxy for the browser. Requires browser restart.
```json
{"token":"my-agent","command":"set-proxy","proxy_url":"http://user:pass@proxy.example.com:8080"}
```

#### get-proxy
Get current proxy configuration.
```json
{"token":"my-agent","command":"get-proxy"}
```

---

### Mobile Emulation

#### emulate-device
Emulate a mobile, tablet, or desktop device. Changes viewport, user agent, device scale factor, and touch support.
```json
{"token":"my-agent","command":"emulate-device","device":"iphone_14"}
```
**Available devices:** `iphone_se`, `iphone_14`, `iphone_14_pro_max`, `ipad`, `ipad_pro`, `galaxy_s23`, `galaxy_tab_s9`, `pixel_8`, `desktop_1080`, `desktop_1440`, `desktop_4k`

#### list-devices
List all available device presets with viewport, scale factor, and type.
```json
{"token":"my-agent","command":"list-devices"}
```

---

### Sessions

#### save-session
Save full browser state: cookies, localStorage, sessionStorage, open tabs, device emulation.
```json
{"token":"my-agent","command":"save-session","name":"my-work"}
```

#### restore-session
Restore a previously saved session. Recreates all tabs, cookies, and storage.
```json
{"token":"my-agent","command":"restore-session","name":"my-work"}
```

#### list-sessions
List all saved sessions with metadata.
```json
{"token":"my-agent","command":"list-sessions"}
```

#### delete-session
Delete a saved session.
```json
{"token":"my-agent","command":"delete-session","name":"my-work"}
```

---

## Anti-Detection Features

Agent-OS **prevents** CAPTCHAs from loading — it doesn't solve them:

### Blocked Bot Detection Systems
- Google reCAPTCHA v2/v3
- hCaptcha
- Cloudflare Turnstile
- PerimeterX
- DataDome
- Imperva/Incapsula
- Akamai Bot Manager
- Shape Security
- Kasada

### How It Works

1. **Network-Level Blocking** — Detection scripts are intercepted and blocked before the browser executes them. Blocked requests return fake "human verified" responses.

2. **DOM Patching (14 stealth patches)**:
   - `navigator.webdriver` → undefined
   - Realistic plugin list (Chrome PDF, Native Client)
   - Languages, platform, hardware concurrency spoofing
   - `window.chrome` runtime object
   - WebGL fingerprint (Intel GPU)
   - Canvas fingerprint noise (subtle bit XOR)
   - Audio context fingerprint
   - WebRTC IP leak blocking
   - Notification permission
   - Media device enumeration

3. **Human Mimicry**:
   - Bezier curve mouse movements with micro-tremor
   - Realistic typing delays (40-300ms per keystroke)
   - Word pause simulation (200-600ms)
   - 3% typo rate with correction
   - Natural scroll (multi-step with variance)
   - Hesitation before actions

4. **Fake Responses**: Blocked bot detection endpoints receive realistic fake responses matching the expected schema (success, score, risk_score, etc.).

### Limitations
- Advanced TLS fingerprinting can still detect Playwright
- Some sophisticated bot protection (BotD) may still work
- Effectiveness varies by site — test on your specific targets

---

## Configuration

Default config at `~/.agent-os/config.yaml`:

```yaml
server:
  host: 127.0.0.1
  ws_port: 8000
  http_port: 8001

browser:
  headless: true
  viewport: {width: 1920, height: 1080}
  max_ram_mb: 500
  user_agent: null  # Auto-generated if null

session:
  timeout_minutes: 15
  auto_wipe: true

security:
  captcha_bypass: true
  human_mimicry: true
```

---

## Privacy & Security

- **Local Only** — All processing on your machine, no external services
- **Zero Telemetry** — No data collection whatsoever
- **Session Auto-Wipe** — Browser data destroyed after timeout (default 15 min)
- **Encrypted Vault** — Credentials stored with AES-256 at `~/.agent-os/vault.enc`
- **Token Auth** — All commands require valid agent token
- **RAM Monitor** — Built-in process monitor caps memory usage
- **Cookie Persistence** — Saved to `~/.agent-os/cookies/` (auto-loaded on restart)
- **Download Isolation** — Downloads saved to `~/.agent-os/downloads/`

---

## Error Handling

All responses follow this format:

**Success:**
```json
{"status":"success","data":"..."}
```

**Error:**
```json
{"status":"error","error":"Descriptive error message"}
```

**Partial (workflows):**
```json
{"status":"partial","successful_steps":3,"failed_steps":1,"steps":[...]}
```

---

## Connector Tool Counts

| Connector | Tools | File |
|-----------|-------|------|
| MCP (Claude/Codex) | 38 | `connectors/mcp_server.py` |
| OpenAI / Claude API | 38 | `connectors/openai_connector.py` |
| OpenClaw | 38 | `connectors/openclaw_connector.py` |
| CLI (Bash) | 74 commands | `connectors/agent-os-tool.sh` |
| HTTP API | 74 commands | Server at `/command` |
| Persistent API | 30+ commands | Server at `/persistent/command` |

---

## Persistent Chromium (Production Mode)

For production deployments serving multiple concurrent users, enable persistent mode:

```bash
python3 main.py --persistent --agent-token "my-token"
```

### Architecture

```
PersistentBrowserManager (singleton)
├── BrowserInstance 1 (Chromium PID 1234)
│   ├── UserContext "user-abc" → ~/.agent-os/users/user-abc/
│   │   ├── main page (tab)
│   │   ├── tab-1 (tab)
│   │   ├── cookies.json
│   │   └── context_state.json
│   ├── UserContext "user-def" → ~/.agent-os/users/user-def/
│   └── ... (up to 50 contexts)
├── BrowserInstance 2 (Chromium PID 5678)
│   └── ... (next 50 users)
└── BrowserInstance N (up to 5 instances = 250 concurrent users)
```

### Key Design Decisions

1. **Playwright persistent contexts** — Each user gets a real Chromium profile directory under `~/.agent-os/users/{user_id}/`. Cookies, localStorage, and sessionStorage persist on disk — survive restarts.

2. **Browser pool** — Multiple Chromium processes for horizontal scaling. Users are assigned to the least-loaded instance via round-robin.

3. **Per-user isolation** — Each user's context is completely isolated. No data leaks between users.

4. **Auto-recovery** — Health checks every 30s. If a Chromium instance crashes, it's automatically restarted and all user contexts are restored from saved state.

5. **LRU eviction** — Idle contexts are evicted after configurable timeout (default 60 min). State is saved to disk before eviction, so users can resume later.

6. **Memory cap** — System monitors total Chromium memory. When cap is exceeded, oldest idle contexts are evicted.

7. **Zero-downtime state** — Manager state is periodically saved to `~/.agent-os/state/manager_state.json`. On restart, all user contexts are automatically restored.

### Configuration

```yaml
persistent:
  enabled: false                       # Enable persistent mode
  max_instances: 5                     # Max Chromium processes (each handles ~50 users)
  max_contexts_per_instance: 50        # Max user contexts per Chromium process
  health_check_interval_seconds: 30    # How often to check browser health
  idle_timeout_minutes: 60             # Evict idle contexts after this
  memory_cap_mb: 4000                  # Total Chromium memory cap
  auto_restart: true                   # Auto-restart crashed browsers
```

### Scaling Estimates

| Config | Concurrent Users | Memory (est.) |
|--------|-----------------|---------------|
| 1 instance × 50 contexts | 50 | ~800 MB |
| 3 instances × 50 contexts | 150 | ~2.4 GB |
| 5 instances × 50 contexts | 250 | ~4 GB |
| 5 instances × 100 contexts | 500 | ~8 GB |

### API Endpoints

#### GET /persistent/health
Full health report of all browser instances.

```bash
curl http://localhost:8001/persistent/health
```

**Response:**
```json
{
  "status": "running",
  "instances": {
    "browser-a1b2c3d4": {
      "state": "running",
      "uptime_seconds": 3600,
      "active_contexts": 12,
      "total_pages": 28,
      "memory_mb": 450.2,
      "crash_count": 0,
      "restart_count": 0
    }
  },
  "summary": {
    "total_instances": 1,
    "total_user_contexts": 12,
    "unique_users": 12,
    "total_memory_mb": 450.2
  }
}
```

#### GET /persistent/users
List all active user contexts.

```bash
curl http://localhost:8001/persistent/users
```

#### POST /persistent/command
Execute a command for a specific user. Creates context if it doesn't exist.

```bash
curl -X POST http://localhost:8001/persistent/command \
  -H "Content-Type: application/json" \
  -d '{
    "token": "my-agent",
    "user_id": "user-123",
    "command": "navigate",
    "url": "https://example.com"
  }'
```

**All standard commands work** — just add `user_id` field. The system automatically:
- Creates or retrieves the user's persistent context
- Executes the command
- Saves state to disk
- Returns the result

### State Persistence

User state is saved to `~/.agent-os/users/{user_id}/`:

```
~/.agent-os/users/user-123/
├── context_state.json    # Tabs, viewport, device, last active
├── cookies.json          # Full Playwright storage state
└── (Chromium profile data — cookies, localStorage, etc.)
```

On restart, these are automatically restored. Users resume where they left off.
