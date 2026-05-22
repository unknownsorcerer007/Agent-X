#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Agent-OS — ONE COMMAND INSTALL + AUTO-CONNECT
# ═══════════════════════════════════════════════════════════════
#
# Install + start + auto-configure MCP for Claude Code, Codex, OpenClaw
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/factspark23-hash/Agent-OS/main/quickstart.sh | bash
#
# What happens:
#   1. Downloads Agent-OS (no git needed)
#   2. Installs Python deps + Chromium
#   3. Generates JWT secret + agent token
#   4. Creates .env config
#   5. Starts server
#   6. Auto-detects Claude Code / Codex / OpenClaw → configures MCP
#   7. Prints ready-to-use connection info
# ═══════════════════════════════════════════════════════════════
set -e

# ─── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

step()  { echo -e "${BLUE}▸${NC} $1"; }
ok()    { echo -e "${GREEN}  ✓${NC} $1"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $1"; }
fail()  { echo -e "${RED}  ✗${NC} $1"; exit 1; }

# ─── Config ──────────────────────────────────────────────
INSTALL_DIR="${AGENT_OS_DIR:-$HOME/.agent-os-server}"
REPO_URL="https://github.com/factspark23-hash/Agent-OS"
WS_PORT="${WS_PORT:-8000}"
HTTP_PORT="${HTTP_PORT:-8001}"

# ─── Parse Args ──────────────────────────────────────────
CUSTOM_TOKEN="" HEADLESS=true EXTRA_ARGS="" NO_START=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)       INSTALL_DIR="$2"; shift 2 ;;
        --headed)    HEADLESS=false; EXTRA_ARGS="$EXTRA_ARGS --headed"; shift ;;
        --port)      WS_PORT="$2"; HTTP_PORT=$((WS_PORT+1)); shift 2 ;;
        --token)     CUSTOM_TOKEN="$2"; shift 2 ;;
        --no-start)  NO_START=true; shift ;;
        --help|-h)
            echo -e "${BOLD}Agent-OS Quick Start${NC}"
            echo "  ./quickstart.sh [--dir PATH] [--token TOKEN] [--headed] [--port PORT] [--no-start]"
            exit 0 ;;
        *) shift ;;
    esac
done

# ─── Secret Generators ───────────────────────────────────
gen_secret() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || head -c 48 /dev/urandom | base64 | tr -d '/+=' | head -c 64; }
gen_token()  { python3 -c 'import secrets; print("aos-" + secrets.token_hex(16))' 2>/dev/null || echo "aos-$(head -c 16 /dev/urandom | xxd -p)"; }

# ─── Banner ──────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}    ${GREEN}${BOLD}🤖 Agent-OS — One Command Setup${NC}           ${CYAN}║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# ─── Step 1: Python ──────────────────────────────────────
step "Checking Python..."
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd > /dev/null 2>&1; then
        VER=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        MAJOR=${VER%%.*}; MINOR=${VER##*.}
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON=$cmd; ok "Python $VER"; break
        fi
    fi
done
[ -z "$PYTHON" ] && fail "Python 3.10+ required"

# ─── Step 2: Download (NO GIT NEEDED) ───────────────────
step "Downloading Agent-OS..."
mkdir -p "$INSTALL_DIR"

# Download as tarball — no git required
DOWNLOAD_OK=false
for url in \
    "${REPO_URL}/archive/refs/heads/main.tar.gz" \
    "${REPO_URL}/archive/main.tar.gz"; do
    if curl -sSL "$url" -o /tmp/agent-os.tar.gz 2>/dev/null; then
        tar -xzf /tmp/agent-os.tar.gz -C /tmp/ 2>/dev/null
        # Move contents (strip top-level folder)
        cp -r /tmp/Agent-OS-main/* "$INSTALL_DIR/" 2>/dev/null || cp -r /tmp/Agent-OS-*/ "$INSTALL_DIR/" 2>/dev/null
        rm -rf /tmp/Agent-OS-main /tmp/Agent-OS-* /tmp/agent-os.tar.gz
        DOWNLOAD_OK=true
        break
    fi
done

if ! $DOWNLOAD_OK; then
    # Fallback: try wget
    if command -v wget > /dev/null 2>&1; then
        wget -q "${REPO_URL}/archive/refs/heads/main.tar.gz" -O /tmp/agent-os.tar.gz
        tar -xzf /tmp/agent-os.tar.gz -C /tmp/
        cp -r /tmp/Agent-OS-main/* "$INSTALL_DIR/" 2>/dev/null || cp -r /tmp/Agent-OS-*/"$INSTALL_DIR/" 2>/dev/null
        rm -rf /tmp/Agent-OS-* /tmp/agent-os.tar.gz
        DOWNLOAD_OK=true
    fi
fi

if ! $DOWNLOAD_OK; then
    # Last resort: git (if available)
    if command -v git > /dev/null 2>&1; then
        [ -d "$INSTALL_DIR/.git" ] && cd "$INSTALL_DIR" && git pull --quiet || git clone --quiet "$REPO_URL" "$INSTALL_DIR"
        DOWNLOAD_OK=true
    fi
fi

$DOWNLOAD_OK || fail "Cannot download Agent-OS. Check internet connection."
ok "Downloaded to $INSTALL_DIR"
cd "$INSTALL_DIR"

# ─── Step 3: Virtual Environment + Deps ─────────────────
step "Setting up dependencies..."

# Create venv
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv 2>/dev/null || {
        # Fallback for systems without ensurepip
        $PYTHON -m venv --without-pip venv 2>/dev/null
        source venv/bin/activate
        curl -sS https://bootstrap.pypa.io/get-pip.py | python 2>/dev/null || true
    }
fi
source venv/bin/activate 2>/dev/null || source venv/bin/activate
ok "Virtual environment ready"

# Install system deps (Linux only)
if command -v apt-get > /dev/null 2>&1; then
    MISSING=""
    for lib in libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2; do
        dpkg -l "$lib" 2>/dev/null | grep -q "^ii" || dpkg -l "${lib}t64" 2>/dev/null | grep -q "^ii" || MISSING="$MISSING $lib"
    done
    if [ -n "$MISSING" ]; then
        if command -v sudo > /dev/null 2>&1; then
            sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y -qq $MISSING 2>/dev/null || true
        fi
    fi
fi

# Install Python packages
pip install --upgrade pip -q 2>&1 | tail -1
REQ="requirements.lock"; [ ! -f "$REQ" ] && REQ="requirements.txt"
pip install -r "$REQ" --no-cache-dir 2>&1 | tail -3 || pip install -r "$REQ" --no-build-isolation 2>&1 | tail -3 || true
ok "Python packages installed"

# Install Chromium
$PYTHON -m patchright install chromium 2>/dev/null || $PYTHON -m playwright install chromium 2>/dev/null || warn "Chromium install skipped"
ok "Chromium ready"

# ─── Step 4: Generate Secrets + Config ──────────────────
step "Generating configuration..."

JWT_SECRET=$(gen_secret)
AGENT_TOKEN="${CUSTOM_TOKEN:-$(gen_token)}"

# Detect PostgreSQL
PG_DSN=""
if command -v psql > /dev/null 2>&1; then
    PG_PASS=$(gen_secret | head -c 24)
    PG_DSN="postgresql+asyncpg://agent_os:${PG_PASS}@localhost:5432/agent_os"
    sudo -u postgres psql -c "CREATE USER agent_os WITH PASSWORD '${PG_PASS}';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE agent_os OWNER agent_os;" 2>/dev/null || true
fi

# Detect Redis
REDIS_URL=""
command -v redis-cli > /dev/null 2>&1 && redis-cli ping > /dev/null 2>&1 && REDIS_URL="redis://localhost:6379/0"

# Write .env
cat > .env << EOF
JWT_SECRET_KEY=${JWT_SECRET}
AGENT_TOKEN=${AGENT_TOKEN}
WS_PORT=${WS_PORT}
HTTP_PORT=${HTTP_PORT}
DATABASE_DSN=${PG_DSN}
REDIS_URL=${REDIS_URL}
EOF

# Write config.yaml
mkdir -p ~/.agent-os
cat > ~/.agent-os/config.yaml << EOF
server:
  host: 127.0.0.1
  ws_port: ${WS_PORT}
  http_port: ${HTTP_PORT}
  agent_token: ${AGENT_TOKEN}
jwt:
  secret_key: ${JWT_SECRET}
security:
  enable_jwt_auth: true
  enable_api_key_auth: true
browser:
  headless: true
  max_ram_mb: 500
EOF

ok "Config created"

# ─── Step 5: Create Start/Stop Scripts ──────────────────
cat > start.sh << 'SOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f venv/bin/activate ] && source venv/bin/activate
export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null
exec python3 main.py --agent-token "${AGENT_TOKEN}" --port "${WS_PORT:-8000}" "$@"
SOF
chmod +x start.sh

cat > stop.sh << 'EOF'
#!/usr/bin/env bash
pkill -f "python3 main.py" 2>/dev/null && echo "✓ Stopped" || echo "Not running"
EOF
chmod +x stop.sh

ok "start.sh + stop.sh created"

# ─── Step 6: Start Server ───────────────────────────────
if $NO_START; then
    warn "Server not started (--no-start). Run: ./start.sh"
else
    step "Starting server..."
    pkill -f "python3 main.py" 2>/dev/null || true
    sleep 1
    export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null
    nohup python3 main.py --agent-token "$AGENT_TOKEN" --port "$WS_PORT" > agent-os.log 2>&1 &

    echo -n "  Waiting"
    for i in $(seq 1 20); do
        sleep 1; echo -n "."
        if curl -s "http://127.0.0.1:${HTTP_PORT}/health" > /dev/null 2>&1; then
            echo ""; ok "Server running!"; break
        fi
    done
fi

# ─── Step 7: Auto-Configure MCP Connections ─────────────
step "Configuring MCP connections..."

MCP_CONFIGURED=0

# --- Claude Code (global config) ---
CLAUDE_CONFIG="$HOME/.claude/claude_desktop_config.json"
if [ -d "$HOME/.claude" ] || command -v claude > /dev/null 2>&1; then
    mkdir -p "$(dirname "$CLAUDE_CONFIG")"
    if [ -f "$CLAUDE_CONFIG" ]; then
        # Merge into existing config
        $PYTHON -c "
import json, sys
try:
    with open('$CLAUDE_CONFIG') as f: cfg = json.load(f)
except: cfg = {}
if 'mcpServers' not in cfg: cfg['mcpServers'] = {}
cfg['mcpServers']['agent-os'] = {
    'command': '$(which python3)',
    'args': ['$INSTALL_DIR/connectors/mcp_server.py'],
    'env': {
        'AGENT_OS_URL': 'http://127.0.0.1:${HTTP_PORT}',
        'AGENT_OS_TOKEN': '${AGENT_TOKEN}'
    }
}
with open('$CLAUDE_CONFIG', 'w') as f: json.dump(cfg, f, indent=2)
print('ok')
" 2>/dev/null && ok "Claude Code MCP configured" && MCP_CONFIGURED=$((MCP_CONFIGURED+1))
    else
        cat > "$CLAUDE_CONFIG" << MCPEOF
{
  "mcpServers": {
    "agent-os": {
      "command": "$(which python3)",
      "args": ["$INSTALL_DIR/connectors/mcp_server.py"],
      "env": {
        "AGENT_OS_URL": "http://127.0.0.1:${HTTP_PORT}",
        "AGENT_OS_TOKEN": "${AGENT_TOKEN}"
      }
    }
  }
}
MCPEOF
        ok "Claude Code MCP configured" && MCP_CONFIGURED=$((MCP_CONFIGURED+1))
    fi
fi

# --- OpenClaw config ---
OPENCLAW_DIR="$HOME/.openclaw"
if [ -d "$OPENCLAW_DIR" ]; then
    mkdir -p "$OPENCLAW_DIR/skills"
    cat > "$OPENCLAW_DIR/skills/agent-os.json" << OCEOF
{
  "name": "agent-os",
  "description": "Agent-OS stealth browser automation",
  "url": "http://127.0.0.1:${HTTP_PORT}",
  "token": "${AGENT_TOKEN}",
  "commands": ["navigate", "click", "screenshot", "fill-form", "smart-click", "evaluate-js"]
}
OCEOF
    ok "OpenClaw configured" && MCP_CONFIGURED=$((MCP_CONFIGURED+1))
fi

# --- Codex / OpenAI ---
CODEX_CONFIG="$HOME/.codex/config.toml"
if [ -d "$HOME/.codex" ] || command -v codex > /dev/null 2>&1; then
    mkdir -p "$(dirname "$CODEX_CONFIG")"
    if ! grep -q "agent-os" "$CODEX_CONFIG" 2>/dev/null; then
        cat >> "$CODEX_CONFIG" << CODEXEOF

# Agent-OS MCP Server (auto-configured by quickstart.sh)
[mcp_servers.agent-os]
command = "$(which python3)"
args = ["$INSTALL_DIR/connectors/mcp_server.py"]
env = { AGENT_OS_URL = "http://127.0.0.1:${HTTP_PORT}", AGENT_OS_TOKEN = "${AGENT_TOKEN}" }
CODEXEOF
        ok "Codex MCP configured" && MCP_CONFIGURED=$((MCP_CONFIGURED+1))
    fi
fi

if [ "$MCP_CONFIGURED" -eq 0 ]; then
    warn "No MCP tools detected (Claude Code / Codex / OpenClaw)"
    warn "Install one, then the config will be auto-applied on next run"
fi

# ─── Done! ───────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}       ${GREEN}${BOLD}✅ Agent-OS Ready!${NC}                   ${CYAN}║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Server:${NC}"
echo -e "    API:       ${CYAN}http://127.0.0.1:${HTTP_PORT}${NC}"
echo -e "    Health:    ${CYAN}http://127.0.0.1:${HTTP_PORT}/health${NC}"
echo -e "    Token:     ${GREEN}${AGENT_TOKEN}${NC}"
echo ""
echo -e "  ${BOLD}Connect:${NC}"
echo -e "    ${YELLOW}Claude Code:${NC}  Restart Claude Code → Agent-OS auto-connected"
echo -e "    ${YELLOW}Codex:${NC}       Restart Codex → Agent-OS auto-connected"
echo -e "    ${YELLOW}OpenClaw:${NC}    Restart OpenClaw → Agent-OS auto-connected"
echo ""
echo -e "  ${BOLD}Or use directly:${NC}"
echo -e "    ${CYAN}curl -X POST http://127.0.0.1:${HTTP_PORT}/command \\${NC}"
echo -e "    ${CYAN}  -H 'Content-Type: application/json' \\${NC}"
echo -e "    ${CYAN}  -d '{\"token\":\"${AGENT_TOKEN}\",\"command\":\"navigate\",\"url\":\"https://google.com\"}'${NC}"
echo ""
echo -e "  ${BOLD}Manage:${NC}"
echo -e "    Start:   ${CYAN}cd $INSTALL_DIR && ./start.sh${NC}"
echo -e "    Stop:    ${CYAN}cd $INSTALL_DIR && ./stop.sh${NC}"
echo -e "    Logs:    ${CYAN}tail -f $INSTALL_DIR/agent-os.log${NC}"
echo ""
