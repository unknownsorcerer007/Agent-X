/**
 * Agent-OS Debug UI — Client Application
 * Real-time dashboard with WebSocket streaming, command execution,
 * session management, and live browser view.
 */

(function () {
    "use strict";

    // ─── State ───────────────────────────────────────────────

    const state = {
        ws: null,
        wsConnected: false,
        reconnectTimer: null,
        currentPanel: "browser",
        agentToken: "",
        commandHistory: [],
        consoleLogs: [],
        screenshotData: null,
        activeHandoffs: [],
        handoffTimerInterval: null,
    };

    // ─── DOM References ──────────────────────────────────────

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ─── WebSocket Connection ────────────────────────────────

    function connectWS() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${protocol}//${location.host}/ws`;

        setBadge("connecting");

        try {
            state.ws = new WebSocket(url);
        } catch (e) {
            scheduleReconnect();
            return;
        }

        state.ws.onopen = () => {
            state.wsConnected = true;
            setBadge("connected");
            // Start ping interval
            state.pingInterval = setInterval(() => {
                if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.ws.send(JSON.stringify({ action: "ping" }));
                }
            }, 30000);
        };

        state.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleWSMessage(msg);
            } catch (e) {
                // ignore parse errors
            }
        };

        state.ws.onclose = () => {
            state.wsConnected = false;
            setBadge("disconnected");
            clearInterval(state.pingInterval);
            scheduleReconnect();
        };

        state.ws.onerror = () => {
            state.wsConnected = false;
            setBadge("disconnected");
        };
    }

    function scheduleReconnect() {
        clearTimeout(state.reconnectTimer);
        state.reconnectTimer = setTimeout(connectWS, 2000);
    }

    function setBadge(status) {
        const badge = $("#status-badge");
        badge.className = "badge " + status;
        badge.textContent =
            status === "connected" ? "Connected" :
            status === "connecting" ? "Connecting..." :
            "Disconnected";
    }

    // ─── WebSocket Message Handler ───────────────────────────

    function handleWSMessage(msg) {
        switch (msg.type) {
            case "screenshot":
                updateScreenshot(msg.data);
                break;

            case "status":
                updateStatusBar(msg.data);
                break;

            case "command":
                addCommandItem(msg.data);
                break;

            case "pong":
                break;

            case "error":
                console.error("Debug WS error:", msg.error);
                break;

            case "login_handoff":
                handleHandoffWSMessage(msg);
                break;
        }
    }

    // ─── Screenshot ──────────────────────────────────────────

    function updateScreenshot(b64) {
        if (!b64) return;
        state.screenshotData = b64;
        const img = $("#browser-screenshot");
        const placeholder = $("#browser-placeholder");

        img.src = `data:image/png;base64,${b64}`;
        img.style.display = "block";
        placeholder.classList.add("hidden");
    }

    // ─── Status Bar ──────────────────────────────────────────

    function updateStatusBar(data) {
        if (data.ram_mb !== undefined) {
            const el = $("#stat-ram");
            el.textContent = data.ram_mb;
            el.style.color = data.ram_mb > 400 ? "var(--red)" : data.ram_mb > 300 ? "var(--yellow)" : "var(--text-primary)";
        }
        if (data.uptime !== undefined) {
            $("#stat-uptime").textContent = formatUptime(data.uptime);
        }
        if (data.sessions !== undefined) {
            $("#stat-sessions").textContent = data.sessions;
        }
        if (data.ws_clients !== undefined) {
            $("#stat-clients").textContent = data.ws_clients;
        }
        if (data.tabs !== undefined) {
            $("#stat-tabs").textContent = data.tabs;
        }
    }

    function formatUptime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}h${m}m`;
        if (m > 0) return `${m}m${s}s`;
        return `${s}s`;
    }

    // ─── Navigation ──────────────────────────────────────────

    function initNavigation() {
        $$(".nav-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                const panel = btn.dataset.panel;
                switchPanel(panel);
            });
        });
    }

    function switchPanel(panelId) {
        state.currentPanel = panelId;

        // Update nav buttons
        $$(".nav-btn").forEach((b) => b.classList.remove("active"));
        $(`.nav-btn[data-panel="${panelId}"]`)?.classList.add("active");

        // Update panels
        $$(".panel").forEach((p) => p.classList.remove("active"));
        $(`#panel-${panelId}`)?.classList.add("active");

        // Auto-fetch data for certain panels
        switch (panelId) {
            case "sessions":
                fetchSessions();
                break;
            case "commands":
                fetchCommands();
                break;
            case "network":
                fetchNetwork();
                break;
            case "console":
                fetchConsole();
                break;
            case "cookies":
                fetchCookies();
                break;
            case "pages":
                fetchPages();
                break;
            case "dom":
                fetchDOM();
                break;
            case "handoff":
                fetchHandoffList();
                break;
        }
    }

    // ─── API Fetchers ────────────────────────────────────────

    async function apiGet(endpoint) {
        try {
            const res = await fetch(endpoint);
            return await res.json();
        } catch (e) {
            console.error(`API GET ${endpoint} failed:`, e);
            return { error: e.message };
        }
    }

    async function apiPost(endpoint, data) {
        try {
            const res = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            return await res.json();
        } catch (e) {
            console.error(`API POST ${endpoint} failed:`, e);
            return { error: e.message };
        }
    }

    // ─── Sessions ────────────────────────────────────────────

    async function fetchSessions() {
        const data = await apiGet("/api/sessions");
        const body = $("#sessions-body");

        if (!data.sessions || data.sessions.length === 0) {
            body.innerHTML = '<tr><td colspan="7" class="empty">No active sessions</td></tr>';
            return;
        }

        body.innerHTML = data.sessions
            .map(
                (s) => `
            <tr>
                <td><code>${s.session_id.substring(0, 12)}...</code></td>
                <td>${formatTime(s.created_at)}</td>
                <td>${formatUptime(s.expires_in_seconds)}</td>
                <td>${s.commands_executed}</td>
                <td>${s.blocked_requests}</td>
                <td><span class="tag ${s.active ? "tag-active" : "tag-expired"}">${s.active ? "Active" : "Expired"}</span></td>
                <td><button class="btn btn-sm btn-danger" onclick="destroySession('${s.session_id}')">Kill</button></td>
            </tr>
        `
            )
            .join("");
    }

    window.destroySession = async function (sessionId) {
        if (!confirm(`Destroy session ${sessionId}?`)) return;
        await apiPost("/api/session/destroy", { session_id: sessionId });
        fetchSessions();
    };

    // ─── Commands ────────────────────────────────────────────

    function addCommandItem(cmd) {
        state.commandHistory.push(cmd);
        const list = $("#command-list");

        // Clear empty state
        const empty = list.querySelector(".empty-state");
        if (empty) empty.remove();

        const time = formatTimestamp(cmd.timestamp);
        const statusClass = cmd.status === "success" ? "success" : cmd.status === "error" ? "error" : cmd.status === "running" ? "running" : "unknown";
        const params = cmd.params ? JSON.stringify(cmd.params).substring(0, 120) : "";
        const result = cmd.result ? JSON.stringify(cmd.result).substring(0, 200) : "";

        const item = document.createElement("div");
        item.className = "command-item";
        item.innerHTML = `
            <div class="cmd-status ${statusClass}"></div>
            <div class="cmd-info">
                <div class="cmd-name">${escHtml(cmd.command)}</div>
                ${params ? `<div class="cmd-params">${escHtml(params)}</div>` : ""}
                ${result ? `<div class="cmd-result">${escHtml(result)}</div>` : ""}
            </div>
            <div class="cmd-time">${time}</div>
        `;

        list.prepend(item);

        // Limit visible items
        while (list.children.length > 200) {
            list.removeChild(list.lastChild);
        }
    }

    async function fetchCommands() {
        const data = await apiGet("/api/commands");
        const list = $("#command-list");
        list.innerHTML = "";

        if (!data.commands || data.commands.length === 0) {
            list.innerHTML = '<div class="empty-state">No commands executed yet</div>';
            return;
        }

        // Render in reverse (newest first)
        data.commands.reverse().forEach((cmd) => addCommandItem(cmd));
    }

    // ─── Network ─────────────────────────────────────────────

    async function fetchNetwork() {
        const data = await apiGet("/api/network");
        const body = $("#network-body");

        if (!data.requests || data.requests.length === 0) {
            body.innerHTML = '<tr><td colspan="5" class="empty">No network requests captured</td></tr>';
            return;
        }

        body.innerHTML = data.requests
            .map(
                (r) => `
            <tr>
                <td>${formatTimestamp(r.timestamp)}</td>
                <td><span class="method-${(r.method || "get").toLowerCase()}">${escHtml(r.method || "GET")}</span></td>
                <td title="${escHtml(r.url || "")}">${escHtml(truncate(r.url || "", 80))}</td>
                <td><span class="status-${String(r.status || 0).charAt(0)}xx">${r.status || "-"}</span></td>
                <td>${escHtml(r.type || r.resource_type || "-")}</td>
            </tr>
        `
            )
            .join("");
    }

    // ─── Console ─────────────────────────────────────────────

    async function fetchConsole() {
        const data = await apiGet("/api/console");
        const output = $("#console-output");
        output.innerHTML = "";

        if (!data.logs || data.logs.length === 0) {
            output.innerHTML = '<div class="empty-state">No console logs yet</div>';
            return;
        }

        data.logs.forEach((log) => appendConsoleLine(log, output));
        output.scrollTop = output.scrollHeight;
    }

    function appendConsoleLine(log, container) {
        const line = document.createElement("div");
        line.className = `console-line ${log.level || "log"}`;
        line.innerHTML = `
            <span class="level">${escHtml(log.level || "log")}</span>
            <span class="msg">${escHtml(log.message || "")}</span>
            <span class="time">${formatTimestamp(log.timestamp)}</span>
        `;
        container.appendChild(line);
    }

    // ─── DOM Inspector ───────────────────────────────────────

    async function fetchDOM() {
        const data = await apiGet("/api/dom");
        const tree = $("#dom-tree");

        if (data.status === "error" || !data.dom_snapshot) {
            tree.innerHTML = `<div class="empty-state">${escHtml(data.error || "Could not inspect DOM")}</div>`;
            return;
        }

        // Render simplified DOM tree
        tree.innerHTML = renderDOMNode(data.dom_snapshot);
    }

    function renderDOMNode(node, depth = 0) {
        if (!node) return "";

        if (typeof node === "string") {
            return `<div style="padding-left:${depth * 16}px"><span class="dom-text">${escHtml(truncate(node, 200))}</span></div>`;
        }

        if (node.tag) {
            const attrs = node.attrs
                ? Object.entries(node.attrs)
                      .map(([k, v]) => ` <span class="dom-attr">${escHtml(k)}</span>="<span class="dom-value">${escHtml(truncate(String(v), 80))}</span>"`)
                      .join("")
                : "";

            let children = "";
            if (node.children && Array.isArray(node.children)) {
                children = node.children.map((c) => renderDOMNode(c, depth + 1)).join("");
            } else if (node.text) {
                children = `<div style="padding-left:${(depth + 1) * 16}px"><span class="dom-text">${escHtml(truncate(node.text, 200))}</span></div>`;
            }

            if (children) {
                return `
                    <div style="padding-left:${depth * 16}px">
                        &lt;<span class="dom-tag">${escHtml(node.tag)}</span>${attrs}&gt;
                    </div>
                    ${children}
                    <div style="padding-left:${depth * 16}px">
                        &lt;/<span class="dom-tag">${escHtml(node.tag)}</span>&gt;
                    </div>
                `;
            } else {
                return `<div style="padding-left:${depth * 16}px">&lt;<span class="dom-tag">${escHtml(node.tag)}</span>${attrs} /&gt;</div>`;
            }
        }

        // Array of nodes
        if (Array.isArray(node)) {
            return node.map((n) => renderDOMNode(n, depth)).join("");
        }

        // Generic object
        return `<div style="padding-left:${depth * 16}px"><span class="dom-text">${escHtml(JSON.stringify(node).substring(0, 200))}</span></div>`;
    }

    // ─── Cookie Import/Export ───────────────────────────────

    function initCookieImportExport() {
        // Export button
        $("#btn-export-cookies")?.addEventListener("click", exportCookies);

        // Import file input
        $("#cookie-import-input")?.addEventListener("change", handleCookieImport);
    }

    async function exportCookies() {
        const btn = $("#btn-export-cookies");
        btn.textContent = "⏳ Exporting...";
        btn.disabled = true;

        try {
            // Fetch as blob to trigger download
            const res = await fetch("/api/cookies/export");
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Export failed");
            }

            const blob = await res.blob();
            const count = res.headers.get("X-Cookie-Count") || "0";

            // Trigger download
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;

            // Extract filename from Content-Disposition or generate one
            const disposition = res.headers.get("Content-Disposition");
            const match = disposition && disposition.match(/filename="?(.+?)"?$/);
            a.download = match ? match[1] : `agent-os-cookies-${Date.now()}.json`;

            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            btn.textContent = `⬇ Exported (${count})`;
            setTimeout(() => {
                btn.textContent = "⬇ Export JSON";
            }, 2000);
        } catch (e) {
            btn.textContent = "⬇ Export Failed";
            setTimeout(() => {
                btn.textContent = "⬇ Export JSON";
            }, 2000);
            console.error("Cookie export failed:", e);
        } finally {
            btn.disabled = false;
        }
    }

    async function handleCookieImport(e) {
        const file = e.target.files[0];
        if (!file) return;

        const status = $("#cookie-import-status");
        const btn = $("#btn-import-cookies");

        status.textContent = "Importing...";
        status.className = "cookie-import-status importing";
        btn.style.opacity = "0.5";

        try {
            const formData = new FormData();
            formData.append("file", file);

            const res = await fetch("/api/cookies/import", {
                method: "POST",
                body: formData,
            });

            const result = await res.json();

            if (result.status === "success") {
                status.textContent = `✓ ${result.imported} imported, ${result.skipped} skipped`;
                status.className = "cookie-import-status success";

                // Refresh cookie table
                fetchCookies();
            } else {
                status.textContent = `✗ ${result.error || "Import failed"}`;
                status.className = "cookie-import-status error";
            }
        } catch (err) {
            status.textContent = `✗ ${err.message}`;
            status.className = "cookie-import-status error";
        } finally {
            btn.style.opacity = "1";
            // Reset file input so same file can be re-imported
            e.target.value = "";
            // Clear status after 5 seconds
            setTimeout(() => {
                status.textContent = "";
                status.className = "cookie-import-status";
            }, 5000);
        }
    }

    // ─── Cookies ─────────────────────────────────────────────

    async function fetchCookies() {
        const data = await apiGet("/api/cookies");
        const body = $("#cookies-body");

        const cookies = data.cookies || [];
        if (cookies.length === 0) {
            body.innerHTML = '<tr><td colspan="7" class="empty">No cookies loaded</td></tr>';
            return;
        }

        body.innerHTML = cookies
            .map(
                (c) => `
            <tr>
                <td><strong>${escHtml(c.name)}</strong></td>
                <td title="${escHtml(c.value)}">${escHtml(truncate(c.value, 40))}</td>
                <td>${escHtml(c.domain || "-")}</td>
                <td>${escHtml(c.path || "/")}</td>
                <td>${c.secure ? "🔒" : "—"}</td>
                <td>${c.httpOnly ? "✓" : "—"}</td>
                <td>${escHtml(c.sameSite || "-")}</td>
            </tr>
        `
            )
            .join("");
    }

    // ─── Pages ───────────────────────────────────────────────

    async function fetchPages() {
        const data = await apiGet("/api/page-info");
        const grid = $("#pages-grid");

        if (!data.pages || data.pages.length === 0) {
            grid.innerHTML = '<div class="empty-state">No pages open</div>';
            return;
        }

        grid.innerHTML = data.pages
            .map(
                (p) => `
            <div class="page-card">
                <div class="page-card-title">${escHtml(p.title || "Untitled")}</div>
                <div class="page-card-url">${escHtml(p.url || "unknown")}</div>
                <div class="page-card-stats">
                    <div class="page-stat">
                        <div class="page-stat-value">${p.elementCount || 0}</div>
                        <div class="page-stat-label">Elements</div>
                    </div>
                    <div class="page-stat">
                        <div class="page-stat-value">${p.linkCount || 0}</div>
                        <div class="page-stat-label">Links</div>
                    </div>
                    <div class="page-stat">
                        <div class="page-stat-value">${p.imageCount || 0}</div>
                        <div class="page-stat-label">Images</div>
                    </div>
                    <div class="page-stat">
                        <div class="page-stat-value">${p.formCount || 0}</div>
                        <div class="page-stat-label">Forms</div>
                    </div>
                    <div class="page-stat">
                        <div class="page-stat-value">${p.scriptCount || 0}</div>
                        <div class="page-stat-label">Scripts</div>
                    </div>
                    <div class="page-stat">
                        <div class="page-stat-value">${escHtml(p.tab_id || "-")}</div>
                        <div class="page-stat-label">Tab</div>
                    </div>
                </div>
            </div>
        `
            )
            .join("");
    }

    // ─── Terminal ────────────────────────────────────────────

    function initTerminal() {
        const input = $("#terminal-input");
        const tokenInput = $("#terminal-token-input");

        // Load saved token
        state.agentToken = localStorage.getItem("agent-os-token") || "";
        if (state.agentToken) {
            tokenInput.value = state.agentToken;
        }

        tokenInput.addEventListener("change", () => {
            state.agentToken = tokenInput.value.trim();
            localStorage.setItem("agent-os-token", state.agentToken);
        });

        input.addEventListener("keydown", async (e) => {
            if (e.key === "Enter") {
                const cmd = input.value.trim();
                if (!cmd) return;
                input.value = "";

                await executeTerminalCommand(cmd);
            }
        });
    }

    async function executeTerminalCommand(rawCmd) {
        const output = $("#terminal-output");

        // Show the command
        appendTerminalLine(`$ ${rawCmd}`, "command", output);

        if (!state.agentToken) {
            appendTerminalLine("Error: Set your agent token above first.", "error", output);
            return;
        }

        // Parse command: "navigate" or "navigate {\"url\":\"...\"}"
        let command, params = {};
        const braceIdx = rawCmd.indexOf("{");
        if (braceIdx > 0) {
            command = rawCmd.substring(0, braceIdx).trim();
            try {
                params = JSON.parse(rawCmd.substring(braceIdx));
            } catch (e) {
                appendTerminalLine(`Error: Invalid JSON params — ${e.message}`, "error", output);
                return;
            }
        } else {
            command = rawCmd;
        }

        const payload = { token: state.agentToken, command, ...params };

        try {
            const result = await apiPost("/api/command", payload);
            appendTerminalLine(JSON.stringify(result, null, 2), result.status === "error" ? "error" : "success", output);

            // Also add to command history panel
            addCommandItem({
                command,
                params,
                result,
                status: result.status || "unknown",
                timestamp: Date.now() / 1000,
            });

            // Refresh screenshot after navigation commands
            if (["navigate", "click", "smart-click", "back", "forward", "reload", "press", "fill-form"].includes(command)) {
                setTimeout(async () => {
                    const ss = await apiGet("/api/screenshot");
                    if (ss.screenshot) updateScreenshot(ss.screenshot);
                }, 500);
            }

            // Update browser URL if navigating
            if (command === "navigate" && params.url) {
                $("#browser-url").textContent = params.url;
            }
        } catch (e) {
            appendTerminalLine(`Error: ${e.message}`, "error", output);
        }

        output.scrollTop = output.scrollHeight;
    }

    function appendTerminalLine(text, cls, container) {
        const line = document.createElement("div");
        line.className = `terminal-line ${cls || ""}`;
        line.textContent = text;
        container.appendChild(line);
        container.scrollTop = container.scrollHeight;
    }

    // ─── Quick Commands ──────────────────────────────────────

    function initQuickCommands() {
        $$(".quick-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const command = btn.dataset.cmd;
                let params = {};
                try {
                    params = JSON.parse(btn.dataset.params || "{}");
                } catch (e) {}

                if (!state.agentToken) {
                    state.agentToken = $("#terminal-token-input").value.trim();
                }

                if (!state.agentToken) {
                    alert("Set your agent token first (Terminal panel)");
                    return;
                }

                // Visual feedback
                btn.style.opacity = "0.5";
                setTimeout(() => (btn.style.opacity = "1"), 300);

                const result = await apiPost("/api/command", {
                    token: state.agentToken,
                    command,
                    ...params,
                });

                addCommandItem({
                    command,
                    params,
                    result,
                    status: result.status || "unknown",
                    timestamp: Date.now() / 1000,
                });

                // Refresh screenshot
                if (command === "screenshot" && result.screenshot) {
                    updateScreenshot(result.screenshot);
                }
            });
        });
    }

    // ─── Event Listeners ─────────────────────────────────────

    function initEventListeners() {
        // Refresh buttons
        $("#btn-refresh-sessions")?.addEventListener("click", fetchSessions);
        $("#btn-refresh-commands")?.addEventListener("click", fetchCommands);
        $("#btn-refresh-network")?.addEventListener("click", fetchNetwork);
        $("#btn-refresh-screenshot")?.addEventListener("click", async () => {
            const data = await apiGet("/api/screenshot");
            if (data.screenshot) updateScreenshot(data.screenshot);
        });
        $("#btn-fetch-console")?.addEventListener("click", fetchConsole);
        $("#btn-fetch-dom")?.addEventListener("click", fetchDOM);
        $("#btn-fetch-cookies")?.addEventListener("click", fetchCookies);
        $("#btn-fetch-pages")?.addEventListener("click", fetchPages);

        // Clear buttons
        $("#btn-clear-commands")?.addEventListener("click", () => {
            state.commandHistory = [];
            $("#command-list").innerHTML = '<div class="empty-state">No commands executed yet</div>';
        });

        $("#btn-clear-console")?.addEventListener("click", () => {
            state.consoleLogs = [];
            $("#console-output").innerHTML = '<div class="empty-state">No console logs yet</div>';
        });

        // Screenshot download
        $("#btn-screenshot-download")?.addEventListener("click", () => {
            if (!state.screenshotData) return;
            const a = document.createElement("a");
            a.href = `data:image/png;base64,${state.screenshotData}`;
            a.download = `agent-os-screenshot-${Date.now()}.png`;
            a.click();
        });

        // Fullscreen toggle
        $("#btn-fullscreen")?.addEventListener("click", () => {
            document.body.classList.toggle("fullscreen-browser");
            const btn = $("#btn-fullscreen");
            btn.textContent = document.body.classList.contains("fullscreen-browser") ? "⛶ Exit" : "⛶";
        });

        // Network filter
        $("#network-filter")?.addEventListener("input", (e) => {
            const filter = e.target.value.toLowerCase();
            $$("#network-body tr").forEach((row) => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(filter) ? "" : "none";
            });
        });
    }

    // ─── Login Handoff ─────────────────────────────────────────

    function handleHandoffWSMessage(msg) {
        const eventData = msg.data || msg;
        const eventType = eventData.event_type || msg.event;

        if (eventType === "login_handoff_started") {
            // A new handoff was started — show the banner and update the panel
            showHandoffBanner(eventData);
            fetchHandoffList();
            showBrowserHandoffOverlay(eventData);
        } else if (eventType === "login_handoff_completed") {
            // Handoff completed — hide the banner
            hideHandoffBanner();
            hideBrowserHandoffOverlay();
            fetchHandoffList();
            fetchHandoffHistory();
        } else if (eventType === "login_handoff_cancelled") {
            hideHandoffBanner();
            hideBrowserHandoffOverlay();
            fetchHandoffList();
        } else if (eventType === "login_handoff_timed_out") {
            hideHandoffBanner();
            hideBrowserHandoffOverlay();
            fetchHandoffList();
        } else {
            // Generic update — refresh list
            fetchHandoffList();
        }
    }

    function showHandoffBanner(data) {
        const banner = $("#handoff-banner");
        const title = $("#handoff-banner-title");
        const msgEl = $("#handoff-banner-msg");

        const pageType = data.page_type || "login";
        const domain = data.domain || "unknown";
        title.textContent = pageType === "signup" ? "Signup Required" : "Login Required";
        msgEl.textContent = data.message || `${pageType.charAt(0).toUpperCase() + pageType.slice(1)} page on ${domain}. AI is paused — your turn to log in.`;

        banner.style.display = "block";

        // Show the quickbar complete button
        const quickComplete = $("#quick-complete-handoff");
        if (quickComplete) quickComplete.style.display = "";

        // Start countdown timer
        startHandoffTimer(data.timeout_seconds || 300);
    }

    function hideHandoffBanner() {
        const banner = $("#handoff-banner");
        banner.style.display = "none";

        const quickComplete = $("#quick-complete-handoff");
        if (quickComplete) quickComplete.style.display = "none";

        stopHandoffTimer();
    }

    function showBrowserHandoffOverlay(data) {
        const frame = $(".browser-frame");
        if (!frame) return;

        // Remove existing overlay
        const existing = frame.querySelector(".browser-handoff-overlay");
        if (existing) existing.remove();

        const domain = data.domain || "unknown";
        const pageType = data.page_type || "login";

        const overlay = document.createElement("div");
        overlay.className = "browser-handoff-overlay";
        overlay.id = "browser-handoff-overlay";
        overlay.innerHTML = `
            <div class="browser-handoff-overlay-icon">🔐</div>
            <div class="browser-handoff-overlay-text">${pageType === "signup" ? "Signup" : "Login"} Required on ${escHtml(domain)}</div>
            <div class="browser-handoff-overlay-sub">The AI has paused and is waiting for you to log in. Your credentials are secure and never seen by the AI.</div>
            <button class="browser-handoff-overlay-btn" id="overlay-complete-btn">✓ I'm Done Logging In</button>
        `;
        frame.appendChild(overlay);

        // Wire up the complete button
        overlay.querySelector("#overlay-complete-btn")?.addEventListener("click", () => {
            completeActiveHandoff();
        });
    }

    function hideBrowserHandoffOverlay() {
        const overlay = document.getElementById("browser-handoff-overlay");
        if (overlay) overlay.remove();
    }

    function startHandoffTimer(seconds) {
        stopHandoffTimer();
        let remaining = seconds;
        const timerEl = $("#handoff-banner-timer");

        function updateTimer() {
            const m = Math.floor(remaining / 60);
            const s = remaining % 60;
            timerEl.textContent = `${m}:${String(s).padStart(2, "0")}`;
            if (remaining <= 60) {
                timerEl.style.color = "var(--red)";
            } else {
                timerEl.style.color = "var(--yellow)";
            }
        }

        updateTimer();
        state.handoffTimerInterval = setInterval(() => {
            remaining--;
            if (remaining <= 0) {
                stopHandoffTimer();
                timerEl.textContent = "0:00";
                timerEl.style.color = "var(--red)";
                return;
            }
            updateTimer();
        }, 1000);
    }

    function stopHandoffTimer() {
        if (state.handoffTimerInterval) {
            clearInterval(state.handoffTimerInterval);
            state.handoffTimerInterval = null;
        }
    }

    async function fetchHandoffList() {
        const httpPort = window.location.port || "8002";
        // Try the direct handoff endpoint on the main HTTP server (port 8001)
        // Fallback to debug server proxy
        const data = await apiGet("/api/handoff/list");
        if (data.status === "error" && data.error && data.error.includes("Not Found")) {
            // Try via command
            return;
        }

        const handoffs = data.handoffs || [];
        state.activeHandoffs = handoffs.filter(h =>
            h.state === "waiting_for_user" || h.state === "detected"
        );

        renderHandoffCards(handoffs);

        // Show/hide banner based on active handoffs
        if (state.activeHandoffs.length > 0) {
            const active = state.activeHandoffs[0];
            showHandoffBanner({
                domain: active.domain,
                page_type: active.page_type,
                message: active.message,
                timeout_seconds: active.remaining_seconds || active.timeout_seconds || 300,
            });
        } else {
            hideHandoffBanner();
        }
    }

    async function fetchHandoffHistory() {
        const data = await apiGet("/api/handoff/history");
        const list = $("#handoff-history-list");

        if (data.status === "error" || !data.history || data.history.length === 0) {
            list.innerHTML = '<div class="empty-state">No handoff history yet</div>';
            return;
        }

        list.innerHTML = data.history.reverse().map(h => {
            const stateClass = h.state === "completed" ? "var(--green)" :
                              h.state === "cancelled" || h.state === "timed_out" ? "var(--red)" : "var(--text-secondary)";
            const duration = h.elapsed_seconds ? `${h.elapsed_seconds.toFixed(0)}s` : "-";
            const cookieCount = h.auth_cookie_names ? h.auth_cookie_names.length : 0;

            return `
                <div class="handoff-history-item">
                    <span class="handoff-history-domain">${escHtml(h.domain)}</span>
                    <span class="handoff-history-type">${escHtml(h.page_type)}</span>
                    <span class="handoff-history-duration">${duration}</span>
                    <span class="handoff-history-cookies">${cookieCount} cookies</span>
                    <span style="color:${stateClass};font-weight:600;font-size:10px;text-transform:uppercase">${escHtml(h.state)}</span>
                    <span class="handoff-history-time">${formatTimestamp(h.completed_at || h.created_at)}</span>
                </div>
            `;
        }).join("");
    }

    function renderHandoffCards(handoffs) {
        const container = $("#handoff-active-cards");

        if (!handoffs || handoffs.length === 0) {
            container.innerHTML = '<div class="empty-state">No active handoffs</div>';
            return;
        }

        container.innerHTML = handoffs.map(h => {
            const stateClass = h.state;
            const isActive = h.state === "waiting_for_user" || h.state === "detected";
            const remaining = h.remaining_seconds ? Math.ceil(h.remaining_seconds) : h.timeout_seconds || 0;
            const remMin = Math.floor(remaining / 60);
            const remSec = remaining % 60;

            return `
                <div class="handoff-card ${stateClass}">
                    <div class="handoff-card-header">
                        <span class="handoff-card-domain">${escHtml(h.domain)}</span>
                        <span class="handoff-card-state ${stateClass}">${escHtml(h.state.replace(/_/g, " "))}</span>
                    </div>
                    <div class="handoff-card-url" title="${escHtml(h.url)}">${escHtml(h.url)}</div>
                    ${h.message ? `<div class="handoff-card-message">${escHtml(h.message)}</div>` : ""}
                    <div class="handoff-card-details">
                        <div class="handoff-card-detail">
                            <div class="handoff-card-detail-label">Type</div>
                            <div class="handoff-card-detail-value">${escHtml(h.page_type)}</div>
                        </div>
                        <div class="handoff-card-detail">
                            <div class="handoff-card-detail-label">Confidence</div>
                            <div class="handoff-card-detail-value">${(h.confidence * 100).toFixed(0)}%</div>
                        </div>
                        <div class="handoff-card-detail">
                            <div class="handoff-card-detail-label">Remaining</div>
                            <div class="handoff-card-detail-value" style="color:${remaining <= 60 ? "var(--red)" : "var(--yellow)"}">${remMin}:${String(remSec).padStart(2, "0")}</div>
                        </div>
                        <div class="handoff-card-detail">
                            <div class="handoff-card-detail-label">Elapsed</div>
                            <div class="handoff-card-detail-value">${h.elapsed_seconds ? h.elapsed_seconds.toFixed(0) + "s" : "0s"}</div>
                        </div>
                    </div>
                    ${isActive ? `
                    <div class="handoff-card-actions">
                        <button class="btn btn-sm btn-handoff-complete" onclick="completeHandoff('${escHtml(h.handoff_id)}')">✓ I'm Done Logging In</button>
                        <button class="btn btn-sm btn-danger" onclick="cancelHandoff('${escHtml(h.handoff_id)}')">✗ Cancel</button>
                    </div>
                    ` : ""}
                    ${h.auth_cookie_names && h.auth_cookie_names.length > 0 ? `
                    <div style="margin-top:8px;font-size:11px;color:var(--green)">
                        Auth cookies: ${h.auth_cookie_names.map(n => escHtml(n)).join(", ")}
                    </div>
                    ` : ""}
                </div>
            `;
        }).join("");
    }

    async function detectLoginPage() {
        const data = await apiPost("/api/handoff/detect", { page_id: "main" });
        const resultSection = $("#handoff-detection-result");
        const card = $("#handoff-detection-card");

        if (data.status === "error") {
            resultSection.style.display = "none";
            alert("Detection failed: " + (data.error || "Unknown error"));
            return;
        }

        resultSection.style.display = "block";
        const isLogin = data.is_login_page;
        const pageType = data.page_type || "none";
        const confidence = data.confidence || 0;

        card.innerHTML = `
            <div class="detection-field">
                <span class="detection-label">Is Login Page</span>
                <span class="detection-value" style="color:${isLogin ? "var(--yellow)" : "var(--green)"}">${isLogin ? "YES" : "NO"}</span>
            </div>
            <div class="detection-field">
                <span class="detection-label">Page Type</span>
                <span class="detection-value">${escHtml(pageType)}</span>
            </div>
            <div class="detection-field">
                <span class="detection-label">Confidence</span>
                <span class="detection-value" style="color:${confidence > 0.7 ? "var(--yellow)" : "var(--text-primary)"}">${(confidence * 100).toFixed(0)}%</span>
            </div>
            <div class="detection-field">
                <span class="detection-label">Domain</span>
                <span class="detection-value">${escHtml(data.domain || "-")}</span>
            </div>
            <div class="detection-field">
                <span class="detection-label">URL</span>
                <span class="detection-value" title="${escHtml(data.url || "")}">${escHtml(truncate(data.url || "-", 80))}</span>
            </div>
        `;
    }

    async function startHandoff() {
        const data = await apiPost("/api/handoff/start", {
            page_id: "main",
            timeout_seconds: 300,
        });

        if (data.status === "success") {
            showHandoffBanner({
                domain: data.domain,
                page_type: data.page_type,
                message: data.message,
                timeout_seconds: data.timeout_seconds,
            });
            showBrowserHandoffOverlay(data);
            fetchHandoffList();
        } else {
            alert("Failed to start handoff: " + (data.error || "Unknown error"));
        }
    }

    async function completeActiveHandoff() {
        if (state.activeHandoffs.length === 0) {
            alert("No active handoff to complete");
            return;
        }
        const handoffId = state.activeHandoffs[0].handoff_id;
        await completeHandoff(handoffId);
    }

    window.completeHandoff = async function (handoffId) {
        const data = await apiPost(`/api/handoff/${handoffId}/complete`, {});

        if (data.status === "success") {
            hideHandoffBanner();
            hideBrowserHandoffOverlay();
            fetchHandoffList();
            fetchHandoffHistory();
        } else {
            alert("Failed to complete handoff: " + (data.error || "Unknown error"));
        }
    };

    window.cancelHandoff = async function (handoffId) {
        if (!confirm("Cancel this login handoff? The AI will resume without logging in.")) return;

        const data = await apiPost(`/api/handoff/${handoffId}/cancel`, {
            reason: "Cancelled by user from Debug UI",
        });

        if (data.status === "success") {
            hideHandoffBanner();
            hideBrowserHandoffOverlay();
            fetchHandoffList();
        } else {
            alert("Failed to cancel handoff: " + (data.error || "Unknown error"));
        }
    };

    function initHandoffPanel() {
        // Detect Login button
        $("#btn-handoff-detect")?.addEventListener("click", detectLoginPage);

        // Start Handoff button
        $("#btn-handoff-start")?.addEventListener("click", startHandoff);

        // Refresh button
        $("#btn-handoff-refresh")?.addEventListener("click", () => {
            fetchHandoffList();
            fetchHandoffHistory();
        });

        // Banner complete button
        $("#btn-handoff-complete-banner")?.addEventListener("click", completeActiveHandoff);

        // Banner cancel button
        $("#btn-handoff-cancel-banner")?.addEventListener("click", () => {
            if (state.activeHandoffs.length > 0) {
                cancelHandoff(state.activeHandoffs[0].handoff_id);
            }
        });

        // Quick bar buttons
        $("#quick-detect-login")?.addEventListener("click", detectLoginPage);
        $("#quick-start-handoff")?.addEventListener("click", startHandoff);
        $("#quick-complete-handoff")?.addEventListener("click", completeActiveHandoff);
    }

    // ─── Utilities ───────────────────────────────────────────

    function escHtml(str) {
        if (typeof str !== "string") return String(str);
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function truncate(str, max) {
        if (!str || str.length <= max) return str;
        return str.substring(0, max) + "…";
    }

    function formatTimestamp(ts) {
        if (!ts) return "-";
        const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
        return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function formatTime(isoStr) {
        if (!isoStr) return "-";
        try {
            const d = new Date(isoStr);
            return d.toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            });
        } catch {
            return isoStr;
        }
    }

    // ─── Init ────────────────────────────────────────────────

    function init() {
        initNavigation();
        initTerminal();
        initQuickCommands();
        initCookieImportExport();
        initHandoffPanel();
        initEventListeners();
        connectWS();

        // Initial data fetch
        apiGet("/api/status").then((data) => {
            if (data.ram_usage_mb) updateStatusBar(data);
        });
    }

    // Start when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
