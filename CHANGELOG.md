# Changelog

All notable changes to Agent X are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.1] — 2026-05-29

### Security
- Fixed WebGL vendor/renderer incoherence — now auto-selected per platform (macOS→Apple, Win/Linux→rotated Intel/NVIDIA/AMD) instead of hardcoded "Intel Inc." for all profiles
- Fixed cookie encryption key write to use atomic pattern (temp + fsync + rename) to prevent corruption on crash
- Replaced hardcoded demo token in `human_demo.py` with env-var/prompt pattern
- Fixed secret-scanner false positive in `qwen_bridge.py` comments

### Fixed
- `.env` file path mismatch between setup wizard and main loader — main.py now tries multiple locations (app dir + home config dir)
- `sec-ch-ua-mobile` header always `?0` — now correctly `?1` for mobile User-Agents
- Cross-platform signal handling — SIGTERM guarded on Windows, graceful fallback when not in main thread
- `install.sh` API key prompt showed even when `.env` already existed — now properly guarded
- Race condition in `session.destroy_session` — consolidated browser null check
- Database `enabled` default mismatch — config now matches main.py behavior (`True` with SQLite fallback)
- urllib3 pinned to `<2.0.0` causing dependency conflicts — bumped to `>=2.0.0,<3.0.0`
- Bare `except:` clauses changed to `except Exception:` to avoid catching `KeyboardInterrupt`/`SystemExit`
- Legacy token validation used O(n) list scan — converted to O(1) set lookup
- Block indicators used list for O(n) scan — converted to frozenset for O(1) lookup
- Token masking leaked length for short tokens — now shows fixed-length mask regardless of size

### Added
- Comprehensive audit report (`AUDIT_REPORT.md`) documenting 17 issues and fixes
- Full test results (`TEST_RESULTS.md`) with 19 test cases
- Stealth system documentation (`STEALTH.md`) with complete technique inventory
- Production CI workflow via GitHub Actions
- Contributing guidelines, security policy, and code of conduct
- `.editorconfig` for consistent formatting

## [4.0.0] — 2025-04-08

### Added
- Multi-Tab Handling — AI agents can manage multiple browser tabs simultaneously
- AI Visual Testing Engine — Zero-cost visual regression testing
- Claude Web Direct Connect — MCP over SSE via Cloudflare tunnel
- Token Optimizer — Adaptive page compression reducing LLM token usage by 90%+
- Advanced Stealth Engine — 5-layer defense (Network, CDP, JavaScript, Behavior, Fingerprint)
- Smart Navigator — Auto-switches between HTTP and browser per domain
- CAPTCHA Solver — Built-in OCR + AI-based challenge solving
- Agent Swarm — Multi-agent orchestration with shared memory
- Production Auth — JWT + API keys + legacy token support
- Docker Compose deployment support
