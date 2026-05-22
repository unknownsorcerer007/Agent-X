#!/usr/bin/env python3
"""
Agent-OS 100-Website Stealth Test
Tests navigation against 100 sites with varying levels of anti-bot protection.
Records: status code, title, whether blocked/challenged, load time, engine.
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.browser import AgentBrowser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stress-test")

WEBSITES: List[Dict[str, Any]] = [
    {"url": "https://example.com", "tier": "easy", "name": "Example"},
    {"url": "https://httpbin.org/get", "tier": "easy", "name": "HTTPBin"},
    {"url": "https://httpbin.org/headers", "tier": "easy", "name": "HTTPBin Headers"},
    {"url": "https://www.wikipedia.org", "tier": "easy", "name": "Wikipedia"},
    {"url": "https://en.wikipedia.org/wiki/Main_Page", "tier": "easy", "name": "Wikipedia EN"},
    {"url": "https://www.gnu.org", "tier": "easy", "name": "GNU"},
    {"url": "https://www.kernel.org", "tier": "easy", "name": "Kernel.org"},
    {"url": "https://archive.org", "tier": "easy", "name": "Internet Archive"},
    {"url": "https://www.fsf.org", "tier": "easy", "name": "FSF"},
    {"url": "https://www.debian.org", "tier": "easy", "name": "Debian"},
    {"url": "https://www.ubuntu.com", "tier": "easy", "name": "Ubuntu"},
    {"url": "https://www.python.org", "tier": "easy", "name": "Python.org"},
    {"url": "https://docs.python.org", "tier": "easy", "name": "Python Docs"},
    {"url": "https://www.rust-lang.org", "tier": "easy", "name": "Rust Lang"},
    {"url": "https://nodejs.org", "tier": "easy", "name": "Node.js"},
    {"url": "https://www.ruby-lang.org", "tier": "easy", "name": "Ruby Lang"},
    {"url": "https://golang.org", "tier": "easy", "name": "Go Lang"},
    {"url": "https://www.sqlite.org", "tier": "easy", "name": "SQLite"},
    {"url": "https://www.postgresql.org", "tier": "easy", "name": "PostgreSQL"},
    {"url": "https://redis.io", "tier": "easy", "name": "Redis"},
    {"url": "https://www.cloudflare.com", "tier": "medium", "name": "Cloudflare"},
    {"url": "https://www.digitalocean.com", "tier": "medium", "name": "DigitalOcean"},
    {"url": "https://www.heroku.com", "tier": "medium", "name": "Heroku"},
    {"url": "https://www.netlify.com", "tier": "medium", "name": "Netlify"},
    {"url": "https://vercel.com", "tier": "medium", "name": "Vercel"},
    {"url": "https://www.npmjs.com", "tier": "medium", "name": "NPM"},
    {"url": "https://www.docker.com", "tier": "medium", "name": "Docker"},
    {"url": "https://hub.docker.com", "tier": "medium", "name": "Docker Hub"},
    {"url": "https://kubernetes.io", "tier": "medium", "name": "Kubernetes"},
    {"url": "https://grafana.com", "tier": "medium", "name": "Grafana"},
    {"url": "https://www.datadog.com", "tier": "medium", "name": "Datadog"},
    {"url": "https://shopify.com", "tier": "medium", "name": "Shopify"},
    {"url": "https://www.stripe.com", "tier": "medium", "name": "Stripe"},
    {"url": "https://squareup.com", "tier": "medium", "name": "Square"},
    {"url": "https://www.paypal.com", "tier": "medium", "name": "PayPal"},
    {"url": "https://www.linkedin.com", "tier": "medium", "name": "LinkedIn"},
    {"url": "https://www.microsoft.com", "tier": "medium", "name": "Microsoft"},
    {"url": "https://www.apple.com", "tier": "medium", "name": "Apple"},
    {"url": "https://www.oracle.com", "tier": "medium", "name": "Oracle"},
    {"url": "https://www.salesforce.com", "tier": "medium", "name": "Salesforce"},
    {"url": "https://www.adobe.com", "tier": "medium", "name": "Adobe"},
    {"url": "https://medium.com", "tier": "medium", "name": "Medium"},
    {"url": "https://dev.to", "tier": "medium", "name": "Dev.to"},
    {"url": "https://stackoverflow.com", "tier": "medium", "name": "StackOverflow"},
    {"url": "https://github.com", "tier": "medium", "name": "GitHub"},
    {"url": "https://gitlab.com", "tier": "medium", "name": "GitLab"},
    {"url": "https://bitbucket.org", "tier": "medium", "name": "Bitbucket"},
    {"url": "https://www.atlassian.com", "tier": "medium", "name": "Atlassian"},
    {"url": "https://www.amazon.com", "tier": "hard", "name": "Amazon US"},
    {"url": "https://www.amazon.co.uk", "tier": "hard", "name": "Amazon UK"},
    {"url": "https://www.ebay.com", "tier": "hard", "name": "eBay"},
    {"url": "https://www.walmart.com", "tier": "hard", "name": "Walmart"},
    {"url": "https://www.target.com", "tier": "hard", "name": "Target"},
    {"url": "https://www.bestbuy.com", "tier": "hard", "name": "BestBuy"},
    {"url": "https://www.homedepot.com", "tier": "hard", "name": "HomeDepot"},
    {"url": "https://www.lowes.com", "tier": "hard", "name": "Lowes"},
    {"url": "https://www.costco.com", "tier": "hard", "name": "Costco"},
    {"url": "https://www.etsy.com", "tier": "hard", "name": "Etsy"},
    {"url": "https://www.zillow.com", "tier": "hard", "name": "Zillow"},
    {"url": "https://www.realtor.com", "tier": "hard", "name": "Realtor"},
    {"url": "https://www.indeed.com", "tier": "hard", "name": "Indeed"},
    {"url": "https://www.glassdoor.com", "tier": "hard", "name": "Glassdoor"},
    {"url": "https://www.reddit.com", "tier": "hard", "name": "Reddit"},
    {"url": "https://old.reddit.com", "tier": "hard", "name": "Reddit Old"},
    {"url": "https://www.quora.com", "tier": "hard", "name": "Quora"},
    {"url": "https://twitter.com", "tier": "hard", "name": "Twitter/X"},
    {"url": "https://www.instagram.com", "tier": "hard", "name": "Instagram"},
    {"url": "https://www.facebook.com", "tier": "hard", "name": "Facebook"},
    {"url": "https://www.tiktok.com", "tier": "hard", "name": "TikTok"},
    {"url": "https://www.pinterest.com", "tier": "hard", "name": "Pinterest"},
    {"url": "https://www.yelp.com", "tier": "hard", "name": "Yelp"},
    {"url": "https://www.tripadvisor.com", "tier": "hard", "name": "TripAdvisor"},
    {"url": "https://www.booking.com", "tier": "hard", "name": "Booking.com"},
    {"url": "https://www.expedia.com", "tier": "hard", "name": "Expedia"},
    {"url": "https://www.airbnb.com", "tier": "hard", "name": "Airbnb"},
    {"url": "https://www.kayak.com", "tier": "hard", "name": "Kayak"},
    {"url": "https://www.washingtonpost.com", "tier": "hard", "name": "Washington Post"},
    {"url": "https://www.nytimes.com", "tier": "hard", "name": "NY Times"},
    {"url": "https://www.wsj.com", "tier": "hard", "name": "WSJ"},
    {"url": "https://www.bloomberg.com", "tier": "hard", "name": "Bloomberg"},
    {"url": "https://www.reuters.com", "tier": "hard", "name": "Reuters"},
    {"url": "https://www.theguardian.com", "tier": "hard", "name": "The Guardian"},
    {"url": "https://www.bbc.com", "tier": "hard", "name": "BBC"},
    {"url": "https://www.cnn.com", "tier": "hard", "name": "CNN"},
    {"url": "https://www.foxnews.com", "tier": "hard", "name": "Fox News"},
    {"url": "https://www.cnbc.com", "tier": "hard", "name": "CNBC"},
    {"url": "https://www.forbes.com", "tier": "hard", "name": "Forbes"},
    {"url": "https://www.businessinsider.com", "tier": "hard", "name": "Business Insider"},
    {"url": "https://www.vice.com", "tier": "hard", "name": "Vice"},
    {"url": "https://www.wired.com", "tier": "hard", "name": "Wired"},
    {"url": "https://www.techcrunch.com", "tier": "hard", "name": "TechCrunch"},
    {"url": "https://www.theverge.com", "tier": "hard", "name": "The Verge"},
    {"url": "https://www.arstechnica.com", "tier": "hard", "name": "Ars Technica"},
    {"url": "https://www.tumblr.com", "tier": "hard", "name": "Tumblr"},
    {"url": "https://www.trulia.com", "tier": "hard", "name": "Trulia"},
    {"url": "https://www.monster.com", "tier": "hard", "name": "Monster"},
    {"url": "https://www.ziprecruiter.com", "tier": "hard", "name": "ZipRecruiter"},
    {"url": "https://www.priceline.com", "tier": "hard", "name": "Priceline"},
    # ── Additional 20 sites for expanded coverage ────────────
    {"url": "https://www.samsung.com", "tier": "medium", "name": "Samsung"},
    {"url": "https://www.dell.com", "tier": "medium", "name": "Dell"},
    {"url": "https://www.hp.com", "tier": "medium", "name": "HP"},
    {"url": "https://www.lenovo.com", "tier": "medium", "name": "Lenovo"},
    {"url": "https://www.uber.com", "tier": "medium", "name": "Uber"},
    {"url": "https://www.lyft.com", "tier": "medium", "name": "Lyft"},
    {"url": "https://www.spotify.com", "tier": "medium", "name": "Spotify"},
    {"url": "https://www.netflix.com", "tier": "medium", "name": "Netflix"},
    {"url": "https://www.discord.com", "tier": "medium", "name": "Discord"},
    {"url": "https://www.slack.com", "tier": "medium", "name": "Slack"},
    {"url": "https://www.figma.com", "tier": "medium", "name": "Figma"},
    {"url": "https://www.notion.so", "tier": "medium", "name": "Notion"},
    {"url": "https://www.trello.com", "tier": "medium", "name": "Trello"},
    {"url": "https://www.dropbox.com", "tier": "medium", "name": "Dropbox"},
    {"url": "https://www.box.com", "tier": "medium", "name": "Box"},
    {"url": "https://www.nike.com", "tier": "hard", "name": "Nike"},
    {"url": "https://www.adidas.com", "tier": "hard", "name": "Adidas"},
    {"url": "https://www.twitch.tv", "tier": "hard", "name": "Twitch"},
    {"url": "https://www.snapchat.com", "tier": "hard", "name": "Snapchat"},
    {"url": "https://www.whatsapp.com", "tier": "hard", "name": "WhatsApp"},
]


class TestConfig:
    """Minimal config adapter for AgentBrowser."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val = self._data
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return default
            if val is None:
                return default
        return val

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        d = self._data
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = value


async def test_single_site(
    browser: AgentBrowser,
    site: Dict[str, Any],
    index: int,
    total: int,
) -> Dict[str, Any]:
    url = site["url"]
    name = site["name"]
    tier = site["tier"]

    logger.info(f"[{index}/{total}] Testing: {name} ({tier}) -> {url}")
    start = time.time()

    try:
        result = await browser.navigate(url, retries=2, warmup=False)
        elapsed = round(time.time() - start, 2)

        status = result.get("status", "unknown")
        status_code = result.get("status_code", 0)
        title = result.get("title", "")
        blocked = result.get("block_report") is not None
        cf_bypassed = result.get("cf_bypassed", False)
        passed = status == "success" and not blocked

        return {
            "index": index, "name": name, "url": url, "tier": tier,
            "passed": passed, "status": status, "status_code": status_code,
            "title": title[:80] if title else "",
            "blocked": blocked, "cf_bypassed": cf_bypassed,
            "time_seconds": elapsed, "attempt": result.get("attempt", 1),
            "error": result.get("error", ""),
        }
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        logger.error(f"[{index}/{total}] Exception for {name}: {e}")
        return {
            "index": index, "name": name, "url": url, "tier": tier,
            "passed": False, "status": "error", "status_code": 0,
            "title": "", "blocked": False, "cf_bypassed": False,
            "time_seconds": elapsed, "attempt": 0, "error": str(e)[:200],
        }


async def run_tests() -> None:
    config = TestConfig({
        "browser": {
            "headless": True,
            "user_agent": None,
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "captcha_auto_solve": False,
            "tls_proxy_enabled": False,
            "proxy_rotation_enabled": False,
            "proxy_file": None,
            "proxy_api_url": None,
            "proxy_api_key": None,
            "firefox_fallback": False,
        },
        "session": {"max_concurrent": 3, "timeout_minutes": 15},
    })

    logger.info("=" * 70)
    logger.info("Agent-OS 100-Website Stealth Test Suite")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("=" * 70)

    browser = AgentBrowser(config)
    logger.info("Starting browser...")
    await browser.start()
    logger.info("Browser started. Beginning tests...")

    results: List[Dict[str, Any]] = []
    total = len(WEBSITES)

    for i, site in enumerate(WEBSITES, 1):
        result = await test_single_site(browser, site, i, total)
        results.append(result)
        await asyncio.sleep(1.0)

    await browser.stop()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(f"stress_test_results_{timestamp}.json")

    tier_stats: Dict[str, Dict[str, int]] = {}
    for r in results:
        tier = r["tier"]
        if tier not in tier_stats:
            tier_stats[tier] = {"total": 0, "passed": 0, "blocked": 0}
        tier_stats[tier]["total"] += 1
        if r["passed"]:
            tier_stats[tier]["passed"] += 1
        if r["blocked"]:
            tier_stats[tier]["blocked"] += 1

    passed_total = sum(1 for r in results if r["passed"])
    blocked_total = sum(1 for r in results if r["blocked"])
    error_total = sum(1 for r in results if r["status"] == "error")
    avg_time = sum(r["time_seconds"] for r in results) / len(results) if results else 0

    report = {
        "timestamp": timestamp,
        "total_sites": total,
        "passed": passed_total,
        "blocked": blocked_total,
        "errors": error_total,
        "pass_rate": round(passed_total / total * 100, 1) if total else 0,
        "avg_time_seconds": round(avg_time, 2),
        "tier_breakdown": tier_stats,
        "results": results,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("")
    logger.info("=" * 70)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("=" * 70)
    logger.info(f"  Total sites:   {total}")
    logger.info(f"  Passed:        {passed_total} ({passed_total/total*100:.1f}%)")
    logger.info(f"  Blocked:       {blocked_total}")
    logger.info(f"  Errors:        {error_total}")
    logger.info(f"  Avg time:      {avg_time:.2f}s")
    logger.info("")
    for tier_name in ["easy", "medium", "hard"]:
        ts = tier_stats.get(tier_name, {"total": 0, "passed": 0, "blocked": 0})
        rate = ts["passed"] / ts["total"] * 100 if ts["total"] else 0
        logger.info(f"  {tier_name.upper():6s}:  {ts['passed']}/{ts['total']} passed ({rate:.0f}%)  |  {ts['blocked']} blocked")
    logger.info("")

    failures = [r for r in results if not r["passed"]]
    if failures:
        logger.info("FAILURES:")
        for r in failures:
            reason = r["error"][:60] if r["error"] else f"blocked (HTTP {r['status_code']})"
            logger.info(f"  X [{r['tier']}] {r['name']:20s} - {reason}")
    logger.info("")
    logger.info(f"Full report saved: {report_path}")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_tests())
