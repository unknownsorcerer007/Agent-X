#!/usr/bin/env bash
# Agent-OS CLI Connector — Complete (198 commands)
# Usage: ./agent-os-tool.sh <command> [args...]
# Env: AGENT_OS_URL (default: http://localhost:8001), AGENT_OS_TOKEN (required)

set -euo pipefail

AGENT_OS_URL="${AGENT_OS_URL:-http://localhost:8001}"
AGENT_OS_TOKEN="${AGENT_OS_TOKEN:-}"

send_command() {
    local cmd="$1"; shift
    local extra="$*"
    if [ -z "$AGENT_OS_TOKEN" ]; then echo '{"status":"error","error":"AGENT_OS_TOKEN not set"}' >&2; exit 1; fi
    local p="{\"token\":\"$AGENT_OS_TOKEN\",\"command\":\"$cmd\""
    [ -n "$extra" ] && p="$p,$extra"
    p="$p}"
    curl -s -X POST "$AGENT_OS_URL/command" -H "Content-Type: application/json" -d "$p" 2>/dev/null || echo '{"status":"error","error":"Connection failed"}'
}

send_get() {
    if [ -z "$AGENT_OS_TOKEN" ]; then echo '{"status":"error","error":"AGENT_OS_TOKEN not set"}' >&2; exit 1; fi
    curl -s "$AGENT_OS_URL$1" 2>/dev/null || echo '{"status":"error","error":"Connection failed"}'
}

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
# Status
status) send_get "/health" ;;

# Navigation
navigate) send_command "navigate" "\"url\":\"${1:-}\"" ;;
smart-navigate) send_command "smart-navigate" "\"url\":\"${1:-}\"" ;;
back) send_command "back" ;;
forward) send_command "forward" ;;
reload) send_command "reload" ;;
route) send_command "route" "\"query\":\"${1:-}\"" ;;
route-stats) send_command "route-stats" ;;

# Interaction
click) send_command "click" "\"selector\":\"${1:-}\"" ;;
double-click) send_command "double-click" "\"selector\":\"${1:-}\"" ;;
right-click) send_command "right-click" "\"selector\":\"${1:-}\"" ;;
context-action) send_command "context-action" "\"selector\":\"${1:-}\",\"action_text\":\"${2:-}\"" ;;
hover) send_command "hover" "\"selector\":\"${1:-}\"" ;;
type) send_command "type" "\"text\":\"${1:-}\"" ;;
press) send_command "press" "\"key\":\"${1:-}\"" ;;
fill-form) send_command "fill-form" "\"fields\":${1:-{}}" ;;
clear-input) send_command "clear-input" "\"selector\":\"${1:-}\"" ;;
select) send_command "select" "\"selector\":\"${1:-}\",\"value\":\"${2:-}\"" ;;
upload) send_command "upload" "\"selector\":\"${1:-}\",\"file_path\":\"${2:-}\"" ;;
checkbox) send_command "checkbox" "\"selector\":\"${1:-}\",\"checked\":${1:-true}" ;;
drag-drop) send_command "drag-drop" "\"source\":\"${1:-}\",\"target\":\"${2:-}\"" ;;
drag-offset) send_command "drag-offset" "\"selector\":\"${1:-}\",\"x\":${2:-0},\"y\":${3:-0}" ;;
scroll) send_command "scroll" "\"direction\":\"${1:-down}\",\"amount\":${2:-500}" ;;
wait) send_command "wait" "\"selector\":\"${1:-}\",\"timeout\":${2:-30}" ;;
viewport) send_command "viewport" "\"width\":${1:-1920},\"height\":${2:-1080}" ;;

# Smart Finder
smart-find) send_command "smart-find" "\"description\":\"${1:-}\"" ;;
smart-find-all) send_command "smart-find-all" "\"description\":\"${1:-}\"" ;;
smart-click) send_command "smart-click" "\"text\":\"${1:-}\"" ;;
smart-fill) send_command "smart-fill" "\"label\":\"${1:-}\",\"value\":\"${2:-}\"" ;;

# Content Extraction
get-content) send_command "get-content" ;;
get-dom) send_command "get-dom" ;;
screenshot) [ "${1:-}" = "--full" ] && send_command "screenshot" "\"full_page\":true" || send_command "screenshot" ;;
get-links) send_command "get-links" ;;
get-images) send_command "get-images" ;;
get-text) send_command "get-text" "\"selector\":\"${1:-}\"" ;;
get-attr) send_command "get-attr" "\"selector\":\"${1:-}\",\"attribute\":\"${2:-}\"" ;;
evaluate-js) send_command "evaluate-js" "\"script\":\"${1:-}\"" ;;
console-logs) send_command "console-logs" "\"limit\":${1:-100}" ;;

# Page Analysis
page-summary) send_command "page-summary" ;;
page-tables) send_command "page-tables" ;;
page-seo) send_command "page-seo" ;;
page-structured) send_command "page-structured" ;;
page-emails) send_command "page-emails" ;;
page-phones) send_command "page-phones" ;;
page-accessibility) send_command "page-accessibility" ;;
analyze) send_command "analyze" "\"url\":\"${1:-}\"" ;;
analyze-search) send_command "analyze-search" "\"query\":\"${1:-}\"" ;;

# Network
network-start) send_command "network-start" "\"url_pattern\":\"${1:-*}\"" ;;
network-stop) send_command "network-stop" ;;
network-get) send_command "network-get" "\"url_pattern\":\"${1:-}\"" ;;
network-apis) send_command "network-apis" ;;
network-detail) send_command "network-detail" "\"request_id\":\"${1:-}\"" ;;
network-stats) send_command "network-stats" ;;
network-export) send_command "network-export" "\"format\":\"${1:-json}\"" ;;
network-clear) send_command "network-clear" ;;

# Security
scan-xss) send_command "scan-xss" "\"url\":\"${1:-}\"" ;;
scan-sqli) send_command "scan-sqli" "\"url\":\"${1:-}\"" ;;
scan-sensitive) send_command "scan-sensitive" ;;

# Workflows
workflow) send_command "workflow" "\"steps\":${1:-[]}" ;;
workflow-save) send_command "workflow-save" "\"name\":\"${1:-}\",\"steps\":${2:-[]}" ;;
workflow-template) send_command "workflow-template" "\"template_name\":\"${1:-}\"" ;;
workflow-list) send_command "workflow-list" ;;
workflow-status) send_command "workflow-status" "\"workflow_id\":\"${1:-}\"" ;;
workflow-json) send_command "workflow-json" "\"json\":\"${1:-}\"" ;;

# Sessions
save-session) send_command "save-session" "\"name\":\"${1:-}\"" ;;
restore-session) send_command "restore-session" "\"name\":\"${1:-}\"" ;;
list-sessions) send_command "list-sessions" ;;
delete-session) send_command "delete-session" "\"name\":\"${1:-}\"" ;;
save-creds) send_command "save-creds" "\"domain\":\"${1:-}\",\"username\":\"${2:-}\",\"password\":\"${3:-}\"" ;;
auto-login) send_command "auto-login" "\"url\":\"${1:-}\",\"domain\":\"${2:-}\"" ;;
get-cookies) send_command "get-cookies" ;;
set-cookie) send_command "set-cookie" "\"name\":\"${1:-}\",\"value\":\"${2:-}\",\"domain\":\"${3:-}\"" ;;

# Tabs & Device
tabs) send_command "tabs" "\"action\":\"${1:-list}\",\"tab_id\":\"${2:-}\"" ;;
add-extension) send_command "add-extension" "\"path\":\"${1:-}\"" ;;
emulate-device) send_command "emulate-device" "\"device\":\"${1:-}\"" ;;
list-devices) send_command "list-devices" ;;

# Proxy
set-proxy) send_command "set-proxy" "\"proxy_url\":\"${1:-}\"" ;;
get-proxy) send_command "get-proxy" ;;
proxy-add) send_command "proxy-add" "\"url\":\"${1:-}\"" ;;
proxy-remove) send_command "proxy-remove" "\"proxy_id\":\"${1:-}\"" ;;
proxy-list) send_command "proxy-list" ;;
proxy-check) send_command "proxy-check" "\"proxy_id\":\"${1:-}\"" ;;
proxy-check-all) send_command "proxy-check-all" ;;
proxy-rotate) send_command "proxy-rotate" "\"strategy\":\"${1:-round_robin}\"" ;;
proxy-stats) send_command "proxy-stats" ;;
proxy-enable) send_command "proxy-enable" ;;
proxy-disable) send_command "proxy-disable" ;;
proxy-strategy) send_command "proxy-strategy" "\"strategy\":\"${1:-}\"" ;;
proxy-save) send_command "proxy-save" "\"filename\":\"${1:-}\"" ;;
proxy-load) send_command "proxy-load" "\"filename\":\"${1:-}\"" ;;
proxy-load-file) send_command "proxy-load-file" "\"filepath\":\"${1:-}\"" ;;
proxy-load-api) send_command "proxy-load-api" "\"url\":\"${1:-}\"" ;;
proxy-record) send_command "proxy-record" "\"proxy_id\":\"${1:-}\",\"success\":${2:-true}" ;;
proxy-get) send_command "proxy-get" ;;

# Smart Wait
smart-wait) send_command "smart-wait" "\"selector\":\"${1:-}\"" ;;
smart-wait-element) send_command "smart-wait-element" "\"selector\":\"${1:-}\"" ;;
smart-wait-network) send_command "smart-wait-network" ;;
smart-wait-js) send_command "smart-wait-js" "\"script\":\"${1:-}\"" ;;
smart-wait-dom) send_command "smart-wait-dom" ;;
smart-wait-page) send_command "smart-wait-page" ;;
smart-wait-compose) send_command "smart-wait-compose" "\"conditions\":${1:-[]}" ;;

# Auto-Heal
heal-click) send_command "heal-click" "\"selector\":\"${1:-}\"" ;;
heal-fill) send_command "heal-fill" "\"selector\":\"${1:-}\",\"value\":\"${2:-}\"" ;;
heal-hover) send_command "heal-hover" "\"selector\":\"${1:-}\"" ;;
heal-double-click) send_command "heal-double-click" "\"selector\":\"${1:-}\"" ;;
heal-wait) send_command "heal-wait" "\"selector\":\"${1:-}\"" ;;
heal-selector) send_command "heal-selector" "\"selector\":\"${1:-}\"" ;;
heal-stats) send_command "heal-stats" ;;
heal-clear) send_command "heal-clear" ;;
heal-fingerprint) send_command "heal-fingerprint" ;;
heal-fingerprint-page) send_command "heal-fingerprint-page" ;;

# Auto-Retry
retry-navigate) send_command "retry-navigate" "\"url\":\"${1:-}\"" ;;
retry-click) send_command "retry-click" "\"selector\":\"${1:-}\"" ;;
retry-fill) send_command "retry-fill" "\"selector\":\"${1:-}\",\"value\":\"${2:-}\"" ;;
retry-execute) send_command "retry-execute" "\"command\":\"${1:-}\"" ;;
retry-api-call) send_command "retry-api-call" "\"url\":\"${1:-}\"" ;;
retry-stats) send_command "retry-stats" ;;
retry-health) send_command "retry-health" ;;
retry-circuit-breakers) send_command "retry-circuit-breakers" ;;
retry-reset-circuit) send_command "retry-reset-circuit" "\"circuit_name\":\"${1:-}\"" ;;
retry-reset-all-circuits) send_command "retry-reset-all-circuits" ;;

# Recording & Replay
record-start) send_command "record-start" "\"name\":\"${1:-}\"" ;;
record-stop) send_command "record-stop" ;;
record-pause) send_command "record-pause" ;;
record-resume) send_command "record-resume" ;;
record-status) send_command "record-status" ;;
record-list) send_command "record-list" ;;
record-delete) send_command "record-delete" "\"name\":\"${1:-}\"" ;;
record-annotate) send_command "record-annotate" "\"name\":\"${1:-}\",\"step_index\":${2:-0},\"note\":\"${3:-}\"" ;;
replay-play) send_command "replay-play" "\"name\":\"${1:-}\"" ;;
replay-stop) send_command "replay-stop" ;;
replay-pause) send_command "replay-pause" ;;
replay-resume) send_command "replay-resume" ;;
replay-step) send_command "replay-step" ;;
replay-jump) send_command "replay-jump" "\"step_index\":${1:-0}" ;;
replay-position) send_command "replay-position" ;;
replay-events) send_command "replay-events" "\"name\":\"${1:-}\"" ;;
replay-load) send_command "replay-load" "\"name\":\"${1:-}\"" ;;
replay-export-workflow) send_command "replay-export-workflow" "\"name\":\"${1:-}\"" ;;

# Multi-Agent Hub
hub-register) send_command "hub-register" "\"agent_id\":\"${1:-}\"" ;;
hub-unregister) send_command "hub-unregister" "\"agent_id\":\"${1:-}\"" ;;
hub-agents) send_command "hub-agents" ;;
hub-status) send_command "hub-status" ;;
hub-broadcast) send_command "hub-broadcast" "\"message\":\"${1:-}\"" ;;
hub-handoff) send_command "hub-handoff" "\"target_agent\":\"${1:-}\"" ;;
hub-heartbeat) send_command "hub-heartbeat" ;;
hub-lock) send_command "hub-lock" "\"resource\":\"${1:-}\"" ;;
hub-unlock) send_command "hub-unlock" "\"resource\":\"${1:-}\"" ;;
hub-locks) send_command "hub-locks" ;;
hub-task-create) send_command "hub-task-create" "\"task_type\":\"${1:-}\",\"description\":\"${2:-}\"" ;;
hub-task-claim) send_command "hub-task-claim" "\"task_id\":\"${1:-}\",\"agent_id\":\"${2:-}\"" ;;
hub-task-start) send_command "hub-task-start" "\"task_id\":\"${1:-}\"" ;;
hub-task-complete) send_command "hub-task-complete" "\"task_id\":\"${1:-}\"" ;;
hub-task-fail) send_command "hub-task-fail" "\"task_id\":\"${1:-}\",\"error\":\"${2:-}\"" ;;
hub-task-cancel) send_command "hub-task-cancel" "\"task_id\":\"${1:-}\"" ;;
hub-tasks) send_command "hub-tasks" "\"status\":\"${1:-}\"" ;;
hub-events) send_command "hub-events" ;;
hub-audit) send_command "hub-audit" ;;
hub-memory-set) send_command "hub-memory-set" "\"key\":\"${1:-}\",\"value\":\"${2:-}\"" ;;
hub-memory-get) send_command "hub-memory-get" "\"key\":\"${1:-}\"" ;;
hub-memory-list) send_command "hub-memory-list" ;;
hub-memory-delete) send_command "hub-memory-delete" "\"key\":\"${1:-}\"" ;;

# Login Handoff
login-handoff-start) send_command "login-handoff-start" "\"url\":\"${1:-}\"" ;;
login-handoff-status) send_command "login-handoff-status" "\"session_id\":\"${1:-}\"" ;;
login-handoff-complete) send_command "login-handoff-complete" "\"session_id\":\"${1:-}\"" ;;
login-handoff-cancel) send_command "login-handoff-cancel" "\"session_id\":\"${1:-}\"" ;;
login-handoff-list) send_command "login-handoff-list" ;;
login-handoff-stats) send_command "login-handoff-stats" ;;
login-handoff-history) send_command "login-handoff-history" ;;
detect-login-page) send_command "detect-login-page" ;;

# TLS HTTP
fetch) send_command "fetch" "\"url\":\"${1:-}\"" ;;
tls-get) send_command "tls-get" "\"url\":\"${1:-}\"" ;;
tls-post) send_command "tls-post" "\"url\":\"${1:-}\",\"body\":\"${2:-}\"" ;;
tls-stats) send_command "tls-stats" ;;

# LLM
llm-complete) send_command "llm-complete" "\"prompt\":\"${1:-}\"" ;;
llm-summarize) send_command "llm-summarize" "\"text\":\"${1:-}\"" ;;
llm-classify) send_command "llm-classify" "\"text\":\"${1:-}\",\"categories\":${2:-[]}" ;;
llm-extract) send_command "llm-extract" "\"text\":\"${1:-}\",\"schema\":${2:-{}}" ;;
llm-provider-set) send_command "llm-provider-set" "\"provider\":\"${1:-}\"" ;;
llm-token-usage) send_command "llm-token-usage" ;;
llm-cache-clear) send_command "llm-cache-clear" ;;

# AI Content
ai-content) send_command "ai-content" ;;
fill-job) send_command "fill-job" "\"data\":${1:-{}}" ;;
structured-extract) send_command "structured-extract" "\"schema\":${1:-{}}" ;;
structured-format) send_command "structured-format" "\"data\":${1:-{}},\"format\":\"${2:-json}\"" ;;
structured-schema) send_command "structured-schema" ;;
structured-deduplicate) send_command "structured-deduplicate" "\"data\":${1:-[]}" ;;

# Captcha
captcha-assess) send_command "captcha-assess" ;;
captcha-preflight) send_command "captcha-preflight" "\"url\":\"${1:-}\"" ;;
captcha-health) send_command "captcha-health" ;;
captcha-monitor-start) send_command "captcha-monitor-start" ;;
captcha-monitor-stop) send_command "captcha-monitor-stop" ;;
captcha-shutdown) send_command "captcha-shutdown" ;;

# Query Router
classify-query) send_command "classify-query" "\"query\":\"${1:-}\"" ;;
needs-web) send_command "needs-web" "\"query\":\"${1:-}\"" ;;
query-strategy) send_command "query-strategy" "\"query\":\"${1:-}\"" ;;
router-stats) send_command "router-stats" ;;
nav-stats) send_command "nav-stats" ;;

# Media
transcribe) send_command "transcribe" "\"url\":\"${1:-}\",\"language\":\"${2:-en}\"" ;;

# Help (default)
help|--help|-h)
    echo "Agent-OS CLI — 198 commands"
    echo ""
    echo "Usage: $0 <command> [args...]"
    echo ""
    echo "Navigation:  navigate, smart-navigate, back, forward, reload, route"
    echo "Interaction: click, double-click, right-click, hover, type, press, fill-form,"
    echo "             clear-input, select, upload, checkbox, drag-drop, scroll, wait, viewport"
    echo "Smart:       smart-find, smart-find-all, smart-click, smart-fill"
    echo "Content:     get-content, get-dom, screenshot, get-links, get-images, get-text, get-attr, evaluate-js"
    echo "Analysis:    page-summary, page-tables, page-seo, page-structured, page-emails, page-phones, page-accessibility"
    echo "Network:     network-start, network-stop, network-get, network-apis, network-stats, network-export, network-clear"
    echo "Security:    scan-xss, scan-sqli, scan-sensitive"
    echo "Workflows:   workflow, workflow-save, workflow-template, workflow-list, workflow-json"
    echo "Sessions:    save-session, restore-session, list-sessions, delete-session, save-creds, auto-login, get-cookies, set-cookie"
    echo "Tabs:        tabs, add-extension, emulate-device, list-devices"
    echo "Proxy:       set-proxy, get-proxy, proxy-add, proxy-list, proxy-rotate, proxy-stats, proxy-enable, proxy-disable"
    echo "Smart Wait:  smart-wait, smart-wait-element, smart-wait-network, smart-wait-js, smart-wait-dom, smart-wait-page"
    echo "Auto-Heal:   heal-click, heal-fill, heal-hover, heal-stats, heal-clear, heal-fingerprint"
    echo "Auto-Retry:  retry-navigate, retry-click, retry-fill, retry-execute, retry-stats, retry-health"
    echo "Recording:   record-start, record-stop, record-pause, record-resume, record-list, record-delete"
    echo "Replay:      replay-play, replay-stop, replay-pause, replay-resume, replay-step, replay-jump"
    echo "Hub:         hub-register, hub-unregister, hub-agents, hub-status, hub-broadcast, hub-handoff, hub-lock"
    echo "Tasks:       hub-task-create, hub-task-claim, hub-task-start, hub-task-complete, hub-task-fail, hub-tasks"
    echo "Handoff:     login-handoff-start, login-handoff-complete, login-handoff-list, detect-login-page"
    echo "TLS HTTP:    fetch, tls-get, tls-post, tls-stats"
    echo "LLM:         llm-complete, llm-summarize, llm-classify, llm-extract, llm-provider-set, llm-token-usage"
    echo "AI:          ai-content, structured-extract, structured-format, structured-schema, fill-job"
    echo "Captcha:     captcha-assess, captcha-preflight, captcha-health, captcha-monitor-start"
    echo "Router:      classify-query, needs-web, query-strategy, router-stats, route, nav-stats"
    echo "Media:       transcribe"
    echo "Status:      status, help"
    ;;

*)
    echo "Unknown command: $CMD" >&2
    echo "Run '$0 help' for available commands." >&2
    exit 1
    ;;
esac
