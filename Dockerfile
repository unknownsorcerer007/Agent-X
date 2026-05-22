# Agent-OS — Production Multi-stage Docker Build
# Final image: ~400MB
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN patchright install chromium
RUN patchright install-deps chromium 2>/dev/null || true

# ─── Final Image ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libxfixes3 fonts-liberation \
    && (apt-get install -y --no-install-recommends libasound2t64 2>/dev/null || apt-get install -y --no-install-recommends libasound2 2>/dev/null || true) \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r agentos && useradd -r -g agentos -d /home/agentos -m agentos

COPY --from=builder /root/.cache/ms-playwright /home/agentos/.cache/ms-playwright
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY main.py .
COPY src/ src/
COPY connectors/ connectors/
COPY alembic/ alembic/
COPY alembic.ini .
COPY qwen_bridge.py .

RUN mkdir -p /home/agentos/.agent-os && \
    chown -R agentos:agentos /app /home/agentos

USER agentos

ENV PLAYWRIGHT_BROWSERS_PATH=/home/agentos/.cache/ms-playwright
# Bind to 0.0.0.0 for Docker (not 127.0.0.1)
ENV AGENT_OS_HOST=0.0.0.0
# Signal that we're running inside Docker (browser uses --no-sandbox)
ENV AGENT_OS_DOCKER=1

# Expose ports
# 8000 = WebSocket (agents connect here)
# 8001 = HTTP REST API (curl / any HTTP client)
EXPOSE 8000 8001 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

ENTRYPOINT ["python3", "main.py"]
CMD ["--port", "8000"]
