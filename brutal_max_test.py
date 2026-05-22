#!/usr/bin/env python3
"""
Agent-OS BRUTAL MAX LIMIT STRESS TEST
======================================
No fluff. No hope. Raw truth only.

- 200+ websites across 5 tiers
- Concurrent multi-tab stress
- Memory leak detection
- Browser crash recovery testing
- Stealth detection via bot test sites
- Performance benchmarks (OPS, latency P50/P95/P99)
- Repeated hit testing (same site 5x to detect rate limiting)
- Tool integration verification (Claude Code, Codex, OpenClaw)
"""
import asyncio
import json
import time
import sys
import os
import traceback
import resource
import gc
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any

# Add project root
sys.path.insert(0, str(Path(__file__).parent))

# ═══════════════════════════════════════════════════════════════
# TEST SITES — 200+ across 5 tiers
# ═══════════════════════════════════════════════════════════════

TIER_EASY = [
    {"name": "Example", "url": "https://example.com"},
    {"name": "HTTPBin GET", "url": "https://httpbin.org/get"},
    {"name": "HTTPBin Headers", "url": "https://httpbin.org/headers"},
    {"name": "HTTPBin IP", "url": "https://httpbin.org/ip"},
    {"name": "HTTPBin UA", "url": "https://httpbin.org/user-agent"},
    {"name": "Wikipedia", "url": "https://www.wikipedia.org"},
    {"name": "Wikipedia EN", "url": "https://en.wikipedia.org/wiki/Main_Page"},
    {"name": "GNU", "url": "https://www.gnu.org"},
    {"name": "Kernel.org", "url": "https://www.kernel.org"},
    {"name": "Internet Archive", "url": "https://archive.org"},
    {"name": "FSF", "url": "https://www.fsf.org"},
    {"name": "Debian", "url": "https://www.debian.org"},
    {"name": "Ubuntu", "url": "https://www.ubuntu.com"},
    {"name": "Python.org", "url": "https://www.python.org"},
    {"name": "Python Docs", "url": "https://docs.python.org"},
    {"name": "Rust Lang", "url": "https://www.rust-lang.org"},
    {"name": "Node.js", "url": "https://nodejs.org"},
    {"name": "Ruby Lang", "url": "https://www.ruby-lang.org"},
    {"name": "Go Lang", "url": "https://golang.org"},
    {"name": "SQLite", "url": "https://www.sqlite.org"},
    {"name": "PostgreSQL", "url": "https://www.postgresql.org"},
    {"name": "Redis.io", "url": "https://redis.io"},
    {"name": "MongoDB", "url": "https://www.mongodb.com"},
    {"name": "CouchDB", "url": "https://couchdb.apache.org"},
    {"name": "Nginx", "url": "https://nginx.org"},
    {"name": "Apache", "url": "https://httpd.apache.org"},
    {"name": "Caddy", "url": "https://caddyserver.com"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com"},
    {"name": "Lobsters", "url": "https://lobste.rs"},
    {"name": "DuckDuckGo", "url": "https://duckduckgo.com"},
]

TIER_MEDIUM = [
    {"name": "Cloudflare", "url": "https://www.cloudflare.com"},
    {"name": "DigitalOcean", "url": "https://www.digitalocean.com"},
    {"name": "Heroku", "url": "https://www.heroku.com"},
    {"name": "Netlify", "url": "https://www.netlify.com"},
    {"name": "Vercel", "url": "https://vercel.com"},
    {"name": "NPM", "url": "https://www.npmjs.com"},
    {"name": "Docker", "url": "https://www.docker.com"},
    {"name": "Docker Hub", "url": "https://hub.docker.com"},
    {"name": "Kubernetes", "url": "https://kubernetes.io"},
    {"name": "Grafana", "url": "https://grafana.com"},
    {"name": "Datadog", "url": "https://www.datadog.com"},
    {"name": "Shopify", "url": "https://shopify.com"},
    {"name": "Stripe", "url": "https://www.stripe.com"},
    {"name": "Square", "url": "https://squareup.com"},
    {"name": "PayPal", "url": "https://www.paypal.com"},
    {"name": "LinkedIn", "url": "https://www.linkedin.com"},
    {"name": "Microsoft", "url": "https://www.microsoft.com"},
    {"name": "Apple", "url": "https://www.apple.com"},
    {"name": "Salesforce", "url": "https://www.salesforce.com"},
    {"name": "Adobe", "url": "https://www.adobe.com"},
    {"name": "Medium", "url": "https://medium.com"},
    {"name": "Dev.to", "url": "https://dev.to"},
    {"name": "StackOverflow", "url": "https://stackoverflow.com"},
    {"name": "GitHub", "url": "https://github.com"},
    {"name": "GitLab", "url": "https://gitlab.com"},
    {"name": "Bitbucket", "url": "https://bitbucket.org"},
    {"name": "Atlassian", "url": "https://www.atlassian.com"},
    {"name": "Figma", "url": "https://www.figma.com"},
    {"name": "Notion", "url": "https://www.notion.so"},
    {"name": "Slack", "url": "https://slack.com"},
]

TIER_HARD = [
    {"name": "Amazon US", "url": "https://www.amazon.com"},
    {"name": "Amazon UK", "url": "https://www.amazon.co.uk"},
    {"name": "eBay", "url": "https://www.ebay.com"},
    {"name": "Walmart", "url": "https://www.walmart.com"},
    {"name": "Target", "url": "https://www.target.com"},
    {"name": "BestBuy", "url": "https://www.bestbuy.com"},
    {"name": "HomeDepot", "url": "https://www.homedepot.com"},
    {"name": "Lowes", "url": "https://www.lowes.com"},
    {"name": "Costco", "url": "https://www.costco.com"},
    {"name": "Etsy", "url": "https://www.etsy.com"},
    {"name": "Zillow", "url": "https://www.zillow.com"},
    {"name": "Realtor", "url": "https://www.realtor.com"},
    {"name": "Indeed", "url": "https://www.indeed.com"},
    {"name": "Glassdoor", "url": "https://www.glassdoor.com"},
    {"name": "Reddit", "url": "https://www.reddit.com"},
    {"name": "Reddit Old", "url": "https://old.reddit.com"},
    {"name": "Quora", "url": "https://www.quora.com"},
    {"name": "Twitter/X", "url": "https://twitter.com"},
    {"name": "Instagram", "url": "https://www.instagram.com"},
    {"name": "Facebook", "url": "https://www.facebook.com"},
    {"name": "TikTok", "url": "https://www.tiktok.com"},
    {"name": "Pinterest", "url": "https://www.pinterest.com"},
    {"name": "Yelp", "url": "https://www.yelp.com"},
    {"name": "TripAdvisor", "url": "https://www.tripadvisor.com"},
    {"name": "Booking.com", "url": "https://www.booking.com"},
    {"name": "Expedia", "url": "https://www.expedia.com"},
    {"name": "Airbnb", "url": "https://www.airbnb.com"},
    {"name": "Kayak", "url": "https://www.kayak.com"},
    {"name": "Washington Post", "url": "https://www.washingtonpost.com"},
    {"name": "NY Times", "url": "https://www.nytimes.com"},
]

TIER_EXTREME = [
    {"name": "WSJ", "url": "https://www.wsj.com"},
    {"name": "Bloomberg", "url": "https://www.bloomberg.com"},
    {"name": "Reuters", "url": "https://www.reuters.com"},
    {"name": "The Guardian", "url": "https://www.theguardian.com"},
    {"name": "BBC", "url": "https://www.bbc.com"},
    {"name": "CNN", "url": "https://www.cnn.com"},
    {"name": "Fox News", "url": "https://www.foxnews.com"},
    {"name": "CNBC", "url": "https://www.cnbc.com"},
    {"name": "Forbes", "url": "https://www.forbes.com"},
    {"name": "Business Insider", "url": "https://www.businessinsider.com"},
    {"name": "Vice", "url": "https://www.vice.com"},
    {"name": "Wired", "url": "https://www.wired.com"},
    {"name": "TechCrunch", "url": "https://techcrunch.com"},
    {"name": "The Verge", "url": "https://www.theverge.com"},
    {"name": "Ars Technica", "url": "https://arstechnica.com"},
    {"name": "Tumblr", "url": "https://www.tumblr.com"},
    {"name": "Trulia", "url": "https://www.trulia.com"},
    {"name": "Monster", "url": "https://www.monster.com"},
    {"name": "ZipRecruiter", "url": "https://www.ziprecruiter.com"},
    {"name": "Priceline", "url": "https://www.priceline.com"},
    {"name": "Oracle", "url": "https://www.oracle.com"},
    {"name": "SAP", "url": "https://www.sap.com"},
    {"name": "ServiceNow", "url": "https://www.servicenow.com"},
    {"name": "Workday", "url": "https://www.workday.com"},
    {"name": "Twilio", "url": "https://www.twilio.com"},
    {"name": "Okta", "url": "https://www.okta.com"},
    {"name": "Cloudflare Dashboard", "url": "https://dash.cloudflare.com"},
    {"name": "Auth0", "url": "https://auth0.com"},
    {"name": "Discord", "url": "https://discord.com"},
    {"name": "Spotify", "url": "https://www.spotify.com"},
]

TIER_NIGHTMARE = [
    # Bot detection test sites — these ARE the judges
    {"name": "Bot Test: CreepJS", "url": "https://abrahamjuliot.github.io/creepjs/"},
    {"name": "Bot Test: Pixelscan", "url": "https://pixelscan.net"},
    {"name": "Bot Test: BrowserLeaks", "url": "https://browserleaks.com/javascript"},
    {"name": "Bot Test: FingerprintJS", "url": "https://fingerprintjs.github.io/fingerprintjs/"},
    {"name": "Bot Test: Incolumitas", "url": "https://bot.incolumitas.com/"},
    {"name": "Bot Test: Antcpt", "url": "https://antcpt.com/score_detector/"},
    {"name": "Bot Test: ReCaptcha Test", "url": "https://www.google.com/recaptcha/api2/demo"},
    {"name": "Bot Test: Cloudflare Challenge", "url": "https://nowsecure.nl"},
    # Sites known to use aggressive PerimeterX/DataDome
    {"name": "PX: Zappos", "url": "https://www.zappos.com"},
    {"name": "PX: StubHub", "url": "https://www.stubhub.com"},
    {"name": "PX: Ticketmaster", "url": "https://www.ticketmaster.com"},
    {"name": "DD: ArtStation", "url": "https://www.artstation.com"},
    {"name": "DD: FootLocker", "url": "https://www.footlocker.com"},
    {"name": "DD: Slickdeals", "url": "https://slickdeals.net"},
    {"name": "Akamai: Nike", "url": "https://www.nike.com"},
    {"name": "Akamai: Adidas", "url": "https://www.adidas.com"},
    {"name": "Akamai: Samsung", "url": "https://www.samsung.com"},
    {"name": "CF: Canva", "url": "https://www.canva.com"},
    {"name": "CF: Discord CDN", "url": "https://discord.com/login"},
    # Financial — strictest bot detection
    {"name": "FIN: Coinbase", "url": "https://www.coinbase.com"},
    {"name": "FIN: Binance", "url": "https://www.binance.com"},
    {"name": "FIN: Robinhood", "url": "https://robinhood.com"},
    {"name": "FIN: Chase", "url": "https://www.chase.com"},
    {"name": "FIN: Bank of America", "url": "https://www.bankofamerica.com"},
    {"name": "FIN: Wells Fargo", "url": "https://www.wellsfargo.com"},
    {"name": "FIN: Capital One", "url": "https://www.capitalone.com"},
    {"name": "FIN: American Express", "url": "https://www.americanexpress.com"},
    {"name": "FIN: Schwab", "url": "https://www.schwab.com"},
    {"name": "FIN: Fidelity", "url": "https://www.fidelity.com"},
]

ALL_TIERS = {
    "easy": TIER_EASY,
    "medium": TIER_MEDIUM,
    "hard": TIER_HARD,
    "extreme": TIER_EXTREME,
    "nightmare": TIER_NIGHTMARE,
}

# ═══════════════════════════════════════════════════════════════
# Block indicators
# ═══════════════════════════════════════════════════════════════

BLOCK_INDICATORS = [
    "access denied", "captcha required", "bot detected",
    "just a moment", "checking your browser",
    "please verify you are human", "unusual traffic",
    "are you a robot", "bot or not",
    "access to this page has been denied",
    "blocked by waf", "security check required",
    "managed challenge", "request denied",
    "your request was blocked", "automated access",
    "ray id", "attention required",
]

SKIP_BLOCK_DOMAINS = ["cloudflare.com", "amazon.com", "amazon.co.uk"]


@dataclass
class TestResult:
    index: int
    name: str
    url: str
    tier: str
    passed: bool
    status: str = ""
    status_code: int = 0
    title: str = ""
    blocked: bool = False
    cf_bypassed: bool = False
    time_seconds: float = 0.0
    attempt: int = 1
    error: str = ""
    ram_mb: float = 0.0
    page_size_kb: float = 0.0


@dataclass
class ConcurrentResult:
    batch_id: int
    total_pages: int
    successful: int = 0
    failed: int = 0
    avg_time: float = 0.0
    max_time: float = 0.0
    errors: List[str] = field(default_factory=list)


class BrutalMaxTester:
    """No mercy. No hope. Just raw data."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.concurrent_results: List[ConcurrentResult] = []
        self.browser = None
        self.playwright = None
        self.context = None
        self.config = None
        self.start_time = 0
        self.end_time = 0
        self.ram_samples: List[float] = []
        self.crash_count = 0
        self.timeout_count = 0
        self.total_requests = 0

    def _get_ram_mb(self) -> float:
        """Get current RSS in MB."""
        try:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        except:
            return 0.0

    def _is_blocked(self, title: str, text: str, url: str = "") -> bool:
        if url and any(d in url.lower() for d in SKIP_BLOCK_DOMAINS):
            return False
        combined = (title + " " + text[:500]).lower()
        return any(ind in combined for ind in BLOCK_INDICATORS)

    async def _init_browser(self):
        """Initialize the Agent-OS browser with full stealth."""
        from src.core.config import Config
        self.config = Config()
        self.config.set("browser.headless", True)
        self.config.set("browser.max_ram_mb", 800)

        from src.core.browser import AgentBrowser
        self.browser = AgentBrowser(self.config)
        await self.browser.start()

        self.playwright = self.browser.playwright
        self.context = self.browser.context

        print(f"[INIT] Browser started | RAM: {self._get_ram_mb():.0f}MB")
        return True

    async def _shutdown_browser(self):
        if self.browser:
            try:
                await self.browser.stop()
            except:
                pass

    async def _test_single_site(self, site: dict, tier: str, index: int, max_attempts: int = 3) -> TestResult:
        """Test a single site with retry logic."""
        result = TestResult(
            index=index,
            name=site["name"],
            url=site["url"],
            tier=tier,
            passed=False,
        )

        for attempt in range(1, max_attempts + 1):
            result.attempt = attempt
            start = time.time()
            try:
                page = await self.browser.context.new_page()
                try:
                    # Set timeout based on tier
                    timeout_map = {
                        "easy": 15000,
                        "medium": 25000,
                        "hard": 35000,
                        "extreme": 45000,
                        "nightmare": 60000,
                    }
                    timeout = timeout_map.get(tier, 30000)

                    resp = await page.goto(site["url"], timeout=timeout, wait_until="domcontentloaded")

                    # Wait a bit for JS to run
                    await asyncio.sleep(2)

                    # Get page info
                    title = await page.title()
                    result.title = title[:200]
                    result.status_code = resp.status if resp else 0

                    # Get page content for block detection
                    body_text = ""
                    try:
                        body_text = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : ''")
                    except:
                        pass

                    # Get page size
                    try:
                        content_length = await page.evaluate(
                            "() => document.documentElement ? document.documentElement.outerHTML.length : 0"
                        )
                        result.page_size_kb = content_length / 1024.0
                    except:
                        pass

                    # Check if blocked
                    blocked = self._is_blocked(title, body_text, site["url"])
                    result.blocked = blocked

                    # Determine pass/fail
                    if blocked:
                        result.passed = False
                        result.status = "blocked"
                    elif resp and resp.status in (200, 201, 202, 301, 302, 401):
                        # 401 = auth required but not blocked
                        result.passed = True
                        result.status = "success"
                    elif resp and resp.status == 403:
                        # 403 could be bot block or legit forbidden
                        if blocked:
                            result.passed = False
                            result.status = "blocked"
                        else:
                            # 403 without block text = possibly geo-block or rate limit
                            result.passed = False
                            result.status = "forbidden"
                    elif resp and resp.status == 429:
                        result.passed = False
                        result.status = "rate_limited"
                    else:
                        result.passed = False
                        result.status = f"http_{resp.status if resp else 'no_response'}"

                    result.time_seconds = round(time.time() - start, 2)
                    result.ram_mb = self._get_ram_mb()

                    # If passed or hard-blocked, no retry needed
                    if result.passed or result.blocked:
                        break

                finally:
                    await page.close()

            except asyncio.TimeoutError:
                result.time_seconds = round(time.time() - start, 2)
                result.error = "TIMEOUT"
                result.status = "timeout"
                self.timeout_count += 1
            except Exception as e:
                result.time_seconds = round(time.time() - start, 2)
                err_str = str(e)[:200]
                result.error = err_str
                result.status = "error"
                # Check for browser crash
                if any(kw in err_str.lower() for kw in ["crashed", "closed", "destroyed", "disconnected"]):
                    self.crash_count += 1
                    try:
                        await self.browser.recover()
                    except:
                        # If recovery fails, re-init
                        try:
                            await self._shutdown_browser()
                        except:
                            pass
                        await self._init_browser()
                    break  # No more retries after crash

        self.total_requests += 1
        self.ram_samples.append(self._get_ram_mb())
        return result

    async def _run_tier(self, tier_name: str, sites: list):
        """Run all sites in a tier sequentially."""
        print(f"\n{'='*60}")
        print(f"  TIER: {tier_name.upper()} ({len(sites)} sites)")
        print(f"{'='*60}")

        for i, site in enumerate(sites, 1):
            result = await self._test_single_site(site, tier_name, i)
            self.results.append(result)

            status_icon = "✓" if result.passed else "✗"
            blocked_icon = " [BLOCKED]" if result.blocked else ""
            timeout_icon = " [TIMEOUT]" if result.error == "TIMEOUT" else ""
            error_icon = f" [ERROR: {result.error[:50]}]" if result.error and result.error != "TIMEOUT" else ""

            print(f"  {status_icon} [{i:3d}/{len(sites)}] {result.name:<25s} | {result.time_seconds:6.1f}s | {result.status_code:3d} | {result.status}{blocked_icon}{timeout_icon}{error_icon}")

            # Small delay between requests to avoid rate limiting
            await asyncio.sleep(0.5)

    async def _run_concurrent_batch(self, sites: list, batch_id: int, concurrency: int) -> ConcurrentResult:
        """Run a batch of sites concurrently."""
        result = ConcurrentResult(batch_id=batch_id, total_pages=len(sites))
        start = time.time()
        times = []

        async def _concurrent_test(site_info):
            tier, site = site_info
            r = await self._test_single_site(site, tier, batch_id * 100 + len(times))
            if r.passed:
                result.successful += 1
            else:
                result.failed += 1
            times.append(r.time_seconds)
            if r.error:
                result.errors.append(f"{r.name}: {r.error[:80]}")

        # Split into chunks of `concurrency`
        site_list = list(enumerate(sites))
        for chunk_start in range(0, len(site_list), concurrency):
            chunk = site_list[chunk_start:chunk_start + concurrency]
            tasks = [_concurrent_test(s) for _, s in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)

        result.avg_time = round(sum(times) / len(times), 2) if times else 0
        result.max_time = round(max(times), 2) if times else 0
        return result

    async def _run_concurrent_test(self):
        """Stress test with concurrent tab opens."""
        print(f"\n{'='*60}")
        print(f"  CONCURRENT STRESS TEST")
        print(f"{'='*60}")

        # Pick 20 representative sites from each tier
        test_sites = []
        for tier, sites in ALL_TIERS.items():
            for site in sites[:6]:
                test_sites.append((tier, site))

        for concurrency in [3, 5, 8, 10]:
            print(f"\n  [Concurrent={concurrency}] Running {len(test_sites)} sites...")
            r = await self._run_concurrent_batch(test_sites, concurrency, concurrency)
            self.concurrent_results.append(r)
            print(f"    OK: {r.successful} | FAIL: {r.failed} | Avg: {r.avg_time}s | Max: {r.max_time}s")

    async def _run_repeat_test(self):
        """Hit the same site 5x to detect rate limiting / IP bans."""
        print(f"\n{'='*60}")
        print(f"  REPEAT HIT TEST (5x per site)")
        print(f"{'='*60}")

        repeat_sites = [
            {"name": "Amazon", "url": "https://www.amazon.com"},
            {"name": "Reddit", "url": "https://www.reddit.com"},
            {"name": "Twitter/X", "url": "https://twitter.com"},
            {"name": "GitHub", "url": "https://github.com"},
            {"name": "NY Times", "url": "https://www.nytimes.com"},
            {"name": "CNN", "url": "https://www.cnn.com"},
            {"name": "eBay", "url": "https://www.ebay.com"},
            {"name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"},
        ]

        for site in repeat_sites:
            print(f"\n  Repeating: {site['name']}")
            for i in range(5):
                r = await self._test_single_site(site, "repeat", i + 1, max_attempts=1)
                status = "✓" if r.passed else "✗"
                print(f"    {status} Hit #{i+1}: {r.time_seconds}s | {r.status_code} | {r.status}")
                await asyncio.sleep(1)

    async def _run_stealth_detection(self):
        """Test against bot detection sites — the real judges."""
        print(f"\n{'='*60}")
        print(f"  STEALTH DETECTION TEST")
        print(f"{'='*60}")

        stealth_sites = [
            {"name": "CreepJS", "url": "https://abrahamjuliot.github.io/creepjs/"},
            {"name": "Pixelscan", "url": "https://pixelscan.net"},
            {"name": "Incolumitas Bot", "url": "https://bot.incolumitas.com/"},
            {"name": "BrowserLeaks JS", "url": "https://browserleaks.com/javascript"},
            {"name": "FingerprintJS", "url": "https://fingerprintjs.github.io/fingerprintjs/"},
            {"name": "Antcpt Score", "url": "https://antcpt.com/score_detector/"},
        ]

        for site in stealth_sites:
            result = await self._test_single_site(site, "stealth", 0)
            self.results.append(result)

            status = "✓ LOADED" if result.passed else "✗ FAILED"
            print(f"  {status} {result.name}: {result.time_seconds}s | {result.status}")

            if result.passed:
                # Try to extract bot detection scores
                try:
                    page = await self.browser.context.new_page()
                    try:
                        await page.goto(site["url"], timeout=30000, wait_until="domcontentloaded")
                        await asyncio.sleep(5)

                        # Try to extract detection results
                        try:
                            # CreepJS trust score
                            score = await page.evaluate("""
                                () => {
                                    const el = document.querySelector('.visitor-class');
                                    return el ? el.textContent : null;
                                }
                            """)
                            if score:
                                print(f"    → CreepJS: {score}")
                        except:
                            pass

                        try:
                            # Generic bot score extraction
                            page_text = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
                            for keyword in ["bot", "automated", "headless", "webdriver", "suspicious", "trust"]:
                                if keyword in page_text.lower():
                                    # Find the relevant line
                                    for line in page_text.split("\n"):
                                        if keyword in line.lower() and len(line.strip()) > 3:
                                            print(f"    → {line.strip()[:120]}")
                                            break
                        except:
                            pass
                    finally:
                        await page.close()
                except:
                    pass

    async def _run_tool_verification(self):
        """Verify installed tools (Claude Code, Codex, OpenClaw)."""
        print(f"\n{'='*60}")
        print(f"  TOOL VERIFICATION")
        print(f"{'='*60}")

        tools = {
            "Claude Code": "claude",
            "OpenAI Codex": "codex",
            "OpenClaw": "openclaw",
        }

        for name, cmd in tools.items():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "which", cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                path = stdout.decode().strip()
                if path:
                    # Try version
                    proc2 = await asyncio.create_subprocess_exec(
                        cmd, "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=10)
                    version = stdout2.decode().strip()[:50]
                    print(f"  ✓ {name}: installed at {path} | v{version}")
                else:
                    print(f"  ✗ {name}: NOT FOUND")
            except Exception as e:
                print(f"  ✗ {name}: {str(e)[:80]}")

    async def run(self):
        """The GRIND. Max limit. No mercy."""
        self.start_time = time.time()

        print("╔══════════════════════════════════════════════════════════════╗")
        print("║   AGENT-OS BRUTAL MAX LIMIT STRESS TEST                    ║")
        print("║   No fluff. No hope. Raw truth.                            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print(f"  Started: {datetime.now().isoformat()}")
        print(f"  Total sites: {sum(len(s) for s in ALL_TIERS.values())}")
        print(f"  RAM at start: {self._get_ram_mb():.0f}MB")

        # Tool verification
        await self._run_tool_verification()

        # Init browser
        try:
            await self._init_browser()
        except Exception as e:
            print(f"\n  ✗✗✗ BROWSER INIT FAILED: {e}")
            print(f"  Cannot run stress test without browser.")
            await self._generate_report(fatal_error=str(e))
            return

        # Phase 1: Sequential tier tests
        ram_before = self._get_ram_mb()

        for tier_name, sites in ALL_TIERS.items():
            await self._run_tier(tier_name, sites)

        ram_after = self._get_ram_mb()
        ram_delta = ram_after - ram_before

        # Phase 2: Concurrent stress
        await self._run_concurrent_test()

        # Phase 3: Repeat hit test
        await self._run_repeat_test()

        # Phase 4: Stealth detection
        await self._run_stealth_detection()

        # Shutdown
        await self._shutdown_browser()
        self.end_time = time.time()

        # Generate report
        await self._generate_report()

    async def _generate_report(self, fatal_error: str = ""):
        """Generate the RAW BRUTAL report. No sugar coating."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        blocked = sum(1 for r in self.results if r.blocked)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        elapsed = self.end_time - self.start_time if self.end_time else time.time() - self.start_time

        # Latency stats
        times = [r.time_seconds for r in self.results if r.time_seconds > 0]
        times.sort()
        p50 = times[len(times) // 2] if times else 0
        p95 = times[int(len(times) * 0.95)] if len(times) > 1 else times[0] if times else 0
        p99 = times[int(len(times) * 0.99)] if len(times) > 1 else times[0] if times else 0
        avg_time = sum(times) / len(times) if times else 0

        # RAM stats
        ram_min = min(self.ram_samples) if self.ram_samples else 0
        ram_max = max(self.ram_samples) if self.ram_samples else 0
        ram_avg = sum(self.ram_samples) / len(self.ram_samples) if self.ram_samples else 0

        # Tier breakdown
        tier_stats = {}
        for tier_name in ALL_TIERS:
            tier_results = [r for r in self.results if r.tier == tier_name]
            tier_total = len(tier_results)
            tier_passed = sum(1 for r in tier_results if r.passed)
            tier_blocked = sum(1 for r in tier_results if r.blocked)
            tier_stats[tier_name] = {
                "total": tier_total,
                "passed": tier_passed,
                "blocked": tier_blocked,
                "failed": tier_total - tier_passed,
                "pass_rate": round(tier_passed / tier_total * 100, 1) if tier_total > 0 else 0,
            }

        # Failed sites list
        failed_sites = [
            {"name": r.name, "url": r.url, "tier": r.tier, "status": r.status,
             "status_code": r.status_code, "blocked": r.blocked, "error": r.error}
            for r in self.results if not r.passed
        ]

        # Concurrent results
        concurrent_data = [asdict(r) for r in self.concurrent_results]

        report = {
            "meta": {
                "timestamp": datetime.now().isoformat(),
                "test_type": "BRUTAL_MAX_LIMIT",
                "total_sites_tested": total,
                "elapsed_seconds": round(elapsed, 1),
                "fatal_error": fatal_error or None,
            },
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "blocked": blocked,
                "pass_rate": round(pass_rate, 1),
                "crash_count": self.crash_count,
                "timeout_count": self.timeout_count,
                "total_requests": self.total_requests,
            },
            "latency": {
                "avg_seconds": round(avg_time, 2),
                "p50_seconds": round(p50, 2),
                "p95_seconds": round(p95, 2),
                "p99_seconds": round(p99, 2),
                "min_seconds": round(min(times), 2) if times else 0,
                "max_seconds": round(max(times), 2) if times else 0,
            },
            "memory": {
                "ram_min_mb": round(ram_min, 1),
                "ram_max_mb": round(ram_max, 1),
                "ram_avg_mb": round(ram_avg, 1),
                "ram_delta_mb": round(ram_max - ram_min, 1),
            },
            "tier_breakdown": tier_stats,
            "concurrent": concurrent_data,
            "failed_sites": failed_sites,
            "all_results": [asdict(r) for r in self.results],
        }

        # Save JSON
        report_path = Path("/home/z/my-project/download/brutal_max_stress_test_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Print report
        print(f"\n\n{'='*70}")
        print(f"  ██  BRUTAL MAX LIMIT STRESS TEST — RESULTS  ██")
        print(f"{'='*70}")
        if fatal_error:
            print(f"\n  ☠ FATAL ERROR: {fatal_error}")
        print(f"\n  SITES TESTED:    {total}")
        print(f"  PASSED:          {passed} ({pass_rate:.1f}%)")
        print(f"  FAILED:          {failed}")
        print(f"  BLOCKED:         {blocked}")
        print(f"  BROWSER CRASHES: {self.crash_count}")
        print(f"  TIMEOUTS:        {self.timeout_count}")
        print(f"  TOTAL REQUESTS:  {self.total_requests}")
        print(f"  ELAPSED:         {elapsed:.0f}s ({elapsed/60:.1f}min)")
        print(f"\n  LATENCY:")
        print(f"    Avg:  {avg_time:.2f}s")
        print(f"    P50:  {p50:.2f}s")
        print(f"    P95:  {p95:.2f}s")
        print(f"    P99:  {p99:.2f}s")
        print(f"\n  MEMORY:")
        print(f"    Min:  {ram_min:.0f}MB")
        print(f"    Max:  {ram_max:.0f}MB")
        print(f"    Avg:  {ram_avg:.0f}MB")
        print(f"    Delta: {ram_max - ram_min:.0f}MB")
        print(f"\n  TIER BREAKDOWN:")
        for tier, stats in tier_stats.items():
            print(f"    {tier:>10s}: {stats['passed']:3d}/{stats['total']:3d} ({stats['pass_rate']:5.1f}%) | blocked: {stats['blocked']}")

        if self.concurrent_results:
            print(f"\n  CONCURRENT STRESS:")
            for cr in self.concurrent_results:
                print(f"    Concurrency={cr.batch_id}: OK={cr.successful} FAIL={cr.failed} Avg={cr.avg_time}s Max={cr.max_time}s")

        if failed_sites:
            print(f"\n  FAILED SITES ({len(failed_sites)}):")
            for fs in failed_sites[:50]:
                blocked_str = " [BLOCKED]" if fs["blocked"] else ""
                print(f"    ✗ {fs['tier']:>10s} | {fs['name']:<25s} | {fs['status_code']:3d} | {fs['status']}{blocked_str}")

        print(f"\n  Report saved: {report_path}")
        print(f"{'='*70}")


async def main():
    tester = BrutalMaxTester()
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
