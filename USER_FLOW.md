# Agent-OS — Complete User Flow (A to Z)

> From installation to daily usage — everything you need to know.

---

## 📦 Step 1: Installation

### Option A: pip install (Recommended)

```bash
pip install agent-os
```

**What you see:**
```
╔══════════════════════════════════════════════════╗
║  Installing Agent-OS...                          ║
║  ✓ playwright installed                          ║
║  ✓ curl_cffi installed                           ║
║  ✓ 82 Python modules ready                       ║
╚══════════════════════════════════════════════════╝
```

### Option B: git clone

```bash
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS
pip install -r requirements.txt
```

**What you see:**
```
Cloning into 'Agent-OS'...
remote: Enumerating objects: 127 commits
Installing dependencies...
 ✓ playwright>=1.40.0
 ✓ curl_cffi>=0.5.0
 ✓ pydantic>=2.0
 ✓ aiohttp>=3.9
 ✓ 42 packages installed
```

### Option C: Docker

```bash
docker pull agent-os/agent-os:latest
docker run -p 8000:8000 -p 8001:8001 agent-os/agent-os:latest
```

---

## 🚀 Step 2: First Launch

```bash
python main.py
```

**What you see:**
```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   █████╗ ██████╗ ████████╗ ██████╗ ██╗  ██╗                 ║
║  ██╔══██╗██╔══██╗╚══██╔══╝██╔═══██╗██║ ██╔╝                 ║
║  ███████║██████╔╝   ██║   ██║   ██║█████╔╝                  ║
║  ██╔══██║██╔══██╗   ██║   ██║   ██║██╔═██╗                 ║
║  ██║  ██║██║  ██║   ██║   ╚██████╔╝██║  ██╗                ║
║  ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝                ║
║                                                              ║
║  Browser Automation with Stealth & AI                       ║
║  v2.0.0 • 82 Modules • 241 Tests • 99.6% Pass Rate         ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🌐 WebSocket Server    → ws://localhost:8000               ║
║  🔌 REST API Server     → http://localhost:8001             ║
║  📊 Debug Dashboard     → http://localhost:8080             ║
║                                                              ║
║  🔒 Stealth: 3 layers active (CDP + GodMode + Evasion)     ║
║  🤖 Swarm: 20 agents ready (max 50)                        ║
║  🛡️ Captcha: Preemption mode: conservative                 ║
║                                                              ║
║  Ready. No API keys needed. No external LLM needed.         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## ⚙️ Step 3: Setup Wizard (Optional)

```bash
python main.py --setup
```

**Interactive wizard:**
```
╔══════════════════════════════════════════════════╗
║  Agent-OS Setup Wizard                          ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  [1/5] Browser Settings                         ║
║  ─────────────────────────                      ║
║  Headless mode? (y/N): y                        ║
║  Browser: chromium                              ║
║  Max RAM (MB): 2048                             ║
║                                                  ║
║  [2/5] Security Settings                        ║
║  ─────────────────────────                      ║
║  Enable JWT auth? (Y/n): y                      ║
║  Enable stealth mode? (Y/n): y                  ║
║  Stealth level (1-3): 3                         ║
║    1 = CDP only                                 ║
║    2 = CDP + GodMode                            ║
║    3 = CDP + GodMode + Evasion (recommended)    ║
║                                                  ║
║  [3/5] Captcha Settings                         ║
║  ─────────────────────────                      ║
║  Captcha preemption mode:                       ║
║    1 = conservative (safe, fewer false alarms)  ║
║    2 = moderate (balanced)                      ║
║    3 = aggressive (more proactive)              ║
║  Choose (1-3): 1                                ║
║                                                  ║
║  [4/5] Swarm Settings                           ║
║  ─────────────────────────                      ║
║  Max parallel agents (5-50): 20                 ║
║  Search timeout (seconds): 30                   ║
║                                                  ║
║  [5/5] Optional Integrations                    ║
║  ─────────────────────────                      ║
║  CAPTCHA_API_KEY (press Enter to skip):         ║
║  LLM_API_KEY (press Enter to skip):             ║
║                                                  ║
║  ✅ Configuration saved to config.yaml           ║
╚══════════════════════════════════════════════════╝
```

> **Important:** No API keys are required. The system works fully without any external services.
> When installed in Claude/Codex, it uses the host platform's LLM automatically.

---

## 🔗 Step 4: Connect to Agent-OS

### Mode 1: Claude Desktop / Claude Code (MCP)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agent-os": {
      "command": "python",
      "args": ["/path/to/Agent-OS/connectors/mcp_server.py"]
    }
  }
}
```

**What Claude sees:**
```
╔══════════════════════════════════════════════════╗
║  Agent-OS MCP Tools Available (38 tools)        ║
╠══════════════════════════════════════════════════╣
║  • navigate        → Go to URL                  ║
║  • fill_form       → Fill form fields           ║
║  • click           → Click element              ║
║  • screenshot      → Take screenshot            ║
║  • get_text        → Extract page text          ║
║  • search          → Web search with swarm      ║
║  • fill_login      → Auto-fill login forms      ║
║  • captcha_check   → Check for captcha risk     ║
║  • ... and 30 more tools                        ║
╚══════════════════════════════════════════════════╝
```

### Mode 2: OpenAI / GPT-4 Function Calling

```python
from connectors.openai_connector import get_tools, call_tool

tools = get_tools("openai")   # Returns 38 function definitions

# Use with OpenAI chat.completions
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Go to google.com and search for AI news"}],
    tools=tools,
)
```

### Mode 3: Direct REST API

```bash
# Navigate
curl -X POST http://localhost:8001/api/command \
  -H "Content-Type: application/json" \
  -d '{"token":"your-token","command":"navigate","url":"https://google.com"}'

# Fill form
curl -X POST http://localhost:8001/api/command \
  -H "Content-Type: application/json" \
  -d '{"token":"your-token","command":"fill_form","profile":{"email":"test@test.com","name":"John"}}'

# Screenshot
curl -X POST http://localhost:8001/api/command \
  -H "Content-Type: application/json" \
  -d '{"token":"your-token","command":"screenshot"}'

# Search with swarm
curl -X POST http://localhost:8001/api/command \
  -H "Content-Type: application/json" \
  -d '{"token":"your-token","command":"search","query":"latest AI news","agents":["news_hound","tech_scanner"]}'
```

---

## 🖥️ Step 5: Debug Dashboard

Open `http://localhost:8080` in your browser:

```
╔══════════════════════════════════════════════════════════════════════╗
║  Agent-OS Dashboard                                    [● Live]  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ ║
║  │  Browser     │  │  Command    │  │  Swarm      │  │  Login   │ ║
║  │  Tab         │  │  Center     │  │  Search     │  │  Handoff │ ║
║  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ ║
║                                                                    ║
║  ┌─ Browser Tab ──────────────────────────────────────────────────┐ ║
║  │                                                                 │ ║
║  │  URL: [https://example.com          ] [Go] [Screenshot]       │ ║
║  │                                                                 │ ║
║  │  ┌───────────────────────────────────────────────────────┐    │ ║
║  │  │                                                       │    │ ║
║  │  │  Example Domain                                       │    │ ║
║  │  │  This domain is for use in illustrative examples...   │    │ ║
║  │  │                                                       │    │ ║
║  │  │  More information...                                  │    │ ║
║  │  │                                                       │    │ ║
║  │  └───────────────────────────────────────────────────────┘    │ ║
║  │                                                                 │ ║
║  │  Stealth: ●●● 3 layers active   Captcha risk: LOW             │ ║
║  │  Session: active (5m 23s)        Agents: 3/20 busy            │ ║
║  └─────────────────────────────────────────────────────────────────┘ ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 🤖 Step 6: Swarm Search (Multi-Agent)

Send a search query to the swarm:

```python
# Via Python
from src.agent_swarm.config import SwarmConfig
from src.agent_swarm.agents.pool import AgentPool

pool = AgentPool(max_workers=20)
results = await pool.search_parallel(
    query="best laptops under $1000 2025",
    agent_profiles=["price_checker", "tech_scanner", "review_reader"],
    search_backend=backend,
)
```

```bash
# Via API
curl -X POST http://localhost:8001/api/command \
  -d '{"command":"search","query":"best laptops under $1000","agents":["price_checker","tech_scanner","review_reader"]}'
```

**What happens internally:**
```
╔══════════════════════════════════════════════════╗
║  Swarm Search: "best laptops under $1000"        ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  🧠 Tier 1: Rule-based routing                  ║
║     → Category: needs_web (confidence: 0.95)    ║
║                                                  ║
║  🤖 Agents dispatched: 3                        ║
║     • price_checker  → Searching prices...  ✓   ║
║     • tech_scanner   → Searching specs...   ✓   ║
║     • review_reader  → Reading reviews...  ✓    ║
║                                                  ║
║  📊 Results: 27 unique, 5 deduplicated          ║
║  ⏱️  Time: 4.2s                                  ║
║  📋 Quality score: 0.87                         ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

### Available Agent Profiles (20):

| Agent | Expertise | Keywords |
|-------|-----------|----------|
| `generalist` | General web search | Any query |
| `news_hound` | Breaking news, current events | news, latest, today, breaking |
| `price_checker` | Price comparison, deals | price, cost, cheap, discount, buy |
| `tech_scanner` | Tech, programming, software | code, debug, API, Python, software |
| `review_reader` | Product reviews, ratings | review, best, compare, vs, rating |
| `job_hunter` | Job listings, careers | job, hiring, salary, career, resume |
| `travel_scout` | Travel, flights, hotels | flight, hotel, travel, vacation, book |
| `food_finder` | Restaurants, recipes, food | restaurant, recipe, food, menu, dine |
| `health_researcher` | Medical, health, fitness | health, medical, symptom, doctor |
| `finance_tracker` | Stocks, crypto, markets | stock, crypto, bitcoin, market, invest |
| `sports_fan` | Sports scores, news | score, game, match, team, player |
| `entertainment` | Movies, TV, music, games | movie, show, game, music, streaming |
| `education_seeker` | Courses, tutorials, learning | course, learn, tutorial, study, school |
| `legal_eagle` | Law, regulations, compliance | law, legal, regulation, compliance |
| `real_estate` | Property, housing, rent | apartment, house, rent, buy, mortgage |
| `auto_expert` | Cars, vehicles, auto | car, vehicle, auto, drive, model |
| `science_nerd` | Research, papers, science | research, paper, study, experiment |
| `social_watcher` | Social media, trends | trend, viral, social, instagram, tiktok |
| `weather_watcher` | Weather, climate, forecast | weather, forecast, rain, temperature |
| `local_explorer` | Local businesses, maps | near me, nearby, local, address, map |

---

## 📝 Step 7: Form Filling

### Automatic Form Detection & Filling

```python
# Via API
curl -X POST http://localhost:8001/api/command \
  -d '{
    "command": "fill_form",
    "profile": {
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "phone": "+1-555-123-4567"
    }
  }'
```

**What happens:**
```
╔══════════════════════════════════════════════════╗
║  Form Filling: GitHub Login Page                 ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  🔍 Detected 2 form fields:                     ║
║     • login_field (username/email) → matched    ║
║     • password (password) → matched             ║
║                                                  ║
║  ✏️  Filling:                                    ║
║     • #login_field ← "user@example.com" ✓       ║
║     • #password   ← "••••••••" ✓                ║
║                                                  ║
║  🔄 React onChange dispatched: Yes               ║
║  🎯 Strategy: native_setter (1st attempt)        ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

### 4-Strategy React-Compatible Fill:
1. **native_setter** — Uses `Object.getOwnPropertyDescriptor` to set value
2. **direct_value** — Falls back to direct `.value =` assignment
3. **react_onchange** — Dispatches `__reactEventHandlers` onChange event
4. **define_property** — Redefines property descriptor as last resort

---

## 🛡️ Step 8: Captcha Preemption

**Before navigating to a risky site:**
```
╔══════════════════════════════════════════════════╗
║  Captcha Preemption: accounts.google.com         ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  ⚠️  Risk Assessment:                            ║
║     • Risk Level: HIGH                           ║
║     • Known captcha site: Yes                    ║
║     • Detection types: [turnstile, recaptcha]    ║
║     • Recommended: preflight_check               ║
║                                                  ║
║  🔍 Preflight Check:                             ║
║     • TLS fingerprint: Chrome 146 ✓              ║
║     • Cookie state: Clean ✓                      ║
║     • JavaScript context: Ready ✓                ║
║                                                  ║
║  🚀 Proceeding with enhanced stealth...          ║
║     • Evasion engine: Active                     ║
║     • Human mimicry: Enabled                     ║
║     • Monitor: Watching for captcha frames       ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

---

## 📊 Step 9: Daily Usage — Common Commands

| Command | Description | Example |
|---------|-------------|---------|
| `navigate` | Go to URL | `{"command": "navigate", "url": "https://google.com"}` |
| `fill_form` | Auto-fill form | `{"command": "fill_form", "profile": {"email": "..."}}` |
| `click` | Click element | `{"command": "click", "selector": "#submit-btn"}` |
| `screenshot` | Capture page | `{"command": "screenshot"}` |
| `get_text` | Extract text | `{"command": "get_text"}` |
| `search` | Swarm search | `{"command": "search", "query": "..."}` |
| `fill_login` | Fill login form | `{"command": "fill_login", "profile": {...}}` |
| `captcha_check` | Check captcha risk | `{"command": "captcha_check", "url": "..."}` |
| `structured_output` | AI data extraction | `{"command": "structured_output"}` |
| `session_save` | Save browser session | `{"command": "session_save"}` |
| `session_load` | Load saved session | `{"command": "session_load", "id": "..."}` |
| `handoff_start` | Start login handoff | `{"command": "handoff_start", "url": "..."}` |
| `handoff_status` | Check handoff status | `{"command": "handoff_status"}` |
| `health` | System health check | `{"command": "health"}` |
| `config_get` | Get configuration | `{"command": "config_get"}` |
| `config_set` | Update configuration | `{"command": "config_set", "key": "...", "value": "..."}` |

---

## 🔧 Step 10: Troubleshooting

| Problem | Solution |
|---------|----------|
| Browser won't start | Run `playwright install chromium` |
| 403 Forbidden on sites | Normal — stealth mode helps but some sites still block |
| Captcha detected | Use `captcha_check` before navigating; enable preemption mode |
| React form not filling | System auto-detects React and uses onChange dispatch |
| Session expired | Use `session_save` to persist, `session_load` to restore |
| Docker --no-sandbox | Auto-detected, no manual config needed |
| Port 8000/8001 in use | Change in `config.yaml` under `server.ws_port` / `server.http_port` |

---

## 📋 Quick Reference Card

```
┌─────────────────────────────────────────────────────┐
│  Agent-OS Quick Reference                           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Start:        python main.py                       │
│  Setup:        python main.py --setup               │
│  MCP:          python connectors/mcp_server.py      │
│  Dashboard:    http://localhost:8080                 │
│  REST API:     http://localhost:8001/api/command     │
│  WebSocket:    ws://localhost:8000                   │
│                                                     │
│  Stealth:      3 layers (CDP + GodMode + Evasion)   │
│  Agents:       20 profiles (max 50 concurrent)      │
│  Tools:        38 MCP/API commands                  │
│  Auth:         JWT + API Keys + Legacy tokens       │
│                                                     │
│  No API keys required.                              │
│  No external LLM needed.                            │
│  Uses host platform's LLM when available.           │
│                                                     │
└─────────────────────────────────────────────────────┘
```
