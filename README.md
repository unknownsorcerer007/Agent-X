<p align="center">
  <img src="docs/agent_x_logo.png" width="180" alt="Agent X Logo">
</p>

<h1 align="center">Agent X</h1>
<p align="center"><strong>Autonomous AI Browser Engine</strong></p>

<p align="center">
  <a href="https://github.com/unknownsorcerer007/Agent-X/releases"><img src="https://img.shields.io/badge/version-4.0.1-blue.svg?style=flat-square" alt="Version 4.0.1"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg?style=flat-square" alt="Python 3.10+"></a>
  <a href="Dockerfile"><img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=flat-square" alt="Docker Ready"></a>
  <img src="https://img.shields.io/badge/tools-209%2B-brightgreen.svg?style=flat-square" alt="209+ Tools">
  <br/>
  <img src="https://img.shields.io/badge/stealth-5--layer-orange.svg?style=flat-square" alt="5-Layer Stealth">
  <img src="https://img.shields.io/badge/swarm-enabled-purple.svg?style=flat-square" alt="Swarm Enabled">
  <img src="https://img.shields.io/badge/multi--tab-blueviolet.svg?style=flat-square" alt="Multi-Tab">
  <img src="https://img.shields.io/badge/captcha-solver-red.svg?style=flat-square" alt="CAPTCHA Solver">
  <img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="MIT License">
</p>

---

## What is Agent X?

**Agent X** is an autonomous browser engine that gives AI agents a **real, persistent, and self-hosted web browser** with zero-friction installation. Built on a battle-tested foundation and hardened through extensive real-world usage.

It exposes **209+ production tools** for mouse interactions, form filling, data extraction, CAPTCHA bypass, session persistence, multi-tab coordination, and visual regression testing. Agent X turns your LLM (Claude Code, Cursor, GPT-4o, Claude Desktop, Claude Web, or custom agents) into an autonomous web operator that can navigate complex sites, bypass CDNs, and complete multi-step workflows.

### What's New in v4.0.1

- Fixed WebGL vendor/renderer coherence — GPU now matches claimed OS platform
- Fixed `.env` file path resolution between setup wizard and main loader
- Fixed `sec-ch-ua-mobile` header for correct mobile/desktop signaling
- Cross-platform signal handling for graceful shutdown on Windows, macOS, Linux
- Comprehensive audit, test coverage, and stealth system documentation
- Production CI/CD pipeline with GitHub Actions

### What's New in v4.0.0

- **Multi-Tab Handling**: AI agents can manage multiple browser tabs simultaneously
- **AI Visual Testing Engine**: Zero-cost visual regression testing
- **Claude Web Direct Connect (MCP over SSE)**: Connect from Claude.ai via secure tunnel
- **Token Optimizer**: Adaptive page compression reducing LLM token usage by 90%+
- **Advanced Stealth Engine**: Enhanced anti-detection with 5-layer defense
- **Smart Navigator**: Auto-switches between HTTP and browser per domain
- **CAPTCHA Solver**: Built-in OCR + AI-based challenge solving
- **Agent Swarm**: Multi-agent orchestration with shared memory
- **Production Auth**: JWT + API keys + legacy token support
- **Docker Ready**: One-command deploy with Docker Compose

---

## Architecture

Agent X uses a **5-layer stealth defense system**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent X Architecture                      │
├─────────────────────────────────────────────────────────────┤
│  Connector Layer    │ MCP, WebSocket, HTTP REST, SSE        │
├─────────────────────┼───────────────────────────────────────┤
│  Agent Layer        │ Swarm orchestrator, Web Need Router   │
├─────────────────────┼───────────────────────────────────────┤
│  Tool Layer         │ 209+ tools (AI, DOM, visual, proxy)   │
├─────────────────────┼───────────────────────────────────────┤
│  Browser Layer      │ Multi-tab, session, smart navigator   │
├─────────────────────┼───────────────────────────────────────┤
│  Stealth Layer      │ CDP, God Mode, Adaptive, Evasion      │
│  (5-layer defense)  │ Human mimicry, CAPTCHA solver         │
├─────────────────────┼───────────────────────────────────────┤
│  Security Layer     │ Cloudflare bypass, Auth, TLS spoof    │
├─────────────────────┼───────────────────────────────────────┤
│  Infra Layer        │ PostgreSQL/SQLite, Redis, logging     │
└─────────────────────┴───────────────────────────────────────┘
```

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
| **5-Layer Stealth** | CDP + God Mode + Adaptive + Evasion + Human Mimicry | Active |
| **Multi-Tab Handler** | Human-like multi-tab browsing for AI agents | Active |
| **Visual Testing** | Zero-cost AI visual regression testing | Active |
| **Token Optimizer** | Adaptive compression, 90%+ token reduction | Active |
| **Smart Navigator** | Auto HTTP/browser strategy selection | Active |
| **CAPTCHA Solver** | OCR + AI challenge solving | Active |
| **Agent Swarm** | Multi-agent orchestration with shared memory | Active |
| **Session Manager** | Encrypted cookie persistence | Active |
| **Proxy Rotation** | Residential/mobile/datacenter with health checks | Active |
| **Cloudflare Bypass** | v1/v2/v3 + Turnstile + domain memory | Active |
| **JWT Auth** | Production-grade authentication (JWT + API keys) | Active |
| **Docker Deploy** | One-command production deploy | Active |

---

## Quick Start

### One-Line Install (Linux/macOS)

```bash
curl -sSL https://raw.githubusercontent.com/unknownsorcerer007/Agent-X/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
powershell -c "irm https://raw.githubusercontent.com/unknownsorcerer007/Agent-X/main/install.ps1 | iex"
```

> **Note for Windows users:** See [Windows Installation Guide](#windows-installation) below for detailed steps.

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

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install browser engine
python -m patchright install chromium

# Run first-time setup (optional — generates .env with JWT and token)
python main.py --setup

# Start Agent X
python main.py --agent-token "your-secure-token"
```

---

## Configuration

Agent X uses a layered configuration system:

1. **Defaults** — Built-in `DEFAULT_CONFIG` in `src/core/config.py`
2. **Config file** — `~/.agent-x/config.yaml` (YAML, auto-created on first run)
3. **Environment variables** — `.env` file (loaded from app dir or `~/.agent-x/.env`)
4. **CLI arguments** — Highest priority

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `JWT_SECRET_KEY` | JWT signing key | Auto-generated | Random 48-byte token |
| `AGENT_TOKEN` | Legacy agent token | Auto-generated | Random hex token |
| `DATABASE_DSN` | PostgreSQL connection | No | SQLite fallback |
| `REDIS_URL` | Redis connection | No | Disabled |
| `OPENAI_API_KEY` | OpenAI integration | No | Disabled |
| `ANTHROPIC_API_KEY` | Claude integration | No | Disabled |

---

## Usage

### Python API

```python
import asyncio
from src.core.browser import AgentBrowser
from src.core.config import Config

async def main():
    config = Config()
    browser = AgentBrowser(config)
    await browser.start()
    
    result = await browser.navigate("https://example.com")
    print(f"Title: {result['title']}")
    
    await browser.stop()

asyncio.run(main())
```

### WebSocket API

```javascript
const ws = new WebSocket('ws://localhost:8000');
ws.send(JSON.stringify({
    token: "your-token",
    command: "navigate",
    params: { url: "https://example.com" }
}));
```

### HTTP REST API

```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token" \
  -d '{"command": "screenshot"}'
```

### Multi-Tab Example

```python
from src.tools.multi_tab_manager import MultiTabHandler

tabs = MultiTabHandler(browser)
await tabs.start()

# Create tabs
gmail = await tabs.create_tab("gmail", "https://gmail.com", group="work")
docs = await tabs.create_tab("docs", "https://docs.google.com", group="work")

# Switch between tabs
await tabs.switch_to(gmail)
overview = tabs.get_tab_overview()
```

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

---

## Stealth System

Agent X implements production-grade anti-detection with **coherent cross-browser fingerprinting**:

- **WebGL vendor/renderer** auto-matches claimed OS (Apple GPU for macOS, rotated Intel/NVIDIA/AMD for Windows/Linux)
- **Client Hints** (`sec-ch-ua-*`) align with User-Agent Chrome version
- **Canvas/audio noise** is stable per session (seeded from GPU renderer hash)
- **Screen/viewport** dimensions match profile configuration
- **No duplicate overrides** — CDP stealth is sole authority, supplementary JS handles only non-overlapping features

For full technical details, see [STEALTH.md](STEALTH.md).

---

## Roadmap

- [ ] Safari/WebKit engine support
- [ ] Distributed agent swarm across multiple hosts
- [ ] Visual workflow builder (no-code)
- [ ] Browser plugin/extension marketplace
- [ ] Advanced CAPTCHA solving with vision models
- [ ] Automatic site-specific strategy learning

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Quick start for contributors:

```bash
git clone https://github.com/unknownsorcerer007/Agent-X.git
cd Agent-X
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

## Troubleshooting / FAQ

**Q: Installation fails with "python3-venv not found"**  
A: Run `sudo apt-get install python3-venv` (Ubuntu/Debian) or equivalent for your OS.

**Q: Browser doesn't start in Docker**  
A: Agent X auto-detects Docker and adds `--no-sandbox`. Ensure your container has `--cap-add=SYS_ADMIN`.

**Q: CAPTCHA solver not working**  
A: Install ddddocr manually: `pip install ddddocr`. Core automation works without it.

**Q: How do I change the stealth level?**  
A: Stealth is adaptive by default. Set `browser.stealth_mode` in config: `adaptive`, `cdp`, or `god`.

**Q: Can I use this on Windows?**  
A: Yes! See the [Windows Installation Guide](#windows-installation) below.

---

## Windows Installation

### Prerequisites

- **Python 3.10+** — Download from [python.org](https://python.org) (check "Add to PATH")
- **Git** — Download from [git-scm.com](https://git-scm.com)
- **Visual C++ Redistributable** — Required for some Python packages

### Step-by-Step

```powershell
# 1. Clone the repository
git clone https://github.com/unknownsorcerer007/Agent-X.git
cd Agent-X

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Chromium browser
python -m patchright install chromium

# 5. First-time setup (generates .env with JWT and token)
python main.py --setup

# 6. Start Agent X
python main.py --agent-token "your-secure-token"
```

### Windows-Specific Notes

| Feature | Status | Notes |
|---------|--------|-------|
| Basic browser automation | ✅ Working | All features functional |
| WebSocket server | ✅ Working | Default port 8000 |
| HTTP REST API | ✅ Working | Default port 8001 |
| Stealth engine | ✅ Working | All 5 layers active |
| Multi-tab | ✅ Working | Full support |
| CAPTCHA solver | ✅ Working | Install ddddocr manually |
| Docker | ✅ Working | Use Docker Desktop |
| Graceful shutdown | ✅ Fixed | SIGINT handler (no SIGTERM on Windows) |
| Signal handling | ✅ Fixed | Cross-platform implementation |

### Common Windows Issues

**Issue: `python` not found**  
Fix: Use `py` instead of `python`, or add Python to PATH during installation.

**Issue: `pip install` fails with C++ compiler errors**  
Fix: Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) or use pre-built wheels with `--prefer-binary`.

**Issue: Chromium install fails**  
Fix: Run `python -m patchright install chromium` in an Administrator PowerShell.

**Issue: Long path errors**  
Fix: Enable long path support: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force`

---

## License

Agent X is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [Patchright](https://github.com/Kaliiiiiiiiii-Vinyas/patchright) — Stealth-enhanced Playwright
- [curl_cffi](https://github.com/yifeikong/curl_cffi) — TLS fingerprint impersonation
- [cloudscraper](https://github.com/VeNoMouS/cloudscraper) — Cloudflare challenge solver
- [Playwright](https://playwright.dev) — Browser automation framework

---

<p align="center">
  <strong>Agent X</strong> — Autonomous AI Browser Engine<br>
  Built with precision. Hardened for real-world usage.<br>
  <a href="https://x.com/Unknown339264">Follow on X</a>
</p>
