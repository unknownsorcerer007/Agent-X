# Agent-OS MCP Passthrough Wrapper

<p align="center">
  <strong>Zero-API-key MCP server for Agent-OS. 207 browser tools + 87% token savings.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/API_Key-Not_Required-brightgreen.svg" alt="No API Key" />
  <img src="https://img.shields.io/badge/tools-207-brightgreen.svg" alt="207 Tools" />
  <img src="https://img.shields.io/badge/token_savings-87%25-blue.svg" alt="87% Token Savings" />
  <img src="https://img.shields.io/badge/MCP-1.0-purple.svg" alt="MCP 1.0" />
</p>

---

## What Is This?

A standalone MCP server that gives Claude Desktop, Cursor, Codex, and any MCP client access to **207 browser automation tools** — without requiring any LLM API key.

```text
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  MCP Client      │     │  MCP Passthrough │     │  Agent-OS Server │
│  (Claude/GPT)    │────▶│  (This wrapper)  │────▶│  (Browser engine)│
│                  │     │                  │     │                  │
│  • Reasoning     │     │  • 207 tools     │     │  • Chromium      │
│  • Tool selection│     │  • Compression   │     │  • Stealth       │
│  • Already paid  │     │  • LLM fallback  │     │  • Anti-detect   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

**Your MCP client's LLM handles reasoning. Agent-OS handles execution. No extra cost.**

---

## Why Use This?

| Problem | Solution |
|---------|----------|
| Agent-OS needs an API key for LLM tools | BuiltinLLM — rule-based, zero API calls |
| Browser results burn 10k+ tokens per page | SmartCompressor — 87% token savings |
| Setting up MCP is complicated | One command: `.\run_mcp.ps1` or `./run_mcp.sh` |
| Server down = everything crashes | Graceful errors, LLM tools work standalone |

---

## Quick Start

### 🪟 Windows

1. Run the one-click installer first if you haven't: `.\install.ps1`
2. Add the following to your Claude Desktop config file (`%APPDATA%\Claude\claude_desktop_config.json`):

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

### 🍎 Mac / 🐧 Linux

1. Run the installer: `bash install.sh`
2. Add the following to your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` or `~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agent-os": {
      "command": "bash",
      "args": ["/absolute/path/to/Agent-OS/run_mcp.sh"]
    }
  }
}
```

Restart Claude Desktop. **207 tools will appear automatically.**

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_OS_URL` | `http://localhost:8001` | Agent-OS server URL |
| `AGENT_OS_TOKEN` | (auto-generated) | Auth token (must match server) |
| `AGENT_OS_COMPRESS` | `aggressive` | Compression mode: `aggressive`, `normal`, `off` |
| `AGENT_OS_MAX_OUTPUT` | `8000` | Max chars returned per tool call |

### Compression Modes

| Mode | Token Savings | Best For |
|------|---------------|----------|
| `aggressive` | ~85% | Production — most use cases |
| `normal` | ~50% | When you need more detail |
| `off` | 0% | Debugging |

---

## How It Works

### Architecture

```text
MCP Client (Claude/GPT)
    │
    │  1. Client asks: "Browse github.com and summarize trending repos"
    │
    ▼
MCP Passthrough
    │
    │  2. LLM tools → BuiltinLLM (rule-based, no API)
    │  3. Browser tools → proxy to Agent-OS server
    │  4. Results → SmartCompressor (strip HTML, dedupe, cap)
    │
    ▼
Agent-OS Server
    │
    │  5. Navigate, extract, screenshot
    │
    ▼
MCP Client
    │
    │  6. Compressed results (~2k tokens instead of ~50k)
    │
    ▼
User sees clean answer
```

### Token Savings — Real Numbers

```text
Single page visit:
  Before:  50,000 chars HTML = ~12,500 tokens  💸
  After:    3,000 chars text = ~750 tokens     ✅
  Saved:   94%

3-page research task:
  Before:  44,361 tokens 💸
  After:    5,681 tokens ✅
  Saved:   87%
```

### BuiltinLLM — No API Key Needed

When LLM tools are called, they use a built-in rule-based engine:

| Tool | Method | Quality |
|------|--------|---------|
| `llm-classify` | Keyword + semantic matching | Good for common categories |
| `llm-extract` | Regex-based extraction | Works for emails, phones, URLs, dates |
| `llm-summarize` | Extractive summarization | Keeps key sentences |
| `llm-complete` | Intent detection + tool suggestion | Contextual analysis |

Quality is lower than a real LLM but keeps all tools functional without any API dependency.

### SmartCompressor — Token Saver

Every tool result is compressed before returning to the MCP client:

1. **Strip HTML tags** — removes `<script>`, `<style>`, `<nav>`, `<footer>`
2. **Remove boilerplate** — cookie banners, copyright notices, duplicate lines
3. **Deduplicate content** — removes repeated lines across page sections
4. **Cap output per tool** — different limits for different tool types
5. **Replace screenshots** — base64 data → placeholder text
6. **Hard cap** — configurable max chars (default 8000)

---

## Troubleshooting

### "Cannot connect to Agent-OS server"

```bash
# Start the server manually
python main.py --agent-token "your-token"

# Check it's running
curl http://localhost:8001/health
```

### Tools not appearing in Claude Desktop

1. Check the absolute path in config (not relative)
2. Make sure PowerShell / bash has execution rights
3. Restart Claude Desktop completely (quit + reopen)
4. Check Claude Desktop logs for errors

### Results too compressed

```json
{
  "env": {
    "AGENT_OS_COMPRESS": "normal",
    "AGENT_OS_MAX_OUTPUT": "15000"
  }
}
```

---

## License

[MIT License](LICENSE) — same as Agent-OS.
