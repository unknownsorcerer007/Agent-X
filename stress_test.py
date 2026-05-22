#!/usr/bin/env python3
"""
Agent-OS Stress Test: Browse 100 websites including bot-protected ones.
Tests anti-detection, content extraction, and real browsing capability.

Improved v3.1:
- 100 websites across all categories
- Stricter block detection (checks status code + title + content)
- Per-category breakdown
- Block reason tracking
- JSON report with full details
"""
import httpx
import json
import time
import sys
from typing import Dict, List, Tuple, Any

TOKEN = "agent-os-main-2026"
BASE = "http://127.0.0.1:8001"

# 100 websites — comprehensive mix across all categories
SITES: List[Tuple[str, str, str]] = [
    # (url, name, category)

    # ── Easy Sites (baseline) ──
    ("https://example.com", "Example Domain", "baseline"),
    ("https://httpbin.org", "httpbin", "baseline"),
    ("https://www.wikipedia.org", "Wikipedia", "baseline"),
    ("https://news.ycombinator.com", "Hacker News", "baseline"),
    ("https://github.com", "GitHub", "baseline"),
    ("https://stackoverflow.com", "Stack Overflow", "baseline"),
    ("https://www.mozilla.org", "Mozilla", "baseline"),
    ("https://www.debian.org", "Debian", "baseline"),
    ("https://www.kernel.org", "Kernel.org", "baseline"),
    ("https://www.rust-lang.org", "Rust Lang", "baseline"),

    # ── E-commerce (heavy bot detection) ──
    ("https://www.amazon.com", "Amazon", "ecommerce"),
    ("https://www.ebay.com", "eBay", "ecommerce"),
    ("https://www.walmart.com", "Walmart", "ecommerce"),
    ("https://www.bestbuy.com", "Best Buy", "ecommerce"),
    ("https://www.target.com", "Target", "ecommerce"),
    ("https://www.etsy.com", "Etsy", "ecommerce"),
    ("https://www.aliexpress.com", "AliExpress", "ecommerce"),
    ("https://www.shopify.com", "Shopify", "ecommerce"),
    ("https://www.costco.com", "Costco", "ecommerce"),
    ("https://www.homedepot.com", "Home Depot", "ecommerce"),

    # ── Social Media (aggressive anti-bot) ──
    ("https://www.reddit.com", "Reddit", "social"),
    ("https://twitter.com", "X/Twitter", "social"),
    ("https://www.linkedin.com", "LinkedIn", "social"),
    ("https://www.instagram.com", "Instagram", "social"),
    ("https://www.facebook.com", "Facebook", "social"),
    ("https://www.tumblr.com", "Tumblr", "social"),
    ("https://www.pinterest.com", "Pinterest", "social"),
    ("https://www.quora.com", "Quora", "social"),
    ("https://www.tiktok.com", "TikTok", "social"),
    ("https://www.snapchat.com", "Snapchat", "social"),

    # ── News Sites ──
    ("https://www.nytimes.com", "NY Times", "news"),
    ("https://www.cnn.com", "CNN", "news"),
    ("https://www.bbc.com", "BBC", "news"),
    ("https://www.reuters.com", "Reuters", "news"),
    ("https://www.theguardian.com", "The Guardian", "news"),
    ("https://www.washingtonpost.com", "Washington Post", "news"),
    ("https://www.aljazeera.com", "Al Jazeera", "news"),
    ("https://www.forbes.com", "Forbes", "news"),
    ("https://www.techcrunch.com", "TechCrunch", "news"),
    ("https://arstechnica.com", "Ars Technica", "news"),

    # ── Travel (aggressive bot protection) ──
    ("https://www.booking.com", "Booking.com", "travel"),
    ("https://www.expedia.com", "Expedia", "travel"),
    ("https://www.tripadvisor.com", "TripAdvisor", "travel"),
    ("https://www.skyscanner.com", "Skyscanner", "travel"),
    ("https://www.kayak.com", "Kayak", "travel"),
    ("https://www.airbnb.com", "Airbnb", "travel"),
    ("https://www.marriott.com", "Marriott", "travel"),
    ("https://www.hotels.com", "Hotels.com", "travel"),

    # ── Search Engines & Portals ──
    ("https://www.google.com", "Google", "search"),
    ("https://www.bing.com", "Bing", "search"),
    ("https://duckduckgo.com", "DuckDuckGo", "search"),
    ("https://www.yahoo.com", "Yahoo", "search"),
    ("https://www.ask.com", "Ask.com", "search"),

    # ── Finance (heavy security) ──
    ("https://www.bloomberg.com", "Bloomberg", "finance"),
    ("https://finance.yahoo.com", "Yahoo Finance", "finance"),
    ("https://www.investing.com", "Investing.com", "finance"),
    ("https://www.coinmarketcap.com", "CoinMarketCap", "finance"),
    ("https://www.marketwatch.com", "MarketWatch", "finance"),
    ("https://www.cnbc.com", "CNBC", "finance"),
    ("https://www.wsj.com", "Wall Street Journal", "finance"),
    ("https://www.nasdaq.com", "NASDAQ", "finance"),

    # ── Tech Companies ──
    ("https://www.microsoft.com", "Microsoft", "tech"),
    ("https://www.apple.com", "Apple", "tech"),
    ("https://www.google.com/about", "Google About", "tech"),
    ("https://www.cloudflare.com", "Cloudflare", "tech"),
    ("https://www.oracle.com", "Oracle", "tech"),
    ("https://www.ibm.com", "IBM", "tech"),
    ("https://www.salesforce.com", "Salesforce", "tech"),
    ("https://www.adobe.com", "Adobe", "tech"),

    # ── Government & Education ──
    ("https://www.nasa.gov", "NASA", "gov_edu"),
    ("https://www.nih.gov", "NIH", "gov_edu"),
    ("https://www.whitehouse.gov", "White House", "gov_edu"),
    ("https://www.census.gov", "US Census", "gov_edu"),
    ("https://www.mit.edu", "MIT", "gov_edu"),
    ("https://www.stanford.edu", "Stanford", "gov_edu"),

    # ── Heavy Anti-Bot / Cloudflare ──
    ("https://www.zillow.com", "Zillow", "heavy_antibot"),
    ("https://www.craigslist.org", "Craigslist", "heavy_antibot"),
    ("https://www.glassdoor.com", "Glassdoor", "heavy_antibot"),
    ("https://www.indeed.com", "Indeed", "heavy_antibot"),
    ("https://www.trulia.com", "Trulia", "heavy_antibot"),
    ("https://www.realtor.com", "Realtor.com", "heavy_antibot"),

    # ── Streaming & Media ──
    ("https://www.imdb.com", "IMDb", "media"),
    ("https://www.rottentomatoes.com", "Rotten Tomatoes", "media"),
    ("https://www.spotify.com", "Spotify", "media"),
    ("https://www.twitch.tv", "Twitch", "media"),
    ("https://www.soundcloud.com", "SoundCloud", "media"),
    ("https://www.vimeo.com", "Vimeo", "media"),

    # ── Developer / Tech Platforms ──
    ("https://dev.to", "Dev.to", "developer"),
    ("https://www.medium.com", "Medium", "developer"),
    ("https://www.producthunt.com", "Product Hunt", "developer"),
    ("https://www.npmjs.com", "npm", "developer"),
    ("https://pypi.org", "PyPI", "developer"),
    ("https://hub.docker.com", "Docker Hub", "developer"),

    # ── Miscellaneous ──
    ("https://www.paypal.com", "PayPal", "misc"),
    ("https://www.craigslist.org", "Craigslist 2", "misc"),
    ("https://www.weather.com", "Weather.com", "misc"),
    ("https://www.espn.com", "ESPN", "misc"),
    ("https://www.imdb.com/chart/top", "IMDb Charts", "misc"),
    ("https://www.reddiquette.com", "Reddiquette", "misc"),
    ("https://archive.org", "Internet Archive", "misc"),
    ("https://www.craigslist.org/about", "Craigslist About", "misc"),
    ("https://www.spotify.com/premium", "Spotify Premium", "misc"),
    ("https://www.netflix.com", "Netflix", "misc"),
]


# Block indicators — strict phrase matching (same logic as browser.py v3.1)
BLOCK_INDICATORS = [
    "access denied",
    "captcha required",
    "bot detected",
    "just a moment",
    "checking your browser",
    "please verify you are human",
    "unusual traffic from your computer",
    "attention required! | cloudflare",
    "cloudflare ray id",
    "enable javascript and cookies",
    "please enable js and disable any ad blocker",
    "are you a robot",
    "bot or not",
    "verify you are human",
    "help us protect",
    "you have been blocked by network security",
    "access to this page has been denied",
    "rate limit exceeded",
    "blocked by waf",
    "security check required",
    "please complete the security check",
    "managed challenge",
]


def classify_block(title: str, text: str, status_code: int) -> str:
    """Classify why a page was blocked or degraded."""
    combined = (title + " " + text[:300]).lower()

    if status_code == 429:
        return "rate_limited"
    if status_code == 403:
        if "cloudflare" in combined or "just a moment" in combined:
            return "cloudflare_403"
        if "captcha" in combined:
            return "captcha_403"
        if "bot" in combined:
            return "bot_detected_403"
        return "forbidden_403"
    if status_code == 503:
        return "service_unavailable"
    if status_code == 401:
        return "unauthorized_401"
    if status_code == 406:
        return "not_acceptable_406"

    for indicator in BLOCK_INDICATORS:
        if indicator in combined:
            return f"blocked_{indicator[:20].replace(' ', '_')}"

    return "unknown"


def is_real_success(title: str, text: str, status_code: int) -> bool:
    """
    Determine if we got REAL content, not just a 200 with a block page.
    Returns True only if the page has actual usable content.
    """
    # Non-200 status codes are never real success
    if status_code not in (200, 201, 202):
        return False

    # Empty title + empty text = likely blocked or JS-only page
    if not title.strip() and not text.strip():
        return False

    combined = (title + " " + text[:500]).lower()

    # Check for block indicators in content
    for indicator in BLOCK_INDICATORS:
        if indicator in combined:
            return False

    # Title is just the domain name with no real content = probably blocked
    if title.strip() in ("", "example.com", "etsy.com", "reuters.com",
                          "tripadvisor.com", "skyscanner.com"):
        return False

    return True


def cmd(command: str, **kwargs) -> Dict[str, Any]:
    """Send command to Agent-OS server."""
    payload = {"token": TOKEN, "command": command, **kwargs}
    try:
        r = httpx.post(f"{BASE}/command", json=payload, timeout=45)
        return r.json()
    except httpx.TimeoutException:
        return {"status": "error", "error": "Request timeout (45s)"}
    except httpx.ConnectError:
        return {"status": "error", "error": "Connection refused — is Agent-OS running?"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


def main() -> None:
    total_sites = len(SITES)
    results: List[Dict[str, Any]] = []
    real_success = 0
    degraded = 0  # Got 200 but content is blocked/limited
    blocked = 0
    failed = 0

    # Per-category tracking
    categories: Dict[str, Dict[str, int]] = {}

    print(f"\n{'='*72}")
    print(f"  🤖 AGENT-OS STRESS TEST v3.1 — {total_sites} WEBSITES")
    print(f"  Anti-detection, content extraction, real browsing capability")
    print(f"{'='*72}\n")

    for i, (url, name, category) in enumerate(SITES, 1):
        sys.stdout.write(f"\r[{i:3d}/{total_sites}] Testing {name:<25s}")
        sys.stdout.flush()

        # Initialize category tracking
        if category not in categories:
            categories[category] = {"success": 0, "degraded": 0, "blocked": 0, "failed": 0}

        start = time.time()
        try:
            nav = cmd("navigate", url=url)
            elapsed = round(time.time() - start, 1)

            if nav.get("status") == "success":
                title = nav.get("title", "")
                status_code = nav.get("status_code", 0)
                blocked_reqs = nav.get("blocked_requests", 0)

                # Get actual page content
                content = cmd("get-content")
                text = content.get("text", "")[:300].replace("\n", " ").strip()

                # Use strict success check
                if is_real_success(title, text, status_code):
                    real_success += 1
                    categories[category]["success"] += 1
                    status = "✅ OK"
                    block_reason = ""
                elif status_code in (200, 201, 202):
                    # Got 200 but content is blocked/limited
                    degraded += 1
                    categories[category]["degraded"] += 1
                    status = "⚠️ DEGRADED"
                    block_reason = classify_block(title, text, status_code)
                else:
                    blocked += 1
                    categories[category]["blocked"] += 1
                    status = "🛡️ BLOCKED"
                    block_reason = classify_block(title, text, status_code)

                results.append({
                    "i": i, "name": name, "url": url, "category": category,
                    "status": status, "block_reason": block_reason,
                    "title": title[:60], "text_preview": text[:100],
                    "time": elapsed, "code": status_code,
                    "blocked_reqs": blocked_reqs,
                })
            else:
                failed += 1
                categories[category]["failed"] += 1
                error = nav.get("error", "unknown")[:60]
                results.append({
                    "i": i, "name": name, "url": url, "category": category,
                    "status": "❌ FAIL", "block_reason": error,
                    "title": error, "text_preview": "",
                    "time": elapsed, "code": 0, "blocked_reqs": 0,
                })
        except Exception as e:
            failed += 1
            categories[category]["failed"] += 1
            elapsed = round(time.time() - start, 1)
            results.append({
                "i": i, "name": name, "url": url, "category": category,
                "status": "❌ ERROR", "block_reason": str(e)[:60],
                "title": str(e)[:60], "text_preview": "",
                "time": elapsed, "code": 0, "blocked_reqs": 0,
            })

        # Small delay between sites to avoid hammering
        time.sleep(0.3)

    # ─── Print Results ──────────────────────────────────────

    print(f"\n\n{'='*72}")
    print(f"  RESULTS — ALL {total_sites} SITES")
    print(f"{'='*72}\n")
    print(f"{'#':>3} {'Status':<12} {'Cat':<14} {'Name':<22} {'Time':>5}s  {'Code':>4}  {'Title':<40}")
    print(f"{'─'*3} {'─'*12} {'─'*14} {'─'*22} {'─'*5}  {'─'*4}  {'─'*40}")

    for r in results:
        title_display = r["title"][:40] if r["title"] else ""
        print(
            f"{r['i']:>3} {r['status']:<12} {r['category']:<14} "
            f"{r['name']:<22} {r['time']:>5.1f}  {r['code']:>4}  {title_display}"
        )

    # ─── Per-Category Breakdown ─────────────────────────────

    print(f"\n\n{'='*72}")
    print(f"  PER-CATEGORY BREAKDOWN")
    print(f"{'='*72}\n")
    print(f"{'Category':<16} {'Total':>5} {'✅ OK':>6} {'⚠️ Degraded':>11} {'🛡️ Blocked':>10} {'❌ Failed':>9} {'Success%':>9}")
    print(f"{'─'*16} {'─'*5} {'─'*6} {'─'*11} {'─'*10} {'─'*9} {'─'*9}")

    for cat, counts in sorted(categories.items()):
        cat_total = sum(counts.values())
        cat_ok = counts["success"]
        cat_deg = counts["degraded"]
        cat_blk = counts["blocked"]
        cat_fail = counts["failed"]
        cat_pct = (cat_ok / cat_total * 100) if cat_total > 0 else 0
        print(
            f"{cat:<16} {cat_total:>5} {cat_ok:>6} {cat_deg:>11} "
            f"{cat_blk:>10} {cat_fail:>9} {cat_pct:>8.1f}%"
        )

    # ─── Summary ────────────────────────────────────────────

    total_tested = real_success + degraded + blocked + failed
    success_pct = (real_success / total_tested * 100) if total_tested > 0 else 0
    degraded_pct = (degraded / total_tested * 100) if total_tested > 0 else 0
    blocked_pct = (blocked / total_tested * 100) if total_tested > 0 else 0
    failed_pct = (failed / total_tested * 100) if total_tested > 0 else 0

    print(f"\n{'='*72}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*72}")
    print(f"  ✅ Real Success (usable content):  {real_success:>3}/{total_tested}  ({success_pct:.1f}%)")
    print(f"  ⚠️  Degraded (200 but blocked):     {degraded:>3}/{total_tested}  ({degraded_pct:.1f}%)")
    print(f"  🛡️  Blocked (403/429/503):          {blocked:>3}/{total_tested}  ({blocked_pct:.1f}%)")
    print(f"  ❌ Failed (error/timeout):          {failed:>3}/{total_tested}  ({failed_pct:.1f}%)")
    print(f"  🌐 Total tested:                   {total_tested:>3}/{total_sites}")
    print(f"{'='*72}")

    # Effective success rate (real + degraded that show some content)
    effective = real_success + degraded
    effective_pct = (effective / total_tested * 100) if total_tested > 0 else 0
    print(f"\n  📊 Effective Success Rate: {effective_pct:.1f}% ({effective}/{total_tested})")
    print(f"     (includes degraded pages with partial content)\n")

    # ─── Top Block Reasons ──────────────────────────────────

    block_reasons: Dict[str, int] = {}
    for r in results:
        reason = r.get("block_reason", "")
        if reason and r["status"] not in ("✅ OK",):
            block_reasons[reason] = block_reasons.get(reason, 0) + 1

    if block_reasons:
        print(f"  🔍 Top Block Reasons:")
        for reason, count in sorted(block_reasons.items(), key=lambda x: -x[1])[:10]:
            print(f"     {count:>3}x — {reason}")
        print()

    # ─── Save Detailed Results ──────────────────────────────

    report = {
        "version": "3.1.0",
        "timestamp": time.time(),
        "summary": {
            "total": total_tested,
            "real_success": real_success,
            "degraded": degraded,
            "blocked": blocked,
            "failed": failed,
            "success_rate_pct": round(success_pct, 1),
            "effective_rate_pct": round(effective_pct, 1),
        },
        "categories": categories,
        "block_reasons": block_reasons,
        "results": results,
    }

    output_path = "/root/.openclaw/workspace/Agent-OS/stress_test_results.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"📁 Detailed report saved to stress_test_results.json")


if __name__ == "__main__":
    main()
