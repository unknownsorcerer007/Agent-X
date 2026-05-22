#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Browser Engine v3.0 — One-Command Installer
# Production Anti-Detection Browser with CDP, Smart Modes, State Persistence,
# Enforced Handover, Auto CAPTCHA Detection, Human-like Form Filling,
# AI Content Extraction & Summarization, LLM-powered Agent Swarm
#
# Uses user's connected tool's LLM (z-ai-web-dev-sdk) — no separate LLM needed
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

BROWSER_ENGINE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${CYAN}"
echo "═══════════════════════════════════════════════════════════════════════"
echo "  Browser Engine v3.0 — Installer"
echo "  Production Anti-Detection Browser + AI + Swarm"
echo "═══════════════════════════════════════════════════════════════════════"
echo -e "${NC}"

# ─── Step 1: Check for Bun ─────────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking for Bun runtime...${NC}"
if command -v bun &>/dev/null; then
    BUN_VERSION=$(bun --version)
    echo -e "${GREEN}  ✓ Bun v${BUN_VERSION} found${NC}"
else
    echo -e "${YELLOW}  Bun not found. Installing Bun...${NC}"
    curl -fsSL https://bun.sh/install | bash
    export BUN_INSTALL="$HOME/.bun"
    export PATH="$BUN_INSTALL/bin:$PATH"
    if command -v bun &>/dev/null; then
        BUN_VERSION=$(bun --version)
        echo -e "${GREEN}  ✓ Bun v${BUN_VERSION} installed${NC}"
    else
        echo -e "${RED}  ✗ Failed to install Bun. Please install manually:${NC}"
        echo -e "${RED}    curl -fsSL https://bun.sh/install | bash${NC}"
        exit 1
    fi
fi

# ─── Step 2: Install npm dependencies ──────────────────────────────────────
echo -e "${YELLOW}[2/6] Installing dependencies (including z-ai-web-dev-sdk)...${NC}"
cd "$BROWSER_ENGINE_DIR"
bun install
echo -e "${GREEN}  ✓ Dependencies installed${NC}"

# ─── Step 3: Install Playwright browsers ────────────────────────────────────
echo -e "${YELLOW}[3/6] Installing Playwright Chromium browser...${NC}"
bunx playwright install chromium 2>/dev/null || {
    echo -e "${YELLOW}  Note: Playwright install may need system deps. Run: bunx playwright install-deps${NC}"
    bunx playwright install chromium
}
echo -e "${GREEN}  ✓ Playwright Chromium installed${NC}"

# ─── Step 4: Create state directories ──────────────────────────────────────
echo -e "${YELLOW}[4/6] Creating state directories...${NC}"
mkdir -p "$HOME/.agent-os/browser-states"
mkdir -p "$HOME/.agent-os/chrome-profile"
echo -e "${GREEN}  ✓ State directories created at ~/.agent-os/${NC}"

# ─── Step 5: Create .env configuration ────────────────────────────────────
echo -e "${YELLOW}[5/6] Setting up environment configuration...${NC}"

ENV_FILE="$BROWSER_ENGINE_DIR/.env"
ENV_EXAMPLE="$BROWSER_ENGINE_DIR/.env.example"

cat > "$ENV_EXAMPLE" << 'EOF'
# ═══════════════════════════════════════════════════════════════════════════════
# Browser Engine v3.0 — Environment Configuration
# Copy this file to .env and fill in your values: cp .env.example .env
# ═══════════════════════════════════════════════════════════════════════════════

# Server port (default: 3003)
PORT=3003

# Directory for saved browser states (cookies, localStorage, IndexedDB)
BROWSER_STATES_DIR=

# Chrome remote debugging port (for CDP connection to user's real browser)
# Launch Chrome with: google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.agent-os/chrome-profile"
CDP_PORT=9222

# Twitter/X API bearer token
TWITTER_BEARER_TOKEN=

# Instagram App ID (default: 936619743392459)
IG_APP_ID=

# Instagram Create Post GraphQL doc_id (default: 6511191288958346)
IG_CREATE_POST_DOC_ID=
EOF

echo -e "${GREEN}  ✓ .env.example created${NC}"

if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo -e "${GREEN}  ✓ .env created from .env.example${NC}"
else
    echo -e "${GREEN}  ✓ .env already exists (skipped)${NC}"
fi

# ─── Step 6: Create start script ──────────────────────────────────────────
echo -e "${YELLOW}[6/6] Creating start script...${NC}"

START_SCRIPT="$BROWSER_ENGINE_DIR/start.sh"
cat > "$START_SCRIPT" << 'STARTSH'
#!/usr/bin/env bash
# Start Browser Engine v3.0 server
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ENGINE_DIR"

# Load .env if it exists
if [ -f "$ENGINE_DIR/.env" ]; then
    set -a
    source "$ENGINE_DIR/.env"
    set +a
fi

PORT="${PORT:-3003}"

echo "═══════════════════════════════════════════════════════════════════════"
echo "  Browser Engine v3.0 — Starting on port $PORT"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  AI LLM: Available via z-ai-web-dev-sdk"
echo "  Chrome: google-chrome --remote-debugging-port=9222 --user-data-dir=~/.agent-os/chrome-profile"
echo ""

exec bun run index.ts
STARTSH

chmod +x "$START_SCRIPT"
echo -e "${GREEN}  ✓ start.sh created and made executable${NC}"

# ─── Done! ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════"
echo -e "  ✓ Browser Engine v3.0 installed successfully!"
echo -e "═══════════════════════════════════════════════════════════════════════"
echo ""
echo -e "${CYAN}  Quick Start:${NC}"
echo -e "    ./start.sh                          # Start the server"
echo -e "    curl http://localhost:3003/api/health  # Verify it's running"
echo -e ""
echo -e "${CYAN}  Chrome Setup (for FULL mode + Handover):${NC}"
echo -e "    google-chrome --remote-debugging-port=9222 --user-data-dir=~/.agent-os/chrome-profile"
echo -e ""
echo -e "${CYAN}  AI Features (automatic — uses your connected LLM):${NC}"
echo -e "    curl http://localhost:3003/api/ai/status"
echo -e "    curl -X POST http://localhost:3003/api/ai/summarize -H 'Content-Type: application/json' -d '{\"sessionId\":\"...\"}'"
echo -e "    curl -X POST http://localhost:3003/api/ai/extract -H 'Content-Type: application/json' -d '{\"sessionId\":\"...\",\"schema\":{\"name\":\"string\",\"email\":\"email\"}}'"
echo -e ""
echo -e "${CYAN}  Swarm Search:${NC}"
echo -e "    curl -X POST http://localhost:3003/api/swarm/plan -H 'Content-Type: application/json' -d '{\"query\":\"best laptops 2024\"}'"
echo -e ""
echo -e "${CYAN}  Features:${NC}"
echo -e "    • CDP Connection Module (6 endpoints)"
echo -e "    • Smart Browser Modes (Full/Light/Ghost)"
echo -e "    • Enforced Handover with Auto CAPTCHA Detection"
echo -e "    • Human-like Form Filling + Multi-page Forms"
echo -e "    • AI Content Extraction & Summarization"
echo -e "    • LLM-powered Agent Swarm"
echo -e "    • Dual-Layer State Persistence"
echo -e "    • 20-Point Stealth & Fingerprint"
echo -e "    • Platform Adapters (Instagram, Twitter, LinkedIn, Facebook)"
echo -e ""
