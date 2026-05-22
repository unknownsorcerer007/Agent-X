#!/usr/bin/env python3
"""
Agent-OS Human Capabilities Demo — Everything humans can do.
"""
import httpx
import json
import time
import base64
import re

TOKEN = "agent-os-main-2026"
BASE = "http://127.0.0.1:8001"

def cmd(command, **kwargs):
    payload = {"token": TOKEN, "command": command, **kwargs}
    r = httpx.post(f"{BASE}/command", json=payload, timeout=60)
    return r.json()

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def save_screenshot(name):
    r = cmd("screenshot")
    img = base64.b64decode(r['screenshot'])
    path = f"/root/.openclaw/workspace/Agent-OS/proof/demo_{name}.png"
    with open(path, "wb") as f:
        f.write(img)
    print(f"📸 Screenshot: demo_{name}.png ({len(img)//1024}KB)")

# ════════════════════════════════════════════════════════════
section("1️⃣  AMAZON — Search, Browse Products, View Details")
# ════════════════════════════════════════════════════════════

r = cmd("navigate", url="https://www.amazon.com")
print(f"✅ Navigated: {r['title'][:50]}")

# Click search box and type
r = cmd("click", selector="#twotabsearchtextbox")
print(f"✅ Clicked search: {r['status']}")

r = cmd("type", text="wireless headphones bluetooth")
print(f"✅ Typed search: {r['status']}")

r = cmd("press", key="Enter")
print(f"✅ Searched")
time.sleep(4)

# Get results
r = cmd("get-content")
text = r.get("text", "")
lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 20]
print(f"✅ Search results ({len(lines)} items):")
for line in lines[:5]:
    print(f"   📦 {line[:65]}")
save_screenshot("amazon_search")

# Click first product
r = cmd("click", selector="[data-component-type='s-search-result'] h2 a")
print(f"✅ Clicked product: {r['status']}")
time.sleep(3)

# Get product details
r = cmd("get-content")
text = r.get("text", "")
prices = re.findall(r'\$[\d,]+\.?\d*', text)
print(f"✅ Product page — prices: {prices[:5]}")
save_screenshot("amazon_product")

# Add to Cart
r = cmd("click", selector="#add-to-cart-button")
print(f"✅ Add to cart: {r['status']}")
time.sleep(2)
save_screenshot("amazon_cart")

# ════════════════════════════════════════════════════════════
section("2️⃣  GOOGLE — Search & Click Results")
# ════════════════════════════════════════════════════════════

r = cmd("navigate", url="https://www.google.com")
print(f"✅ Navigated: {r['title']}")

r = cmd("click", selector="[name='q']")
r = cmd("type", text="Agent-OS AI browser automation tool")
r = cmd("press", key="Enter")
time.sleep(3)

r = cmd("get-content")
text = r.get("text", "")
lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30][:5]
print(f"✅ Google results:")
for i, line in enumerate(lines, 1):
    print(f"   {i}. {line[:70]}")
save_screenshot("google_search")

# ════════════════════════════════════════════════════════════
section("3️⃣  WIKIPEDIA — Read, Extract Data & Structure")
# ════════════════════════════════════════════════════════════

r = cmd("navigate", url="https://en.wikipedia.org/wiki/Artificial_intelligence")
print(f"✅ Navigated: {r['title'][:50]}")

# Page analysis
r = cmd("page-summary")
a = r.get("analysis", {})
print(f"✅ Page Analysis:")
print(f"   Words: {a.get('word_count', '?')}")
print(f"   Headings: {len(a.get('headings', []))}")
for h in a.get("headings", [])[:6]:
    print(f"     H{h['level']}: {h['text'][:55]}")

# Tables
r = cmd("page-tables")
print(f"✅ Tables: {len(r.get('tables', []))}")

# SEO
r = cmd("page-seo")
seo = r.get("seo", {})
print(f"✅ SEO: {seo.get('score', '?')}/100")

# Emails
r = cmd("page-emails")
print(f"✅ Emails: {r.get('emails', [])[:3]}")

# Scroll down to read more
r = cmd("scroll", direction="down", amount=2000)
print(f"✅ Scrolled: {r['status']}")
save_screenshot("wikipedia_scrolled")

# ════════════════════════════════════════════════════════════
section("4️⃣  FORM FILLING — GitHub Login Page")
# ════════════════════════════════════════════════════════════

r = cmd("navigate", url="https://github.com/login")
print(f"✅ Navigated: {r['title'][:40]}")
time.sleep(2)

# Fill username
r = cmd("fill-form", fields={
    "#login_field": "demo_user@example.com",
    "#password": "MySecureP@ssw0rd!"
})
print(f"✅ Form filled: {r['status']} — {r.get('filled', [])}")
save_screenshot("github_login_filled")

# Don't actually submit - just show it's filled
print(f"✅ (Not submitting — demo only)")

# ════════════════════════════════════════════════════════════
section("5️⃣  MULTI-TAB — Open, Navigate, Switch Tabs")
# ════════════════════════════════════════════════════════════

r = cmd("tabs", action="list")
print(f"✅ Current tabs: {r.get('tabs', [])}")

cmd("tabs", action="new", tab_id="wiki-tab")
cmd("tabs", action="switch", tab_id="wiki-tab")
cmd("navigate", url="https://en.wikipedia.org/wiki/Main_Page")
print(f"✅ New tab opened: Wikipedia")

cmd("tabs", action="new", tab_id="news-tab")
cmd("tabs", action="switch", tab_id="news-tab")
cmd("navigate", url="https://news.ycombinator.com")
print(f"✅ Another tab: Hacker News")

r = cmd("tabs", action="list")
print(f"✅ All tabs: {r.get('tabs', [])}")

# Switch back
cmd("tabs", action="switch", tab_id="main")
print(f"✅ Back to main tab")

# ════════════════════════════════════════════════════════════
section("6️⃣  NETWORK CAPTURE — Monitor HTTP Requests")
# ════════════════════════════════════════════════════════════

cmd("network-start")
cmd("navigate", url="https://news.ycombinator.com")
time.sleep(3)

r = cmd("network-apis")
apis = r.get("apis", [])
print(f"✅ API endpoints discovered: {len(apis)}")
for api in apis[:5]:
    print(f"   🔗 {api.get('url', '?')[:60]}")

r = cmd("network-stop")
print(f"✅ Captured {r.get('total_captured', 0)} requests")
by_type = r.get("by_type", {})
for t, count in list(by_type.items())[:5]:
    print(f"   {t}: {count}")

# ════════════════════════════════════════════════════════════
section("7️⃣  MOBILE EMULATION — Browse as iPhone")
# ════════════════════════════════════════════════════════════

r = cmd("emulate-device", device="iphone_14")
print(f"✅ iPhone 14: {r.get('viewport', {})}")

r = cmd("navigate", url="https://www.amazon.com")
print(f"✅ Mobile Amazon: {r['title'][:40]}")
save_screenshot("mobile_amazon")

# List devices
r = cmd("list-devices")
devices = list(r.get("devices", {}).keys())
print(f"✅ Available devices: {devices}")

# Back to desktop
cmd("emulate-device", device="desktop_1080")
print(f"✅ Back to desktop")

# ════════════════════════════════════════════════════════════
section("8️⃣  TABLE EXTRACTION — Structured Data")
# ════════════════════════════════════════════════════════════

cmd("navigate", url="https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)")
time.sleep(2)

r = cmd("page-tables")
tables = r.get("tables", [])
print(f"✅ Extracted {len(tables)} tables")
if tables:
    t = tables[0]
    print(f"   First table: {t.get('rows', 0)} rows × {t.get('cols', 0)} cols")
    headers = t.get("headers", [])
    print(f"   Headers: {headers[:5]}")

# ════════════════════════════════════════════════════════════
section("9️⃣  SESSION SAVE/RESTORE — Persistent State")
# ════════════════════════════════════════════════════════════

cmd("navigate", url="https://github.com")
time.sleep(2)

r = cmd("save-session", name="github-demo")
print(f"✅ Saved: {r['name']} ({r.get('cookies', 0)} cookies, pages: {r.get('pages', [])})")

r = cmd("list-sessions")
print(f"✅ Sessions: {[s['name'] for s in r.get('sessions', [])]}")

# ════════════════════════════════════════════════════════════
section("🔟  COOKIE MANAGEMENT — Get & Set Cookies")
# ════════════════════════════════════════════════════════════

cmd("navigate", url="https://www.google.com")
time.sleep(2)

r = cmd("get-cookies")
cookies = r.get("cookies", [])
print(f"✅ Cookies: {len(cookies)}")
for c in cookies[:3]:
    print(f"   🍪 {c.get('name', '?')}: {c.get('value', '?')[:20]}...")

# Set a custom cookie
r = cmd("set-cookie", name="agent_test", value="hello_from_agent_os")
print(f"✅ Set cookie: {r['status']}")

r = cmd("get-cookies")
print(f"✅ Total cookies now: {r.get('count', 0)}")

# ════════════════════════════════════════════════════════════
section("🎉 SUMMARY — Everything Humans Can Do")
# ════════════════════════════════════════════════════════════

print(f"""
  ✅ Browse any website (Amazon, Google, Wikipedia, GitHub...)
  ✅ Search for products & click results
  ✅ Add items to cart
  ✅ Fill login forms with typed input
  ✅ Manage multiple tabs (open, switch, close)
  ✅ Capture all network requests
  ✅ Emulate mobile devices (iPhone, Galaxy, Pixel)
  ✅ Extract tables, emails, phone numbers
  ✅ Save & restore browser sessions
  ✅ Get & set cookies
  ✅ Scroll, click, type, press keys
  ✅ Take screenshots of everything
  ✅ Run JavaScript in pages
  ✅ Analyze page SEO & accessibility
  ✅ Workflows — chain multiple actions
  ✅ Smart finder — click by visible text (no selectors)
""")
