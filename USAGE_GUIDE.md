# Agent-OS — Usage Guide

## Step 1: Install & Start

### Using Docker (Recommended)
```bash
# Clone the repository
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS

# Start everything (PostgreSQL + Redis + Agent-OS)
docker compose up -d

# Verify it's running
curl http://localhost:8001/health
```

**Output:** `{"status": "healthy", "checks": {...}}`

### Without Docker (Manual)
```bash
git clone https://github.com/factspark23-hash/Agent-OS.git
cd Agent-OS
chmod +x setup.sh && ./setup.sh
python3 main.py --agent-token "your-token-here"
```

---

## Step 2: Verify Installation

```bash
# Health check
curl http://localhost:8001/health

# Status check
curl http://localhost:8001/status
```

---

## Step 3: Start Using It!

### Authentication Setup (For Production)

```bash
# Register a new user
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@example.com",
    "username": "admin",
    "password": "StrongPass123!"
  }'

# Login — you'll receive a JWT token
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "StrongPass123!"
  }'

# Response:
# {
#   "status": "success",
#   "access_token": "eyJhbGciOi...",
#   "refresh_token": "eyJhbGciOi...",
#   "user": {"id": "...", "username": "admin", "plan": "free"}
# }

# Create an API key (using JWT token)
curl -X POST http://localhost:8001/auth/api-keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"name": "my-app-key", "scopes": ["browser", "scanning"]}'
```

---

### Browser Commands (Most Important!)

#### Navigate to any website
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "navigate",
    "url": "https://google.com"
  }'
```

#### Take a screenshot
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"command": "screenshot"}'
```

#### Get page content
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"command": "get-content"}'
```

#### Extract all links
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"command": "get-links"}'
```

#### Click an element
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "click",
    "selector": "button[type=submit]"
  }'
```

#### Fill a form
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "fill-form",
    "fields": {
      "q": "Agent-OS browser automation"
    }
  }'
```

#### Scroll the page
```bash
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "scroll",
    "direction": "down",
    "amount": 500
  }'
```

---

### Using with AI Agents

#### With OpenAI / GPT-4
```python
from connectors.openai_connector import get_tools, call_tool

# Get tool definitions
tools = get_tools("openai")  # For GPT-4 function calling

# Execute tools
result = await call_tool("browser_navigate", {"url": "https://github.com"})
result = await call_tool("browser_screenshot", {})
result = await call_tool("browser_click", {"selector": "a[href='/login']"})
```

#### With Claude / MCP
```json
// Add to Claude Desktop config
{
  "mcpServers": {
    "agent-os": {
      "command": "python3",
      "args": ["/path/to/Agent-OS/connectors/mcp_server.py"],
      "env": {
        "AGENT_OS_URL": "http://localhost:8001",
        "AGENT_OS_TOKEN": "your-token"
      }
    }
  }
}
```

#### From CLI (Bash/Python/Node/Any Language)
```bash
./connectors/agent-os-tool.sh navigate "https://github.com"
./connectors/agent-os-tool.sh screenshot
./connectors/agent-os-tool.sh get-content
```

---

### Login & Credential Management

```bash
# Save credentials for a site (AES-256 encrypted)
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "save-creds",
    "domain": "github.com",
    "username": "you@example.com",
    "password": "your-password"
  }'

# Auto-login later
curl -X POST http://localhost:8001/command \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "command": "auto-login",
    "url": "https://github.com/login",
    "domain": "github.com"
  }'
```

---

### Real-World Examples

#### Example 1: List repositories from a GitHub profile
```bash
# Navigate to profile
curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{"command": "navigate", "url": "https://github.com/factspark23-hash"}'

# Get the content
curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{"command": "get-content"}'
```

#### Example 2: Search for a product on Amazon
```bash
curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{"command": "navigate", "url": "https://amazon.com"}'

curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{"command": "fill-form", "fields": {"field-keywords": "MacBook Pro"}}'

curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{"command": "click", "selector": "input[type=submit]"}'
```

#### Example 3: Multi-step workflow in a single command
```bash
curl -X POST http://localhost:8001/command \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "command": "workflow",
    "steps": [
      {"command": "navigate", "url": "https://example.com/login"},
      {"command": "fill-form", "fields": {"email": "test@test.com", "password": "pass123"}},
      {"command": "click", "selector": "button[type=submit]"},
      {"command": "wait", "selector": ".dashboard"},
      {"command": "screenshot"}
    ]
  }'
```

---

## All Commands Reference

| Category | Commands |
|----------|----------|
| **Navigation** | `navigate`, `back`, `forward`, `reload`, `smart-navigate` |
| **Click/Type** | `click`, `type`, `press`, `hover`, `double-click`, `right-click` |
| **Content** | `get-content`, `get-dom`, `get-links`, `get-images`, `get-text`, `screenshot` |
| **Forms** | `fill-form`, `fill-job`, `select`, `checkbox`, `upload`, `clear-input` |
| **Scroll** | `scroll` (up/down/left/right) |
| **Auth** | `save-creds`, `auto-login`, `get-cookies`, `set-cookie` |
| **Tabs** | `tabs` (list/new/switch/close) |
| **Smart** | `smart-click`, `smart-fill`, `smart-find`, `smart-find-all`, `smart-wait` |
| **Workflow** | `workflow`, `workflow-save`, `workflow-template`, `workflow-list` |
| **Network** | `network-start`, `network-stop`, `network-get`, `network-apis`, `network-stats` |
| **Security** | `scan-xss`, `scan-sqli`, `scan-sensitive` |
| **Recording** | `record-start`, `record-stop`, `replay-play` |
| **Multi-Agent** | `hub-register`, `hub-task-create`, `hub-broadcast` |
| **Proxy** | `set-proxy`, `get-proxy`, `proxy-add`, `proxy-list`, `proxy-stats` |
| **Media** | `transcribe` |
| **Sessions** | `save-session`, `restore-session`, `list-sessions`, `delete-session` |
| **Analysis** | `page-summary`, `page-tables`, `page-seo`, `page-structured`, `page-emails` |

---

## Production Deployment

```bash
# Full stack deploy (PostgreSQL + Redis + Agent-OS + Nginx)
docker compose --profile with-nginx up -d

# Set environment variables
export JWT_SECRET_KEY="your-super-secret-key-here"
export POSTGRES_PASSWORD="strong-db-password"

# View logs
docker compose logs -f agent-os
```

---

## Important Notes

1. **Run locally or behind a firewall** — This is a local server. Do not expose it to the internet without Nginx/SSL.
2. **Keep your tokens secure** — Legacy tokens provide browser-only access. Use JWT authentication for production.
3. **CORS** — Cross-origin requests are blocked by default. Add your domain to `server.cors_allowed_origins` in the config.
4. **RAM** — ~500MB idle, ~800MB under load. More tabs = more RAM. Use `--max-ram` to set limits.

---

_Built with dedication by the Agent-OS team_
