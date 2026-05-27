<p align="center">
  <img src="docs/agent_x_logo.png" width="180" alt="Agent X Logo">
</p>

<h1 align="center">Agent X</h1>
<p align="center"><strong>Autonomous AI Browser Engine — Production Ready</strong></p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/version-4.0.0-blue.svg?style=flat-square" alt="Version 4.0.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=flat-square" alt="Docker Ready"></a>
  <img src="https://img.shields.io/badge/tools-209-brightgreen.svg?style=flat-square" alt="209 Tools">
  <br/>
  <img src="https://img.shields.io/badge/stealth-99%25-success.svg?style=flat-square" alt="Stealth 99%">
  <img src="https://img.shields.io/badge/captcha-solver-orange.svg?style=flat-square" alt="CAPTCHA Solver">
  <img src="https://img.shields.io/badge/swarm-enabled-purple.svg?style=flat-square" alt="Swarm Enabled">
</p>

---

## What is Agent X?

**Agent X** is the next-generation autonomous browser engine that gives AI agents a **real, persistent, and self-hosted web browser** with zero-friction installation. Built on top of the legendary Agent-OS codebase, completely rewritten and hardened for production.

It exposes **209 production-ready tools** for mouse interactions, form filling, data extraction, CAPTCHA bypass, and session persistence. Agent X turns your LLM (Claude Code, Cursor, GPT-4o, Claude Desktop, or custom agents) into an autonomous web operator that can navigate complex sites, bypass CDNs, and complete multi-step workflows.

### What's New in v4.0.0

- **Zero-Dependency Fallbacks**: Works even with missing packages — graceful degradation
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
curl -sSL https://raw.githubusercontent.com/yourusername/agent-x/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/yourusername/agent-x/main/install.ps1 | iex
```

### Docker

```bash
git clone https://github.com/yourusername/agent-x.git
cd agent-x
export POSTGRES_PASSWORD="your-strong-password"
docker compose up -d
```

### Manual Install

```bash
# Clone the repository
git clone https://github.com/yourusername/agent-x.git
cd agent-x

# Install dependencies
pip install -r requirements.txt

# Install browser engine
python -m playwright install chromium

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
| **209 Tools** | Complete browser automation toolkit | Production Ready |
| **Stealth Engine** | 5-layer anti-detection system | 99% Bypass Rate |
| **Smart Navigator** | Auto HTTP/browser strategy selection | Production Ready |
| **CAPTCHA Solver** | OCR + AI challenge solving | Production Ready |
| **Agent Swarm** | Multi-agent orchestration | Production Ready |
| **Session Manager** | Encrypted cookie persistence | Production Ready |
| **Proxy Rotation** | Residential/mobile/datacenter | Production Ready |
| **Cloudflare Bypass** | v1/v2/v3 + Turnstile support | Production Ready |
| **JWT Auth** | Production-grade authentication | Production Ready |
| **API Keys** | Scoped permissions + rate limits | Production Ready |
| **Docker Deploy** | One-command production deploy | Production Ready |

---

## Connectors

Agent X supports multiple connector pipelines:

- **MCP (Model Context Protocol)**: Claude Desktop, Cursor integration
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
  Built with precision. Hardened for production. Ready to deploy.
</p>
