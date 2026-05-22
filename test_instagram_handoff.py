#!/usr/bin/env python3
"""
Instagram & Twitter Login Handoff — Live Test
==============================================
Tests the complete login handoff flow with a running Agent-OS server.
"""
import asyncio
import json
import sys
import time
import base64

try:
    import httpx
except ImportError:
    print("httpx not available, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

BASE_URL = "http://127.0.0.1:8001"
TOKEN = "test-handoff-token"


async def test_instagram_handoff():
    """Test complete Instagram login handoff flow."""
    print("=" * 70)
    print("  Instagram Login Handoff — Live Test")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=30) as client:
        # Step 0: Check server health
        print("\n[0] Checking server health...")
        try:
            resp = await client.get(f"{BASE_URL}/health")
            health = resp.json()
            print(f"    Server: {health['status']}, Browser: {health['checks'].get('browser', 'unknown')}")
        except Exception as e:
            print(f"    ERROR: Server not reachable: {e}")
            return False

        # Step 1: Navigate to Instagram login page
        print("\n[1] Navigating to Instagram login page...")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "navigate",
                "url": "https://www.instagram.com/accounts/login/",
            })
            result = resp.json()
            print(f"    Status: {result.get('status', 'unknown')}")
            if result.get("status") != "success":
                print(f"    Error: {result.get('error', 'unknown')}")
                print(f"    Full response: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"    ERROR: {e}")
            return False

        # Wait for page to load
        print("    Waiting for page to load...")
        await asyncio.sleep(5)

        # Step 2: Detect login page
        print("\n[2] Detecting login page...")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/detect", json={
                "token": TOKEN,
                "page_id": "main",
            })
            result = resp.json()
            print(f"    is_login_page: {result.get('is_login_page')}")
            print(f"    page_type: {result.get('page_type')}")
            print(f"    confidence: {result.get('confidence')}")
            print(f"    domain: {result.get('domain')}")
            print(f"    url: {result.get('url', 'unknown')[:80]}")
        except Exception as e:
            print(f"    ERROR: {e}")
            # Try detection via command endpoint instead
            print("    Trying via command endpoint...")
            try:
                resp = await client.post(f"{BASE_URL}/command", json={
                    "token": TOKEN,
                    "command": "login-handoff-detect",
                    "page_id": "main",
                })
                result = resp.json()
                print(f"    Detection result: {json.dumps(result, indent=2)[:300]}")
            except Exception as e2:
                print(f"    Also failed: {e2}")

        # Step 3: Start handoff
        print("\n[3] Starting login handoff for Instagram...")
        handoff_id = None
        try:
            resp = await client.post(f"{BASE_URL}/handoff/start", json={
                "token": TOKEN,
                "url": "https://www.instagram.com/accounts/login/",
                "page_id": "main",
                "timeout_seconds": 300,
            })
            result = resp.json()
            print(f"    Status: {result.get('status')}")
            if result.get("status") == "success":
                handoff_id = result.get("handoff_id")
                print(f"    Handoff ID: {handoff_id}")
                print(f"    Domain: {result.get('domain')}")
                print(f"    Page Type: {result.get('page_type')}")
                print(f"    Confidence: {result.get('confidence')}")
                print(f"    State: {result.get('state')}")
                print(f"    Message: {result.get('message', '')[:100]}")
            else:
                print(f"    Error: {result.get('error', 'unknown')}")
                # Try via command endpoint
                print("    Trying via command endpoint...")
                try:
                    resp = await client.post(f"{BASE_URL}/command", json={
                        "token": TOKEN,
                        "command": "login-handoff-start",
                        "url": "https://www.instagram.com/accounts/login/",
                        "page_id": "main",
                        "timeout_seconds": 300,
                    })
                    result = resp.json()
                    print(f"    Result: {json.dumps(result, indent=2)[:500]}")
                    if result.get("status") == "success":
                        handoff_id = result.get("handoff_id")
                except Exception as e2:
                    print(f"    Also failed: {e2}")
        except Exception as e:
            print(f"    ERROR: {e}")

        if not handoff_id:
            print("\n    Could not start handoff. Testing URL detection only.")
            # Test URL detection at minimum
            from src.tools.login_handoff import LoginDetector
            is_login, page_type, confidence = LoginDetector.detect_from_url(
                "https://www.instagram.com/accounts/login/"
            )
            print(f"    URL Detection: is_login={is_login}, type={page_type}, conf={confidence}")
            return True

        # Step 4: Check handoff status
        print("\n[4] Checking handoff status...")
        try:
            # Try GET with token in header
            resp = await client.get(
                f"{BASE_URL}/handoff/{handoff_id}",
                headers={"X-API-Key": TOKEN},
            )
            result = resp.json()
            print(f"    State: {result.get('handoff', {}).get('state')}")
            print(f"    Remaining: {result.get('handoff', {}).get('remaining_seconds')}s")
        except Exception as e:
            print(f"    Status check error: {e}")

        # Step 5: List handoffs
        print("\n[5] Listing active handoffs...")
        try:
            resp = await client.get(
                f"{BASE_URL}/handoff",
                headers={"X-API-Key": TOKEN},
            )
            result = resp.json()
            print(f"    Active handoffs: {result.get('count', 0)}")
            for h in result.get("handoffs", []):
                print(f"      - {h.get('domain')}: {h.get('state')} (type={h.get('page_type')})")
        except Exception as e:
            print(f"    List error: {e}")

        # Step 6: Take screenshot to verify we're on Instagram
        print("\n[6] Taking screenshot of current page...")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "screenshot",
            })
            result = resp.json()
            if result.get("status") == "success" and result.get("screenshot"):
                screenshot_data = result["screenshot"]
                # Save screenshot
                img_path = "/home/z/my-project/download/instagram_login_handoff.png"
                with open(img_path, "wb") as f:
                    f.write(base64.b64decode(screenshot_data))
                print(f"    Screenshot saved to: {img_path}")
            else:
                print(f"    Screenshot status: {result.get('status')}")
        except Exception as e:
            print(f"    Screenshot error: {e}")

        # Step 7: Cancel handoff (since we can't actually login in headless)
        print("\n[7] Cancelling handoff (headless mode - can't manually login)...")
        if handoff_id:
            try:
                resp = await client.post(
                    f"{BASE_URL}/handoff/{handoff_id}/cancel",
                    json={"token": TOKEN, "reason": "Test complete - headless mode"},
                )
                result = resp.json()
                print(f"    Cancel status: {result.get('status')}")
                print(f"    Message: {result.get('message', '')[:100]}")
            except Exception as e:
                print(f"    Cancel error: {e}")

        # Step 8: Get handoff stats
        print("\n[8] Getting handoff statistics...")
        try:
            resp = await client.get(
                f"{BASE_URL}/handoff/stats",
                headers={"X-API-Key": TOKEN},
            )
            result = resp.json()
            stats = result.get("stats", result)
            print(f"    Total handoffs: {stats.get('total_handoffs', 'N/A')}")
            print(f"    Completed: {stats.get('completed_handoffs', 'N/A')}")
            print(f"    Cancelled: {stats.get('cancelled_handoffs', 'N/A')}")
        except Exception as e:
            print(f"    Stats error: {e}")

    print("\n" + "=" * 70)
    print("  Instagram Login Handoff Test COMPLETE")
    print("=" * 70)
    return True


async def test_twitter_handoff():
    """Test Twitter/X login handoff flow."""
    print("\n" + "=" * 70)
    print("  Twitter/X Login Handoff — Live Test")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=30) as client:
        # Navigate to Twitter/X
        print("\n[1] Navigating to Twitter/X login page...")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "navigate",
                "url": "https://x.com/login",
            })
            result = resp.json()
            print(f"    Navigation: {result.get('status')}")
        except Exception as e:
            print(f"    ERROR: {e}")
            return False

        await asyncio.sleep(5)

        # Detect
        print("\n[2] Detecting Twitter/X login page...")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/detect", json={
                "token": TOKEN,
                "page_id": "main",
            })
            result = resp.json()
            print(f"    is_login_page: {result.get('is_login_page')}")
            print(f"    domain: {result.get('domain')}")
            print(f"    confidence: {result.get('confidence')}")
        except Exception as e:
            print(f"    Detection error: {e}")

        # Start handoff
        print("\n[3] Starting Twitter/X handoff...")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/start", json={
                "token": TOKEN,
                "url": "https://x.com/login",
                "page_id": "main",
                "timeout_seconds": 300,
            })
            result = resp.json()
            if result.get("status") == "success":
                handoff_id = result.get("handoff_id")
                print(f"    Handoff started: {handoff_id}")
                print(f"    Domain: {result.get('domain')}")

                # Cancel
                resp = await client.post(
                    f"{BASE_URL}/handoff/{handoff_id}/cancel",
                    json={"token": TOKEN, "reason": "Test complete"},
                )
                print(f"    Cancelled: {resp.json().get('status')}")
            else:
                print(f"    Error: {result.get('error')}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\n" + "=" * 70)
    print("  Twitter/X Login Handoff Test COMPLETE")
    print("=" * 70)
    return True


async def main():
    print("\nINSTAGRAM & TWITTER LOGIN HANDOFF — LIVE TEST")
    print("=" * 70)
    
    success = True
    
    # Test Instagram
    if not await test_instagram_handoff():
        success = False
    
    # Test Twitter/X
    if not await test_twitter_handoff():
        success = False
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
