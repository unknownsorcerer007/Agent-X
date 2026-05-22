<!-- mcp-name: io.github.factspark23-hash/Agent-OS -->

<h1 align="center">
    <a href="https://github.com/factspark23-hash/Agent-OS">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="docs/cover_dark.svg">
          <img alt="Agent-OS" src="docs/cover_light.svg" width="700">
        </picture>
    </a>
    <br>
</h1>

<p align="center">
    <a href="https://opensource.org/licenses/MIT">
        <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT" />
    </a>
    <a href="https://www.python.org/downloads/">
        <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+" />
    </a>
    <a href="https://www.docker.com/">
        <img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg" alt="Docker Ready" />
    </a>
    <img src="https://img.shields.io/badge/tools-207-brightgreen.svg" alt="207 Tools" />
    <img src="https://img.shields.io/badge/version-3.2.0-orange.svg" alt="Version 3.2.0" />
    <br/>
    <a href="https://github.com/factspark23-hash/Agent-OS/stargazers">
        <img src="https://img.shields.io/github/stars/factspark23-hash/Agent-OS?style=social" alt="Stars" />
    </a>
    <a href="https://github.com/factspark23-hash/Agent-OS/network/members">
        <img src="https://img.shields.io/github/forks/factspark23-hash/Agent-OS?style=social" alt="Forks" />
    </a>
</p>

<p align="center">
    <a href="#-quick-start"><strong>Quick Start</strong></a> &middot;
    <a href="#-connectors"><strong>Connectors</strong></a> &middot;
    <a href="#-stealth-engine"><strong>Stealth</strong></a> &middot;
    <a href="#-adaptive-scraper"><strong>Adaptive</strong></a> &middot;
    <a href="#-bot-detection-tests"><strong>Verify Stealth</strong></a> &middot;
    <a href="#-architecture"><strong>Architecture</strong></a> &middot;
    <a href="#-deployment"><strong>Deployment</strong></a>
</p>

---

Agent-OS gives AI agents a **real browser** — persistent, stealthy, and self-hosted. It ships **207 tools** for navigation, form filling, data extraction, CAPTCHA bypass, adaptive scraping, and more. Works with **Claude, Cursor, GPT-4, Codex, OpenClaw**, and any agent that can send an HTTP request.

One command to install. One config to connect. Zero API keys needed.

---

## Why Agent-OS?

| Problem | Agent-OS Solution |
|---------|-------------------|
| AI agents can't interact with websites | Real Chromium browser with 207 tools |
| Bot detection blocks automation | 26+ anti-detection vectors, Cloudflare bypass |
| Website changes break selectors | **Adaptive scraper** — learns element fingerprints, auto-relocates |
| Manual login required | Login handoff — pause AI, human logs in, resume |
| Single IP gets blocked | Proxy rotation with 4 strategies + health tracking |
| LLM token waste on browser output | SmartCompressor — 87% token savings |
| Need multiple AI platforms | 7 connectors — MCP, OpenAI, Claude, CLI, REST, OpenClaw |

---

## ⚡ Quick Start

### 🪟 Windows (One-Click)

```powershell
# Open PowerShell and run:
.\install.ps1

# To start the server:
.\start.ps1
```

### 🍎 Mac / 🐧 Linux (One-Click)

```bash
# Open Terminal and run:
curl -sSL https://raw.githubusercontent.com/factspark23-hash/Agent-OS/main/install.sh | bash

# To start the server:
python3 main.py --agent-token "dev-token"
```

### 🐳 Docker

```bash
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS
export POSTGRES_PASSWORD="strong-password"
docker compose up -d
```

---

## 🧪 Bot Detection Tests (Verify Stealth)

Don't trust our words, test it yourself! We've included a standalone script that runs our stealth engine against the internet's toughest bot detectors.

```bash
# Run this to verify a 100% bypass success rate:
python run_stealth_tests.py
```
This tests against:
1. **Sannysoft** (Standard Webdriver/CDP checks)
2. **Cloudflare / NowSecure** (Advanced CDN Challenges)
3. **CreepJS** (Deep WebGL/Canvas Fingerprinting & Trust Score)

*(Note: On Windows, ensure Windows Defender Firewall allows the newly downloaded headless `chrome.exe` to access the internet.)*

---

## 🔌 Connectors

All 207 tools are available in every connector:

| Connector | Tools | Use With | API Key? |
|-----------|-------|----------|----------|
| **MCP Passthrough** ⭐ | 207 | Claude Desktop, Cursor, Codex | ❌ No |
| MCP Server | 207 | Claude Desktop, Claude Code, Codex | Optional |
| OpenAI | 207 | GPT-4, GPT-4o, any OpenAI-compatible | Yes |
| Claude API | 207 | Claude API (tool-use format) | Yes |
| OpenClaw | 207 | OpenClaw agent framework | Optional |
| CLI (Bash) | 206 | Any language (Python, Node, Go...) | Token |
| HTTP REST | 206 | Direct API calls | Token |

### MCP Passthrough (Zero API Key) ⭐

**Claude Desktop config:**
```json
{
  "mcpServers": {
    "agent-os": {
      "command": "powershell",
      "args": ["-ExecutionPolicy", "Bypass", "-File", "C:/absolute/path/to/Agent-OS/run_mcp.ps1"]
    }
  }
}
```
*(For Mac/Linux, use `bash` and `run_mcp.sh`)*

---

## 🛡️ Stealth Engine

Agent-OS defeats bot detection with a **4-layer defense system**:

```text
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Network                                         │
│ Chrome TLS fingerprint (JA3/JA4) via curl_cffi          │
│ HTTP/2 matching • Bot scripts blocked at network level   │
├─────────────────────────────────────────────────────────┤
│ Layer 2: CDP (Chrome DevTools Protocol)                  │
│ Page.addScriptToEvaluateOnNewDocument injection          │
│ User-Agent metadata spoofing • Timezone override         │
├─────────────────────────────────────────────────────────┤
│ Layer 3: JavaScript (19 injection modules)               │
│ navigator.webdriver removal • CDP property filtering     │
│ WebGL/Canvas/Audio fingerprint spoofing                  │
│ WebRTC IP leak prevention • Function toString masking    │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Behavior                                        │
│ Bezier-curve mouse movements • Realistic typing rhythms  │
│ Word pause simulation • Typo + correction (3% rate)      │
└─────────────────────────────────────────────────────────┘
```

**Blocked vendors:** DataDome, PerimeterX, Imperva, Akamai, Cloudflare Bot Management, Turnstile, Kasada, Shape Security, F5, Arkose Labs, ThreatMetrix, hCaptcha, reCAPTCHA

---

## 🧠 Adaptive Scraper

When a website changes its DOM structure, traditional selectors break. Agent-OS **remembers** element fingerprints and **relocates** them automatically:

```text
1. Find element with CSS selector → ✅ Found → Save fingerprint (tag, attrs, text, path, parent)
2. Website redesigns, selector breaks → ❌ Not found
3. Load stored fingerprint → Scan all page elements → Score similarity
4. Best match above 40% threshold → ✅ Element relocated!
```

---

## 🔄 Proxy Rotation

Thread-safe proxy rotator with **4 strategies**:

| Strategy | How it works | Best for |
|----------|-------------|----------|
| **Cyclic** | Sequential round-robin | General scraping |
| **Weighted** | Higher weight = more requests | Premium vs budget proxies |
| **Random** | Random selection | Anti-pattern detection |
| **Sticky** | Same proxy per domain | Session-based scraping |

---

## 🌐 Browser Automation

**207 tools** across 15 categories:

| Category | Tools | Highlights |
|----------|-------|------------|
| Navigation | 6 | `navigate`, `smart-navigate` (auto HTTP/browser) |
| Interaction | 17 | `click`, `fill-form`, `drag-drop`, `scroll` |
| Content | 9 | `screenshot`, `get-dom`, `evaluate-js` |
| Workflows | 6 | Multi-step automation with variables |
| Proxy | 18 | Pool management, health checks, rotation |
| Adaptive | 4 | Element fingerprinting + relocation |
| Multi-Agent | 19 | Shared sessions, task queues, locks |
| Login Handoff | 8 | Pause AI → human logs in → resume |
| LLM | 7 | Built-in `llm-complete`, `llm-summarize` |

---

## 🤝 Contributing

```bash
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 -m patchright install chromium

# Run tests
python3 -m pytest tests/ -v
```

---

## 📄 License

[MIT License](LICENSE) — free for commercial and personal use.

### Third-Party Code

- **[Scrapling](https://github.com/D4Vinci/Scrapling)** by Karim Shoair — Adaptive scraping algorithm and proxy rotation engine. Used under [BSD 3-Clause License](THIRD_PARTY_LICENSES.md).