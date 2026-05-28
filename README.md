<p align="center">
  <img src="docs/agent_x_logo.png" width="180" alt="Agent X Logo">
</p>

<h1 align="center">Agent X</h1>
<p align="center"><strong>Autonomous AI Browser Engine</strong></p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/version-4.0.0-blue.svg?style=flat-square" alt="Version 4.0.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=flat-square" alt="Docker Ready"></a>
  <img src="https://img.shields.io/badge/tools-209+-brightgreen.svg?style=flat-square" alt="209+ Tools">
  <br/>
  <img src="https://img.shields.io/badge/stealth-99%25-success.svg?style=flat-square" alt="Stealth 99%">
  <img src="https://img.shields.io/badge/captcha-solver-orange.svg?style=flat-square" alt="CAPTCHA Solver">
  <img src="https://img.shields.io/badge/swarm-enabled-purple.svg?style=flat-square" alt="Swarm Enabled">
  <img src="https://img.shields.io/badge/multi--tab-supported-blueviolet.svg?style=flat-square" alt="Multi-Tab">
  <img src="https://img.shields.io/badge/visual--testing-integrated-ff69b4.svg?style=flat-square" alt="Visual Testing">
</p>

---

## What is Agent X?

**Agent X** is an autonomous browser engine that gives AI agents a **real, persistent, and self-hosted web browser** with zero-friction installation. Built on a battle-tested foundation and hardened through extensive real-world usage.

It exposes **209+ production tools** for mouse interactions, form filling, data extraction, CAPTCHA bypass, session persistence, multi-tab coordination, and visual regression testing. Agent X turns your LLM (Claude Code, Cursor, GPT-4o, Claude Desktop, Claude Web, or custom agents) into an autonomous web operator that can navigate complex sites, bypass CDNs, and complete multi-step workflows.

### What's New in v4.0.0

- **Multi-Tab Handling**: AI agents can now manage multiple browser tabs simultaneously, switching contextually like humans
- **AI Visual Testing Engine**: Zero-cost visual regression testing that sends diffs to your connected AI for analysis
- **Claude Web Direct Connect (MCP over SSE)**: Connect Agent X directly from Claude.ai web interface via secure tunnel
- **Token Optimizer**: Adaptive page compression reducing LLM token usage by 90%+
- **99% Stealth Success Rate**: Enhanced anti-detection with 5-layer defense
- **Smart Navigator**: Auto-switches between HTTP and browser per domain
- **CAPTCHA Solver**: Built-in OCR + AI-based challenge solving
- **Agent Swarm**: Multi-agent orchestration with shared memory
- **Production Auth**: JWT + API keys + legacy token support
- **Docker Ready**: One-command deploy with Docker Compose

---

## Quick Start

### One-Line Install (Linux/macOS)

```bash
curl -sSL https://raw.githubusercontent.com/unknownsorcerer007/Agent-X/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/unknownsorcerer007/Agent-X/main/install.ps1 | iex
```

### Docker

```bash
git clone https://github.com/unknownsorcerer007/Agent-X.git
cd Agent-X
export POSTGRES_PASSWORD="your-strong-password"
docker compose up -d
```

### Manual Install

```bash
# Clone the repository
git clone https://github.com/unknownsorcerer007/Agent-X.git
cd Agent-X

# Install dependencies
pip install -r requirements.txt

# Install browser engine
python -m patchright install chromium

# Start Agent X
python main.py --agent-token "your-secure-token"
```

---

## Architecture

Agent X uses a **5-layer stealth defense system**:

1. **Network Layer**: Real Chrome/Firefox TLS handshakes (JA3/JA4 fingerprints) via curl_cffi
2. **CDP Layer**: Dynamic runtime script injection to spoof all browser properties
3. **JavaScript Layer**: WebGL/Canvas spoofing, webdriver masking, audio synthesis
4. **Behavior Layer**: Human-like mouse movements (Bezier curves), natural typing
5. **Fingerprint Layer**: Consistent per-session fingerprints across all vectors

---

## Key Features

| Feature | Description | Status |
|---------|-------------|--------|
| **209+ Tools** | Complete browser automation toolkit | Active |
| **Stealth Engine** | 5-layer anti-detection system | 99% Bypass Rate |
| **Multi-Tab Handler** | Human-like multi-tab browsing for AI agents | Active |
| **Visual Testing** | Zero-cost AI visual regression testing | Active |
| **Token Optimizer** | Adaptive compression, 90%+ token reduction | Active |
| **Smart Navigator** | Auto HTTP/browser strategy selection | Active |
| **CAPTCHA Solver** | OCR + AI challenge solving | Active |
| **Agent Swarm** | Multi-agent orchestration | Active |
| **Session Manager** | Encrypted cookie persistence | Active |
| **Proxy Rotation** | Residential/mobile/datacenter | Active |
| **Cloudflare Bypass** | v1/v2/v3 + Turnstile support | Active |
| **JWT Auth** | Production-grade authentication | Active |
| **API Keys** | Scoped permissions + rate limits | Active |
| **Docker Deploy** | One-command production deploy | Active |

---

## Connectors

Agent X supports multiple connector pipelines:

- **MCP (Model Context Protocol)**: Claude Desktop, Cursor, Claude Web integration
- **WebSocket**: Real-time agent communication
- **HTTP REST**: curl/simple integrations
- **OpenAI Compatible**: Works with any OpenAI-compatible API

### MCP Setup for Claude Desktop

```json
{
  "mcpServers": {
    "agent-x": {
      "command": "/path/to/agent-x/venv/bin/python",
      "args": ["/path/to/agent-x/connectors/mcp_passthrough.py"],
      "env": {
        "AGENT_X_URL": "http://localhost:8001",
        "AGENT_X_TOKEN": "your-token"
      }
    }
  }
}
```

### Claude Web Direct Connect (via Cloudflare Tunnel)

Connect Agent X directly from **Claude.ai web interface** — no desktop app required:

```bash
# Start Agent X MCP SSE server
python connectors/mcp_sse_server.py

# In another terminal, start the tunnel
python -c "
import asyncio
from src.tools.tunnel_manager import TunnelManager

tunnel = TunnelManager(local_port=8002)
url = asyncio.run(tunnel.start())
if url:
    print(f'Public URL: {url}/sse')
    print('Paste this into Claude.ai → Settings → MCP Servers')
    asyncio.run(asyncio.sleep(3600))  # Keep alive
"
```

The tunnel creates a secure HTTPS URL that Claude Web can connect to directly.

---

## Multi-Tab Handling

Agent X supports human-like multi-tab browsing:

```python
from src.tools.multi_tab_manager import MultiTabHandler

# Initialize multi-tab handler
tabs = MultiTabHandler(browser)
await tabs.start()

# Create tabs for different tasks
gmail = await tabs.create_tab("gmail", "https://gmail.com", group="work")
docs = await tabs.create_tab("docs", "https://docs.google.com", group="work")
api = await tabs.create_tab("api", "https://api.example.com", group="dev")

# Switch between tabs contextually
await tabs.switch_to(gmail)
await tabs.switch_by_name("docs")

# Execute actions without switching
result = await tabs.execute_in_tab(api, lambda page: page.evaluate("fetch('/data').then(r=>r.json())"))

# Get overview for AI decision making
overview = tabs.get_tab_overview()
```

---

## AI Visual Testing

Zero-cost visual regression testing:

```python
from src.tools.visual_testing import VisualTestingEngine

vt = VisualTestingEngine()

# Capture baseline
await vt.capture_baseline(page, "homepage")

# After deployment changes
result = await vt.compare_visual(page, "homepage")
if result.has_changes:
    # Send to user's AI for analysis (zero external cost)
    analysis = await vt.analyze_with_user_ai(result)
    print(analysis["prompt"])  # Ready to send to Claude/GPT
```

---

## Token Optimization

Agent X includes advanced token optimization:

```python
from src.tools.token_optimizer import capture_optimized, capture_diff_only

# Optimized snapshot (90%+ token reduction)
snapshot = await capture_optimized(page, strategy="adaptive")
print(f"Estimated tokens: {snapshot.token_estimate}")

# For subsequent captures on same page
changes = await capture_diff_only(page)  # Only changed elements
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `ws://localhost:8000` | WebSocket | Real-time agent communication |
| `http://localhost:8001/health` | GET | Health check |
| `http://localhost:8001/auth/register` | POST | User registration |
| `http://localhost:8001/auth/login` | POST | User login |
| `http://localhost:8001/auth/api-keys` | POST | API key management |
| `http://localhost:8001/swarm/search` | POST | Swarm search |
| `http://localhost:8001/swarm/health` | GET | Swarm health |
| `http://localhost:8002/sse` | SSE | MCP SSE endpoint for Claude Web |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_X_TOKEN` | Legacy agent token | Auto-generated |
| `JWT_SECRET_KEY` | JWT signing key | Auto-generated |
| `DATABASE_DSN` | PostgreSQL connection | SQLite fallback |
| `REDIS_URL` | Redis connection | Disabled |
| `OPENAI_API_KEY` | OpenAI integration | Optional |
| `ANTHROPIC_API_KEY` | Claude integration | Optional |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_all.py -v
```

---

## Security

Agent X implements production-grade security:

- **bcrypt** password hashing
- **JWT** access + refresh tokens
- **API key** scoped permissions
- **Rate limiting** per token
- **Session encryption** for cookies
- **Input validation** on all endpoints
- **Audit logging** for all actions

---

## License

Agent X is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Agent X</strong> — Autonomous AI Browser Engine<br>
  Built with precision. Hardened for real-world usage.
</p>
