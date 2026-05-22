import asyncio
import os
import time
from src.core.browser import AgentBrowser

async def run_tests():
    print("Initializing AgentBrowser...")
    # Provide basic config
    config = {
        "browser.headless": True,
        "browser.proxy_rotation_enabled": False, # disable for test speed
        "browser.tls_proxy_enabled": False,
        "browser.firefox_fallback": False
    }
    
    browser_engine = AgentBrowser(config)
    await browser_engine.start()
    
    results = {}
    
    # Test 1: Sannysoft
    try:
        print("\n--- Test 1: Sannysoft Bot Test ---")
        page = browser_engine.page
        page.set_default_timeout(60000)
        
        await page.goto("https://bot.sannysoft.com/", wait_until="domcontentloaded", timeout=60000)
        print("Sannysoft loaded, waiting 5s for JS to execute...")
        await page.wait_for_timeout(5000) # let tests run
        
        # Extract results
        webdriver_passed = await page.evaluate("() => { const el = document.getElementById('webdriver-result'); return el ? el.classList.contains('passed') : false; }")
        phantom_passed = await page.evaluate("() => { const el = document.getElementById('phantom-result'); return el ? el.classList.contains('passed') : false; }")
        
        results["Sannysoft"] = {
            "webdriver_hidden": webdriver_passed,
            "phantom_hidden": phantom_passed
        }
        print(f"Sannysoft result: Webdriver Hidden: {webdriver_passed}")
        
        # Save screenshot
        await page.screenshot(path="sannysoft_result.png", full_page=True)
        print("Saved sannysoft_result.png")
    except Exception as e:
        print(f"Sannysoft failed: {e}")

    # Test 2: NowSecure (Cloudflare)
    try:
        print("\n--- Test 2: NowSecure (Cloudflare) ---")
        page = browser_engine.page
        await page.goto("https://nowsecure.nl/", wait_until="domcontentloaded", timeout=60000)
        print("NowSecure loaded, waiting 8s for CF challenge...")
        await page.wait_for_timeout(8000) # wait for CF challenge
        
        title = await page.title()
        cf_bypassed = "nowsecure.nl" in title.lower() and "just a moment" not in title.lower()
        
        results["NowSecure"] = {
            "cloudflare_bypassed": cf_bypassed,
            "title": title
        }
        print(f"Cloudflare bypass result: {cf_bypassed} (Title: {title})")
        await page.screenshot(path="cloudflare_result.png")
        print("Saved cloudflare_result.png")
    except Exception as e:
        print(f"NowSecure failed: {e}")

    # Test 3: CreepJS
    try:
        print("\n--- Test 3: CreepJS Advanced Fingerprinting ---")
        page = browser_engine.page
        await page.goto("https://abrahamjuliot.github.io/creepjs/", wait_until="domcontentloaded", timeout=60000)
        print("CreepJS loaded, waiting 15s for analysis...")
        await page.wait_for_timeout(15000) # CreepJS takes a while to calculate
        
        trust_score = await page.evaluate("""() => {
            const el = document.querySelector('.trust-score .score');
            return el ? el.innerText : 'Not found';
        }""")
        
        results["CreepJS"] = {
            "trust_score": trust_score
        }
        print(f"CreepJS Trust Score: {trust_score}")
        await page.screenshot(path="creepjs_result.png", full_page=True)
        print("Saved creepjs_result.png")
    except Exception as e:
        print(f"CreepJS failed: {e}")

    # Cleanup
    if browser_engine.browser:
        await browser_engine.browser.close()
    if browser_engine.playwright:
        await browser_engine.playwright.stop()
        
    print("\n--- FINAL TEST RESULTS ---")
    for k, v in results.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    asyncio.run(run_tests())
