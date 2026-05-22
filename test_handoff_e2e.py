#!/usr/bin/env python3
"""
End-to-End Login Handoff Test
Starts Agent OS, tests Instagram and Twitter handoff, then exits.
"""
import asyncio
import json
import sys
import os
import time
import base64
import signal

sys.path.insert(0, "/home/z/my-project/Agent-OS")

async def main():
    print("=" * 70)
    print("  Agent-OS Login Handoff E2E Test")
    print("  Instagram + Twitter Login Detection & Handoff")
    print("=" * 70)
    
    # Import and start Agent OS
    from main import parse_args, AgentOS
    
    class Args:
        headed = False
        agent_token = "test-handoff-token"
        port = None
        max_ram = 800
        config = None
        proxy = None
        device = None
        persistent = False
        debug = False
        rate_limit = 60
        swarm = False
        swarm_api_key = None
        database = None
        redis = None
        json_logs = False
        no_json_logs = True
        log_level = "WARNING"
        create_tables = False
    
    args = Args()
    app = AgentOS(args)
    
    # Start the server
    print("\n[1] Starting Agent-OS server...")
    server_task = asyncio.create_task(app.start())
    await asyncio.sleep(5)
    
    # Check browser health
    print("[2] Checking server health...")
    health_resp = await app.server._handle_health(
        type('Request', (), {'remote': 'localhost'})()
    )
    health = json.loads(health_resp.body.decode())
    print(f"    Server: {health['status']}, Browser: {health['checks'].get('browser', 'unknown')}")
    
    if health['status'] != 'healthy':
        print("    ERROR: Server not healthy, aborting test")
        await app.stop()
        return 1
    
    # Import httpx for API testing
    try:
        import httpx
    except ImportError:
        print("    httpx not available, using internal server methods")
        httpx = None
    
    TOKEN = "test-handoff-token"
    passed = 0
    failed = 0
    
    # ─── INSTAGRAM TEST ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  INSTAGRAM LOGIN HANDOFF TEST")
    print("=" * 70)
    
    # Navigate to Instagram
    print("\n[3] Navigating to Instagram login page...")
    try:
        nav_result = await app.server._process_command(
            {"token": TOKEN, "command": "navigate", "url": "https://www.instagram.com/accounts/login/"},
            {"user_id": "legacy", "scopes": ["browser"], "auth_method": "legacy_token"}
        )
        print(f"    Status: {nav_result.get('status')}")
        print(f"    URL: {nav_result.get('url', '')[:60]}")
        if nav_result.get('status') == 'success':
            passed += 1
        else:
            failed += 1
            print(f"    Error: {nav_result.get('error', 'unknown')}")
    except Exception as e:
        print(f"    ERROR: {e}")
        failed += 1
    
    await asyncio.sleep(4)
    
    # Detect login page
    print("\n[4] Detecting Instagram login page...")
    try:
        handoff_mgr = app.server._get_login_handoff()
        detection = await handoff_mgr.detect_login_page("main")
        print(f"    is_login_page: {detection.get('is_login_page')}")
        print(f"    page_type: {detection.get('page_type')}")
        print(f"    confidence: {detection.get('confidence')}")
        print(f"    domain: {detection.get('domain')}")
        if detection.get('is_login_page'):
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        failed += 1
    
    # Start handoff
    print("\n[5] Starting Instagram handoff...")
    try:
        handoff_result = await handoff_mgr.start_handoff(
            url="https://www.instagram.com/accounts/login/",
            page_id="main",
            user_id="test_user",
            session_id="test_session",
            timeout_seconds=300,
        )
        ig_handoff_id = handoff_result.get("handoff_id", "")
        print(f"    Status: {handoff_result.get('status')}")
        print(f"    Handoff ID: {ig_handoff_id}")
        print(f"    Domain: {handoff_result.get('domain')}")
        print(f"    State: {handoff_result.get('state')}")
        print(f"    Message: {handoff_result.get('message', '')[:80]}")
        if handoff_result.get('status') == 'success':
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        ig_handoff_id = ""
        failed += 1
    
    # Check status
    if ig_handoff_id:
        print("\n[6] Checking handoff status...")
        status = await handoff_mgr.get_handoff_status(ig_handoff_id)
        h = status.get("handoff", {})
        print(f"    State: {h.get('state')}")
        print(f"    Remaining: {h.get('remaining_seconds')}s")
        print(f"    Elapsed: {h.get('elapsed_seconds')}s")
        passed += 1
    
    # Take screenshot
    print("\n[7] Taking screenshot...")
    try:
        ss_result = await app.server._process_command(
            {"token": TOKEN, "command": "screenshot"},
            {"user_id": "legacy", "scopes": ["browser"], "auth_method": "legacy_token"}
        )
        if ss_result.get("screenshot"):
            img_data = base64.b64decode(ss_result["screenshot"])
            img_path = "/home/z/my-project/download/instagram_login_handoff.png"
            with open(img_path, "wb") as f:
                f.write(img_data)
            print(f"    Screenshot saved: {img_path} ({len(img_data)} bytes)")
            passed += 1
        else:
            print(f"    No screenshot data")
            failed += 1
    except Exception as e:
        print(f"    Screenshot error: {e}")
        failed += 1
    
    # Cancel Instagram handoff
    print("\n[8] Cancelling Instagram handoff...")
    if ig_handoff_id:
        cancel_result = await handoff_mgr.cancel_handoff(ig_handoff_id, reason="Test complete")
        print(f"    Status: {cancel_result.get('status')}, State: {cancel_result.get('state')}")
        passed += 1
    
    # ─── TWITTER/X TEST ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TWITTER/X LOGIN HANDOFF TEST")
    print("=" * 70)
    
    # Navigate to Twitter/X
    print("\n[9] Navigating to Twitter/X login page...")
    try:
        nav_result = await app.server._process_command(
            {"token": TOKEN, "command": "navigate", "url": "https://x.com/login"},
            {"user_id": "legacy", "scopes": ["browser"], "auth_method": "legacy_token"}
        )
        print(f"    Status: {nav_result.get('status')}")
        if nav_result.get('status') == 'success':
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        failed += 1
    
    await asyncio.sleep(4)
    
    # Detect Twitter login
    print("\n[10] Detecting Twitter/X login page...")
    try:
        tw_detection = await handoff_mgr.detect_login_page("main")
        print(f"    is_login_page: {tw_detection.get('is_login_page')}")
        print(f"    domain: {tw_detection.get('domain')}")
        print(f"    confidence: {tw_detection.get('confidence')}")
        if tw_detection.get('is_login_page') and tw_detection.get('domain') in ('x.com', 'twitter.com'):
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        failed += 1
    
    # Start Twitter handoff
    print("\n[11] Starting Twitter/X handoff...")
    try:
        tw_result = await handoff_mgr.start_handoff(
            url="https://x.com/login",
            page_id="main",
            user_id="test_user",
            timeout_seconds=300,
        )
        tw_handoff_id = tw_result.get("handoff_id", "")
        print(f"    Status: {tw_result.get('status')}")
        print(f"    Handoff ID: {tw_handoff_id}")
        print(f"    Domain: {tw_result.get('domain')}")
        if tw_result.get('status') == 'success':
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"    ERROR: {e}")
        tw_handoff_id = ""
        failed += 1
    
    # Cancel Twitter handoff
    if tw_handoff_id:
        print("\n[12] Cancelling Twitter/X handoff...")
        cancel_result = await handoff_mgr.cancel_handoff(tw_handoff_id, reason="Test complete")
        print(f"    Status: {cancel_result.get('status')}")
        passed += 1
    
    # ─── STATS ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  HANDOFF STATISTICS")
    print("=" * 70)
    
    stats = handoff_mgr.get_stats()
    print(f"  Total handoffs: {stats.get('total_handoffs')}")
    print(f"  Completed: {stats.get('completed_handoffs')}")
    print(f"  Cancelled: {stats.get('cancelled_handoffs')}")
    print(f"  Timed out: {stats.get('timed_out_handoffs')}")
    print(f"  Active: {stats.get('active_handoffs')}")
    print(f"  Success rate: {stats.get('success_rate')}%")
    
    # History
    history = await handoff_mgr.get_handoff_history()
    print(f"\n  History ({history.get('count')} entries):")
    for h in history.get("history", []):
        print(f"    - {h.get('domain', '?'):25s} | {h.get('state'):10s} | {h.get('page_type'):6s} | cookies: {len(h.get('auth_cookie_names', []))}")
    
    # Summary
    print("\n" + "=" * 70)
    print(f"  TEST RESULTS: {passed} PASSED, {failed} FAILED")
    print("=" * 70)
    
    # Stop server
    print("\nStopping Agent-OS...")
    await app.stop()
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
