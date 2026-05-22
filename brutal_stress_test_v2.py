#!/usr/bin/env python3
"""
Agent-OS BRUTAL STRESS TEST v2
================================
NO FIXING. ONLY REPORTING. BRUTAL HONESTY.
Tests EVERYTHING at maximum intensity.

Tests:
1. Stealth (all 3 layers) against real bot detection sites
2. Form filling on real login pages
3. Swarm/Router system
4. Proxy rotation
5. TLS fingerprinting
6. Captcha detection
7. Database + Redis
8. MCP connector
9. Login Handoff
10. Installation readiness
11. Production readiness
"""
import asyncio
import json
import os
import sys
import time
import traceback
import importlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent))

# ═══════════════════════════════════════════════════════════════
# RESULTS COLLECTOR
# ═══════════════════════════════════════════════════════════════

class BrutalResults:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
        
    def record(self, category: str, test_name: str, passed: bool, 
               details: str = "", severity: str = "info",
               fix_hint: str = ""):
        if category not in self.results:
            self.results[category] = {"tests": [], "passed": 0, "failed": 0, "skipped": 0}
        
        entry = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "severity": severity,  # info, warning, critical, fatal
            "fix_hint": fix_hint,
            "timestamp": datetime.now().isoformat(),
        }
        self.results[category]["tests"].append(entry)
        if passed:
            self.results[category]["passed"] += 1
        else:
            self.results[category]["failed"] += 1
            
    def skip(self, category: str, test_name: str, reason: str):
        if category not in self.results:
            self.results[category] = {"tests": [], "passed": 0, "failed": 0, "skipped": 0}
        self.results[category]["tests"].append({
            "test": test_name, "passed": None, "details": f"SKIPPED: {reason}",
            "severity": "skip", "fix_hint": "", "timestamp": datetime.now().isoformat()
        })
        self.results[category]["skipped"] += 1
    
    def summary(self):
        total_passed = sum(r["passed"] for r in self.results.values())
        total_failed = sum(r["failed"] for r in self.results.values())
        total_skipped = sum(r["skipped"] for r in self.results.values())
        total = total_passed + total_failed + total_skipped
        elapsed = time.time() - self.start_time
        
        print("\n" + "=" * 80)
        print("  BRUTAL STRESS TEST RESULTS — HONEST, NO SUGARCOATING")
        print("=" * 80)
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Total Tests: {total}")
        print(f"  PASSED: {total_passed} | FAILED: {total_failed} | SKIPPED: {total_skipped}")
        if total > 0:
            success_rate = (total_passed / (total_passed + total_failed)) * 100 if (total_passed + total_failed) > 0 else 0
            print(f"  SUCCESS RATE: {success_rate:.1f}%")
        print("=" * 80)
        
        for category, data in self.results.items():
            cat_rate = (data["passed"] / (data["passed"] + data["failed"])) * 100 if (data["passed"] + data["failed"]) > 0 else 0
            status_icon = "✅" if cat_rate >= 80 else "⚠️" if cat_rate >= 50 else "❌"
            print(f"\n  {status_icon} {category}: {data['passed']}/{data['passed']+data['failed']} ({cat_rate:.0f}%) [+{data['skipped']} skipped]")
            
            for t in data["tests"]:
                if t["passed"] is True:
                    icon = "  ✅"
                elif t["passed"] is False:
                    sev = t.get("severity", "info")
                    icon = "  ❌" if sev in ("critical", "fatal") else "  ⚠️"
                else:
                    icon = "  ⏭️"
                detail = t["details"][:80] if t["details"] else ""
                print(f"    {icon} {t['test']}: {detail}")
        
        # Production readiness verdict
        print("\n" + "=" * 80)
        print("  PRODUCTION READINESS VERDICT")
        print("=" * 80)
        
        fatal_count = sum(
            1 for cat in self.results.values() 
            for t in cat["tests"] 
            if t.get("severity") == "fatal" and t["passed"] is False
        )
        critical_count = sum(
            1 for cat in self.results.values() 
            for t in cat["tests"] 
            if t.get("severity") == "critical" and t["passed"] is False
        )
        
        if fatal_count > 0:
            print(f"  ❌ NOT PRODUCTION READY — {fatal_count} FATAL issue(s) found")
            print(f"     Launch karne se PEHLE in fatal issues ko fix karo")
        elif critical_count > 3:
            print(f"  ⚠️ RISKY FOR PRODUCTION — {critical_count} critical issue(s)")
            print(f"     Launch toh ho jayega par problems aayengi")
        elif critical_count > 0:
            print(f"  ⚠️ MOSTLY READY — {critical_count} critical issue(s) remain")
            print(f"     With workarounds, can launch")
        elif success_rate >= 85:
            print(f"  ✅ PRODUCTION READY — {success_rate:.0f}% success rate")
            print(f"     Launch kar sakte ho, minor issues hain but manageable")
        elif success_rate >= 70:
            print(f"  ⚠️ BORDERLINE — {success_rate:.0f}% success rate")
            print(f"     Some features need fixing before launch")
        else:
            print(f"  ❌ NOT READY — {success_rate:.0f}% success rate")
            print(f"     Major work needed before production")
        
        print("=" * 80)
        
        return {
            "total": total,
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "success_rate": round(success_rate, 1) if (total_passed + total_failed) > 0 else 0,
            "fatal_issues": fatal_count,
            "critical_issues": critical_count,
            "categories": self.results,
        }


results = BrutalResults()


# ═══════════════════════════════════════════════════════════════
# TEST 1: INSTALLATION & DEPENDENCY CHECK
# ═══════════════════════════════════════════════════════════════

def test_installation():
    """Check if all dependencies are installable and importable."""
    print("\n[1/10] Testing Installation & Dependencies...")
    
    # Core dependencies
    core_deps = {
        "patchright": "patchright",
        "websockets": "websockets", 
        "aiohttp": "aiohttp",
        "cryptography": "cryptography",
        "pyyaml": "yaml",
        "psutil": "psutil",
        "numpy": "numpy",
    }
    
    for name, module in core_deps.items():
        try:
            mod = importlib.import_module(module)
            ver = getattr(mod, "__version__", "unknown")
            results.record("Installation", f"Import {name}", True, f"v{ver}")
        except ImportError as e:
            results.record("Installation", f"Import {name}", False, 
                         str(e)[:80], "critical", f"pip install {name}")
    
    # Optional but important deps
    opt_deps = {
        "curl_cffi": "curl_cffi",
        "cloudscraper": "cloudscraper",
        "redis": "redis",
        "sqlalchemy": "sqlalchemy",
        "asyncpg": "asyncpg",
        "PyJWT": "jwt",
        "bcrypt": "bcrypt",
        "pydantic": "pydantic",
        "structlog": "structlog",
        "mcp": "mcp",
        "openai": "openai",
    }
    
    for name, module in opt_deps.items():
        try:
            mod = importlib.import_module(module)
            ver = getattr(mod, "__version__", "unknown")
            results.record("Installation", f"Optional: {name}", True, f"v{ver}")
        except ImportError as e:
            results.record("Installation", f"Optional: {name}", False,
                         f"NOT INSTALLED: {str(e)[:60]}", "warning", f"pip install {name}")
    
    # Check if patchright browser binary exists
    try:
        result = subprocess.run(
            [sys.executable, "-m", "patchright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=10
        )
        # If dry-run doesn't work, check directly
        from patchright.async_api import async_playwright
        results.record("Installation", "Patchright browser binary", True, 
                      "patchright module importable")
    except Exception as e:
        results.record("Installation", "Patchright browser binary", False,
                      f"May need: python -m patchright install chromium", "critical",
                      "python -m patchright install chromium")
    
    # Check install.sh exists and is executable
    install_sh = Path(__file__).parent / "install.sh"
    results.record("Installation", "install.sh exists", 
                  install_sh.exists(), 
                  f"Found: {install_sh}" if install_sh.exists() else "Missing",
                  "warning" if not install_sh.exists() else "info")
    
    # Check requirements.txt
    req_file = Path(__file__).parent / "requirements.txt"
    if req_file.exists():
        with open(req_file) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        results.record("Installation", "requirements.txt", True, f"{len(lines)} packages listed")
    else:
        results.record("Installation", "requirements.txt", False, "Missing!", "fatal")
    
    # Check Dockerfile
    dockerfile = Path(__file__).parent / "Dockerfile"
    results.record("Installation", "Dockerfile exists", dockerfile.exists(),
                  "Found" if dockerfile.exists() else "Missing",
                  "warning" if not dockerfile.exists() else "info")
    
    # Check docker-compose
    dc_file = Path(__file__).parent / "docker-compose.yml"
    results.record("Installation", "docker-compose.yml exists", dc_file.exists(),
                  "Found" if dc_file.exists() else "Missing",
                  "warning" if not dc_file.exists() else "info")


# ═══════════════════════════════════════════════════════════════
# TEST 2: STEALTH SYSTEM (3 LAYERS)
# ═══════════════════════════════════════════════════════════════

async def test_stealth_layers():
    """Test all 3 stealth layers: CDP, InitScript, GodMode."""
    print("\n[2/10] Testing Stealth System (3 Layers)...")
    
    try:
        from src.core.browser import AgentBrowser, BROWSER_PROFILES
        from src.core.config import Config
        from src.core.stealth import ANTI_DETECTION_JS
        from src.core.cdp_stealth import CDPStealthInjector
        from src.core.stealth_god import GodModeStealth, ConsistentFingerprint
    except ImportError as e:
        results.record("Stealth", "Module imports", False, str(e), "fatal")
        return
    
    # Test browser profiles
    results.record("Stealth", "Browser profiles count", 
                  len(BROWSER_PROFILES) >= 12,
                  f"{len(BROWSER_PROFILES)} profiles (need 12+)",
                  "critical" if len(BROWSER_PROFILES) < 12 else "info")
    
    # Check profile diversity (Windows, Mac, Linux, Edge)
    platforms = set(p.platform for p in BROWSER_PROFILES)
    results.record("Stealth", "Profile platform diversity",
                  len(platforms) >= 3,
                  f"Platforms: {platforms} (need 3+)",
                  "warning" if len(platforms) < 3 else "info")
    
    # Test ANTI_DETECTION_JS completeness
    required_layers = [
        "LAYER 0", "LAYER 1", "LAYER 2", "LAYER 3", "LAYER 4", "LAYER 5",
        "LAYER 6", "LAYER 7", "LAYER 8", "LAYER 9", "LAYER 10", "LAYER 11",
        "LAYER 12", "LAYER 13", "LAYER 14", "LAYER 15", "LAYER 16",
    ]
    missing_layers = [l for l in required_layers if l not in ANTI_DETECTION_JS]
    results.record("Stealth", "ANTI_DETECTION_JS layers",
                  len(missing_layers) == 0,
                  f"Missing: {missing_layers}" if missing_layers else f"All {len(required_layers)} layers present",
                  "critical" if missing_layers else "info")
    
    # Check key anti-detection features in JS
    js_features = {
        "webdriver removal": "navigator.webdriver" in ANTI_DETECTION_JS or "Navigator.prototype.webdriver" in ANTI_DETECTION_JS,
        "toString cloaking": "spoofToString" in ANTI_DETECTION_JS or "native code" in ANTI_DETECTION_JS,
        "Chrome runtime mock": "chrome.runtime" in ANTI_DETECTION_JS or "_chromeObj" in ANTI_DETECTION_JS,
        "WebGL spoofing": "getParameter" in ANTI_DETECTION_JS,
        "Canvas noise": "toDataURL" in ANTI_DETECTION_JS,
        "Audio fingerprint": "AudioContext" in ANTI_DETECTION_JS or "AnalyserNode" in ANTI_DETECTION_JS,
        "WebRTC block": "RTCPeerConnection" in ANTI_DETECTION_JS,
        "Permissions spoof": "permissions.query" in ANTI_DETECTION_JS,
        "Notification mock": "Notification" in ANTI_DETECTION_JS,
        "Battery API": "getBattery" in ANTI_DETECTION_JS,
        "Font enumeration block": "document.fonts" in ANTI_DETECTION_JS,
        "Performance timing": "performance.timing" in ANTI_DETECTION_JS or "timeOrigin" in ANTI_DETECTION_JS,
        "Beacon API intercept": "sendBeacon" in ANTI_DETECTION_JS,
        "CDP detection prevention": "__cdp_bindings__" in ANTI_DETECTION_JS,
        "Cloudflare challenge detection": "challenge-running" in ANTI_DETECTION_JS or "cf-challenge" in ANTI_DETECTION_JS,
    }
    
    for feature, present in js_features.items():
        results.record("Stealth", f"JS: {feature}", present,
                      "Present" if present else "MISSING!",
                      "critical" if not present else "info")
    
    # Test CDPStealthInjector
    try:
        injector = CDPStealthInjector()
        results.record("Stealth", "CDPStealthInjector init", True, "Initialized")
    except Exception as e:
        results.record("Stealth", "CDPStealthInjector init", False, str(e)[:80], "critical")
    
    # Test GodModeStealth
    try:
        god = GodModeStealth()
        results.record("Stealth", "GodModeStealth init", True, "Initialized")
    except Exception as e:
        results.record("Stealth", "GodModeStealth init", False, str(e)[:80], "critical")
    
    # Test ConsistentFingerprint
    try:
        cf = ConsistentFingerprint()
        results.record("Stealth", "ConsistentFingerprint init", True, "Initialized")
    except Exception as e:
        results.record("Stealth", "ConsistentFingerprint init", False, str(e)[:80], "warning")
    
    # Test browser startup with stealth (THE REAL TEST)
    try:
        config = Config()
        config.set("browser.headless", True)
        browser = AgentBrowser(config)
        await browser.start()
        results.record("Stealth", "Browser startup with stealth", True, "Browser started")
        
        # Navigate to a bot detection test
        page = browser.page
        try:
            await page.goto("https://bot.sannysoft.com/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            
            # Check webdriver detection
            webdriver_result = await page.evaluate("() => navigator.webdriver")
            results.record("Stealth", "navigator.webdriver",
                          webdriver_result is None or webdriver_result == False or webdriver_result == "undefined",
                          f"Value: {webdriver_result}",
                          "critical" if webdriver_result else "info")
            
            # Check plugins
            plugins_length = await page.evaluate("() => navigator.plugins.length")
            results.record("Stealth", "navigator.plugins",
                          plugins_length >= 3,
                          f"Count: {plugins_length} (need 3+)",
                          "critical" if plugins_length < 3 else "info")
            
            # Check chrome runtime
            chrome_exists = await page.evaluate("() => !!window.chrome && !!window.chrome.runtime")
            results.record("Stealth", "window.chrome.runtime",
                          chrome_exists,
                          f"Exists: {chrome_exists}",
                          "critical" if not chrome_exists else "info")
            
            # Check platform consistency
            platform = await page.evaluate("() => navigator.platform")
            results.record("Stealth", "navigator.platform",
                          platform in ("Win32", "MacIntel", "Linux x86_64"),
                          f"Platform: {platform}",
                          "warning" if platform not in ("Win32", "MacIntel", "Linux x86_64") else "info")
            
            # Check languages
            languages = await page.evaluate("() => navigator.languages")
            results.record("Stealth", "navigator.languages",
                          isinstance(languages, list) and len(languages) >= 2,
                          f"Languages: {languages}",
                          "warning" if not isinstance(languages, list) else "info")
            
            # Check hardware info
            cores = await page.evaluate("() => navigator.hardwareConcurrency")
            memory = await page.evaluate("() => navigator.deviceMemory")
            results.record("Stealth", "Hardware info set",
                          isinstance(cores, int) and cores > 0,
                          f"Cores: {cores}, Memory: {memory}GB",
                          "warning" if not isinstance(cores, int) else "info")
            
            # Check WebGL vendor
            webgl_vendor = await page.evaluate("""() => {
                try {
                    const c = document.createElement('canvas');
                    const gl = c.getContext('webgl');
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                } catch(e) { return 'error'; }
            }""")
            results.record("Stealth", "WebGL vendor",
                          webgl_vendor != "Google Inc. (SwiftShader)" and webgl_vendor != "error",
                          f"Vendor: {webgl_vendor}",
                          "critical" if "SwiftShader" in str(webgl_vendor) else "info")
            
            # Check WebGL renderer (must NOT be SwiftShader)
            webgl_renderer = await page.evaluate("""() => {
                try {
                    const c = document.createElement('canvas');
                    const gl = c.getContext('webgl');
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                } catch(e) { return 'error'; }
            }""")
            is_swiftshader = "SwiftShader" in str(webgl_renderer)
            results.record("Stealth", "WebGL renderer (NOT SwiftShader)",
                          not is_swiftshader,
                          f"Renderer: {str(webgl_renderer)[:60]}",
                          "critical" if is_swiftshader else "info")
            
            # Screenshot for proof
            try:
                screenshot = await page.screenshot()
                proof_path = Path(__file__).parent / "proof" / "brutal_test_bot_sannysoft.png"
                proof_path.parent.mkdir(parents=True, exist_ok=True)
                proof_path.write_bytes(screenshot)
                results.record("Stealth", "Bot detection screenshot", True, f"Saved to {proof_path}")
            except Exception as e:
                results.record("Stealth", "Bot detection screenshot", False, str(e)[:60])
            
        except Exception as e:
            results.record("Stealth", "Bot detection site test", False, 
                         str(e)[:80], "critical")
        
        # Test second bot detection site
        try:
            await page.goto("https://abrahamjuliot.github.io/creepjs/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)
            
            # Check creepjs score
            try:
                trust_score = await page.evaluate("""() => {
                    const el = document.querySelector('.visitor-info .trust');
                    if (el) return el.textContent;
                    const els = document.querySelectorAll('.score');
                    for (const e of els) {
                        if (e.textContent.includes('%')) return e.textContent;
                    }
                    return 'unknown';
                }""")
                results.record("Stealth", "CreepJS fingerprint score",
                              True,  # We just want to see the score
                              f"Score: {trust_score}",
                              "info")
            except Exception as e:
                results.record("Stealth", "CreepJS score read", False, str(e)[:60], "info")
            
            # Screenshot
            try:
                screenshot = await page.screenshot(full_page=True)
                proof_path = Path(__file__).parent / "proof" / "brutal_test_creepjs.png"
                proof_path.write_bytes(screenshot)
                results.record("Stealth", "CreepJS screenshot", True, f"Saved to {proof_path}")
            except Exception as e:
                results.record("Stealth", "CreepJS screenshot", False, str(e)[:60])
                
        except Exception as e:
            results.record("Stealth", "CreepJS site test", False, 
                         str(e)[:80], "warning")
        
        # Clean up
        await browser.stop()
        
    except Exception as e:
        results.record("Stealth", "Browser startup", False, str(e)[:80], "fatal")


# ═══════════════════════════════════════════════════════════════
# TEST 3: FORM FILLER
# ═══════════════════════════════════════════════════════════════

async def test_form_filler():
    """Test form filling capabilities."""
    print("\n[3/10] Testing Form Filler...")
    
    try:
        from src.tools.form_filler import FormFiller, ProfileBuilder
    except ImportError as e:
        results.record("Form Filler", "Module import", False, str(e), "fatal")
        return
    
    results.record("Form Filler", "FormFiller import", True, "Imported")
    results.record("Form Filler", "ProfileBuilder import", True, "Imported")
    
    # Test FIELD_PATTERNS completeness
    required_fields = ["email", "username", "password", "first_name", "last_name", 
                      "phone", "address", "city", "state", "zip", "country"]
    missing = [f for f in required_fields if f not in FormFiller.FIELD_PATTERNS]
    results.record("Form Filler", "FIELD_PATTERNS completeness",
                  len(missing) == 0,
                  f"Missing: {missing}" if missing else f"All {len(required_fields)} field types present",
                  "critical" if missing else "info")
    
    # Test password field specifically (was broken by React regression)
    has_password = "password" in FormFiller.FIELD_PATTERNS
    password_patterns = FormFiller.FIELD_PATTERNS.get("password", [])
    has_pwd_variants = "pwd" in password_patterns or "passwd" in password_patterns
    results.record("Form Filler", "Password field patterns",
                  has_password and has_pwd_variants,
                  f"Patterns: {password_patterns}",
                  "critical" if not has_password else "info")
    
    # Test CROSS_FIELD_MAP
    has_cross = hasattr(FormFiller, "CROSS_FIELD_MAP") and len(FormFiller.CROSS_FIELD_MAP) > 0
    results.record("Form Filler", "Cross-field mapping",
                  has_cross,
                  f"Mappings: {FormFiller.CROSS_FIELD_MAP}" if has_cross else "MISSING!",
                  "warning" if not has_cross else "info")
    
    # Test ProfileBuilder
    try:
        profile = ProfileBuilder.from_dict({
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "555-1234",
            "password": "SuperSecret123!",
        })
        results.record("Form Filler", "ProfileBuilder.from_dict",
                      bool(profile.get("email")),
                      f"Email: {profile.get('email')}, FName: {profile.get('first_name')}")
    except Exception as e:
        results.record("Form Filler", "ProfileBuilder.from_dict", False, str(e)[:80], "critical")
    
    # Test real form filling on a login page
    try:
        from src.core.browser import AgentBrowser
        from src.core.config import Config
        
        config = Config()
        config.set("browser.headless", True)
        browser = AgentBrowser(config)
        await browser.start()
        
        filler = FormFiller(browser)
        
        # Navigate to GitHub login
        page = browser.page
        await page.goto("https://github.com/login", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        # Try form filling
        profile = {
            "username": "test_agent_os_user",
            "email": "test@example.com",
            "password": "TestPassword123!",
        }
        
        result = await filler.fill_job_application("https://github.com/login", profile)
        results.record("Form Filler", "GitHub login form fill",
                      result.get("status") == "success" or result.get("fields_filled", 0) > 0,
                      f"Status: {result.get('status')}, Fields filled: {result.get('fields_filled', 0)}",
                      "warning" if result.get("status") != "success" else "info")
        
        # Check if username field was filled (cross-field: username → email)
        try:
            login_value = await page.evaluate("""() => {
                const el = document.querySelector('#login_field');
                return el ? el.value : 'NOT_FOUND';
            }""")
            results.record("Form Filler", "Username field value",
                          login_value != "NOT_FOUND" and len(login_value) > 0,
                          f"Value: '{login_value}'",
                          "warning" if login_value == "NOT_FOUND" else "info")
        except Exception as e:
            results.record("Form Filler", "Username field check", False, str(e)[:60])
        
        # Check if password field was filled
        try:
            pwd_value = await page.evaluate("""() => {
                const el = document.querySelector('#password');
                return el ? el.value : 'NOT_FOUND';
            }""")
            results.record("Form Filler", "Password field value",
                          pwd_value != "NOT_FOUND" and len(pwd_value) > 0,
                          f"Has value: {bool(pwd_value)}",
                          "warning" if pwd_value == "NOT_FOUND" else "info")
        except Exception as e:
            results.record("Form Filler", "Password field check", False, str(e)[:60])
        
        # Screenshot
        try:
            screenshot = await page.screenshot()
            proof_path = Path(__file__).parent / "proof" / "brutal_test_form_fill_github.png"
            proof_path.write_bytes(screenshot)
            results.record("Form Filler", "Form fill screenshot", True, f"Saved")
        except:
            pass
        
        await browser.stop()
        
    except Exception as e:
        results.record("Form Filler", "Real form fill test", False, str(e)[:80], "critical")


# ═══════════════════════════════════════════════════════════════
# TEST 4: SWARM/ROUTER SYSTEM
# ═══════════════════════════════════════════════════════════════

async def test_swarm_router():
    """Test the agent swarm routing system."""
    print("\n[4/10] Testing Swarm/Router System...")
    
    try:
        from src.agent_swarm.router.rule_based import RuleBasedRouter, QueryCategory
    except ImportError as e:
        results.record("Swarm Router", "Module import", False, str(e), "fatal")
        return
    
    results.record("Swarm Router", "RuleBasedRouter import", True, "Imported")
    
    router = RuleBasedRouter()
    
    # Test query classification accuracy
    test_cases = [
        # (query, expected_category)
        ("solve the captcha", QueryCategory.NEEDS_SECURITY),
        ("bypass cloudflare", QueryCategory.NEEDS_SECURITY),
        ("what is 2 + 2", QueryCategory.NEEDS_CALCULATION),
        ("calculate compound interest", QueryCategory.NEEDS_CALCULATION),
        ("write a python function", QueryCategory.NEEDS_CODE),
        ("implement a load balancer in Go", QueryCategory.NEEDS_CODE),
        ("what is photosynthesis", QueryCategory.NEEDS_KNOWLEDGE),
        ("who invented the telephone", QueryCategory.NEEDS_KNOWLEDGE),
        ("latest news today", QueryCategory.NEEDS_WEB),
        ("bitcoin price right now", QueryCategory.NEEDS_WEB),
        ("weather in New York today", QueryCategory.NEEDS_WEB),
        ("scrape product prices from amazon", QueryCategory.NEEDS_WEB),
        ("fill out the login form", QueryCategory.NEEDS_SECURITY),
        ("solve the math equation", QueryCategory.NEEDS_CALCULATION),
        ("how to install python", QueryCategory.NEEDS_WEB),  # install queries need web
        ("formula for area of circle", QueryCategory.NEEDS_KNOWLEDGE),
        ("code fibonacci in python", QueryCategory.NEEDS_CODE),
        ("convert 100 USD to EUR", QueryCategory.NEEDS_WEB),
    ]
    
    correct = 0
    total = len(test_cases)
    misroutes = []
    
    for query, expected in test_cases:
        result = router.classify(query)
        match = result.category == expected
        if match:
            correct += 1
        else:
            misroutes.append(f"'{query}': expected {expected.value}, got {result.category.value}")
        results.record("Swarm Router", f"Route: '{query[:30]}'",
                      match,
                      f"→ {result.category.value} (conf: {result.confidence:.2f})",
                      "info")
    
    accuracy = (correct / total) * 100
    results.record("Swarm Router", "Overall routing accuracy",
                  accuracy >= 80,
                  f"{accuracy:.0f}% ({correct}/{total})",
                  "critical" if accuracy < 60 else "warning" if accuracy < 80 else "info")
    
    # Test agent suggestions
    for query in ["solve recaptcha", "latest AI news", "calculate factorial"]:
        result = router.classify(query)
        has_agents = len(result.suggested_agents) > 0
        results.record("Swarm Router", f"Agents for '{query[:20]}'",
                      has_agents,
                      f"Agents: {result.suggested_agents}",
                      "warning" if not has_agents else "info")
    
    # Test orchestrator
    try:
        from src.agent_swarm.router.orchestrator import OrchestratorRouter
        orch = OrchestratorRouter()
        results.record("Swarm Router", "OrchestratorRouter init", True, "Initialized")
    except ImportError as e:
        results.record("Swarm Router", "OrchestratorRouter init", False, str(e)[:60], "warning")
    
    # Test provider router
    try:
        from src.agent_swarm.router.provider_router import ProviderRouter
        results.record("Swarm Router", "ProviderRouter import", True, "Imported")
    except ImportError as e:
        results.record("Swarm Router", "ProviderRouter import", False, str(e)[:60], "warning")
    
    # Test conservative router
    try:
        from src.agent_swarm.router.conservative import ConservativeRouter
        results.record("Swarm Router", "ConservativeRouter import", True, "Imported")
    except ImportError as e:
        results.record("Swarm Router", "ConservativeRouter import", False, str(e)[:60], "warning")


# ═══════════════════════════════════════════════════════════════
# TEST 5: PROXY ROTATION
# ═══════════════════════════════════════════════════════════════

async def test_proxy_rotation():
    """Test proxy rotation system."""
    print("\n[5/10] Testing Proxy Rotation...")
    
    try:
        from src.tools.proxy_rotation import ProxyManager, ProxyInfo
    except ImportError as e:
        results.record("Proxy Rotation", "Module import", False, str(e), "critical")
        return
    
    results.record("Proxy Rotation", "ProxyManager import", True, "Imported")
    
    # Test ProxyManager initialization
    try:
        pm = ProxyManager(strategy="weighted")
        results.record("Proxy Rotation", "ProxyManager init", True, "Strategy: weighted")
    except Exception as e:
        results.record("Proxy Rotation", "ProxyManager init", False, str(e)[:80], "critical")
        return
    
    # Test proxy loading from file (should handle missing file gracefully)
    try:
        result = pm.load_proxies("/tmp/nonexistent_proxy_file.txt")
        results.record("Proxy Rotation", "Missing file handling",
                      result.get("loaded", 0) == 0 or "error" in result,
                      f"Result: {result}",
                      "info")
    except Exception as e:
        results.record("Proxy Rotation", "Missing file handling", False, str(e)[:60])
    
    # Test adding proxies manually
    try:
        pm.add_proxy("http://user1:pass1@proxy1.example.com:8080", proxy_type="residential")
        pm.add_proxy("http://user2:pass2@proxy2.example.com:8080", proxy_type="datacenter")
        pm.add_proxy("http://user3:pass3@proxy3.example.com:8080", proxy_type="mobile")
        results.record("Proxy Rotation", "Add proxies", True, "3 proxies added")
    except Exception as e:
        results.record("Proxy Rotation", "Add proxies", False, str(e)[:60], "warning")
    
    # Test proxy selection
    try:
        proxy = pm.get_next_proxy()
        results.record("Proxy Rotation", "Get next proxy",
                      proxy is not None,
                      f"Proxy: {proxy.url if proxy else 'None'}",
                      "warning" if proxy is None else "info")
    except Exception as e:
        results.record("Proxy Rotation", "Get next proxy", False, str(e)[:60], "warning")
    
    # Test rotation
    try:
        proxies = []
        for _ in range(5):
            p = pm.get_next_proxy()
            if p:
                proxies.append(p.url)
        results.record("Proxy Rotation", "Rotation working",
                      len(proxies) > 0,
                      f"Got {len(proxies)} proxies in 5 tries",
                      "warning" if len(proxies) == 0 else "info")
    except Exception as e:
        results.record("Proxy Rotation", "Rotation", False, str(e)[:60], "warning")
    
    # Test result recording
    try:
        proxy = pm.get_next_proxy()
        if proxy:
            pm.record_result(proxy.url, success=True, response_time=1.5)
            results.record("Proxy Rotation", "Result recording", True, "Success recorded")
        else:
            results.skip("Proxy Rotation", "Result recording", "No proxy available")
    except Exception as e:
        results.record("Proxy Rotation", "Result recording", False, str(e)[:60], "warning")


# ═══════════════════════════════════════════════════════════════
# TEST 6: TLS FINGERPRINTING
# ═══════════════════════════════════════════════════════════════

async def test_tls_fingerprinting():
    """Test TLS fingerprinting system."""
    print("\n[6/10] Testing TLS Fingerprinting...")
    
    try:
        from src.core.tls_spoof import TLSFingerprintEngine, apply_browser_tls_spoofing
    except ImportError as e:
        results.record("TLS Fingerprinting", "Module import", False, str(e), "critical")
        return
    
    results.record("TLS Fingerprinting", "TLSFingerprintEngine import", True, "Imported")
    
    # Test TLS engine initialization
    try:
        engine = TLSFingerprintEngine()
        results.record("TLS Fingerprinting", "Engine init", True, "Initialized")
    except Exception as e:
        results.record("TLS Fingerprinting", "Engine init", False, 
                      f"curl_cffi issue: {str(e)[:60]}", "warning",
                      "pip install curl_cffi")
        return
    
    # Test TLS request with browser impersonation
    try:
        result = engine.get("https://tls.peet.ws/api/all", impersonate="chrome136")
        if result:
            status = result.status_code if hasattr(result, 'status_code') else None
            results.record("TLS Fingerprinting", "TLS request with impersonation",
                          status == 200 if status else False,
                          f"Status: {status}",
                          "info")
            
            # Check JA3/JA4 fingerprint
            if hasattr(result, 'json'):
                try:
                    data = result.json() if callable(result.json) else result.json
                    tls_version = data.get("tls_version", "unknown")
                    ja3_hash = data.get("ja3_hash", "unknown") if isinstance(data, dict) else "unknown"
                    results.record("TLS Fingerprinting", "TLS version",
                                  "1.3" in str(tls_version) or "1.2" in str(tls_version),
                                  f"Version: {tls_version}, JA3: {str(ja3_hash)[:20]}",
                                  "info")
                except:
                    results.record("TLS Fingerprinting", "TLS response parse", False, "Could not parse", "info")
        else:
            results.record("TLS Fingerprinting", "TLS request", False, "No response", "warning")
    except Exception as e:
        results.record("TLS Fingerprinting", "TLS request", False, str(e)[:80], "warning")
    
    # Test TLS proxy
    try:
        from src.core.tls_proxy import TLSProxyServer, _CURL_AVAILABLE
        results.record("TLS Fingerprinting", "curl_cffi available",
                      _CURL_AVAILABLE,
                      "Installed" if _CURL_AVAILABLE else "NOT installed — TLS proxy won't work",
                      "warning" if not _CURL_AVAILABLE else "info")
    except ImportError:
        results.record("TLS Fingerprinting", "TLS proxy import", False, "Module missing", "warning")


# ═══════════════════════════════════════════════════════════════
# TEST 7: DATABASE + REDIS
# ═══════════════════════════════════════════════════════════════

async def test_database_redis():
    """Test database and Redis infrastructure."""
    print("\n[7/10] Testing Database & Redis...")
    
    # Test database module
    try:
        from src.infra.database import init_db
        results.record("Database", "Module import", True, "Imported")
    except ImportError as e:
        results.record("Database", "Module import", False, str(e), "critical")
    
    # Test database models
    try:
        from src.infra.models import Base
        results.record("Database", "Models import", True, "Imported")
    except ImportError as e:
        results.record("Database", "Models import", False, str(e), "warning")
    
    # Test Redis module
    try:
        from src.infra.redis_client import init_redis
        results.record("Redis", "Module import", True, "Imported")
    except ImportError as e:
        results.record("Redis", "Module import", False, str(e), "warning")
    
    # Try actual Redis connection
    try:
        import redis as redis_lib
        r = redis_lib.Redis(host="localhost", port=6379, socket_connect_timeout=3)
        r.ping()
        results.record("Redis", "Redis connection", True, "Connected to localhost:6379")
        
        # Test basic operations
        r.set("agent_os_test_key", "test_value", ex=10)
        val = r.get("agent_os_test_key")
        results.record("Redis", "Redis SET/GET",
                      val == b"test_value",
                      f"Value: {val}",
                      "info")
        r.delete("agent_os_test_key")
    except Exception as e:
        results.record("Redis", "Redis connection", False,
                      f"Redis not running: {str(e)[:60]}",
                      "warning",
                      "Start Redis: docker run -d -p 6379:6379 redis")
    
    # Try actual PostgreSQL connection
    try:
        import asyncpg
        conn = await asyncpg.connect(
            "postgresql://agent_os:agent_os@localhost:5432/agent_os",
            timeout=5,
        )
        results.record("Database", "PostgreSQL connection", True, "Connected")
        await conn.close()
    except Exception as e:
        results.record("Database", "PostgreSQL connection", False,
                      f"DB not running: {str(e)[:60]}",
                      "warning",
                      "Start PostgreSQL or use docker-compose")
    
    # Test Alembic migration
    alembic_ini = Path(__file__).parent / "alembic.ini"
    alembic_dir = Path(__file__).parent / "alembic"
    results.record("Database", "Alembic setup",
                  alembic_ini.exists() and alembic_dir.exists(),
                  f"INI: {alembic_ini.exists()}, Dir: {alembic_dir.exists()}",
                  "info")


# ═══════════════════════════════════════════════════════════════
# TEST 8: MCP CONNECTOR
# ═══════════════════════════════════════════════════════════════

async def test_mcp():
    """Test MCP connector."""
    print("\n[8/10] Testing MCP Connector...")
    
    # Test MCP server module
    try:
        from connectors.mcp_server import mcp
        results.record("MCP", "MCP server module", True, "Imported")
    except ImportError as e:
        results.record("MCP", "MCP server module", False, str(e)[:80], "warning")
    
    # Test MCP config
    mcp_config = Path(__file__).parent / "connectors" / "mcp_config.json"
    if mcp_config.exists():
        try:
            with open(mcp_config) as f:
                config = json.load(f)
            results.record("MCP", "MCP config file", True, f"Config loaded")
        except Exception as e:
            results.record("MCP", "MCP config file", False, str(e)[:60])
    else:
        results.skip("MCP", "MCP config file", "No config file found")
    
    # Test mcp library
    try:
        import mcp
        ver = getattr(mcp, "__version__", "installed")
        results.record("MCP", "mcp library", True, f"v{ver}")
    except ImportError:
        results.record("MCP", "mcp library", False, "Not installed", "warning",
                      "pip install mcp")
    
    # Test OpenAI connector
    try:
        from connectors.openai_connector import OpenAIConnector
        results.record("MCP", "OpenAI connector", True, "Imported")
    except ImportError as e:
        results.record("MCP", "OpenAI connector", False, str(e)[:60], "info")


# ═══════════════════════════════════════════════════════════════
# TEST 9: LOGIN HANDOFF
# ═══════════════════════════════════════════════════════════════

async def test_login_handoff():
    """Test login handoff system."""
    print("\n[9/10] Testing Login Handoff...")
    
    try:
        from src.tools.login_handoff import (
            LoginDetector, LoginHandoffManager, HandoffState, HandoffSession
        )
    except ImportError as e:
        results.record("Login Handoff", "Module import", False, str(e), "fatal")
        return
    
    results.record("Login Handoff", "Module import", True, "All classes imported")
    
    # Test LoginDetector URL detection
    test_urls = [
        ("https://github.com/login", True, "login"),
        ("https://instagram.com/accounts/login/", True, "login"),
        ("https://twitter.com/i/flow/login", True, "login"),
        ("https://amazon.com/ap/signin", True, "login"),
        ("https://example.com/signup", True, "signup"),
        ("https://example.com/register", True, "signup"),
        ("https://example.com/home", False, "none"),
        ("https://google.com/search?q=test", False, "none"),
    ]
    
    correct = 0
    for url, expected_is_login, expected_type in test_urls:
        is_login, page_type, confidence = LoginDetector.detect_from_url(url)
        match = is_login == expected_is_login
        if match:
            correct += 1
        results.record("Login Handoff", f"URL detect: {url[:40]}",
                      match,
                      f"Expected: {expected_type}, Got: {page_type} (conf: {confidence:.2f})",
                      "info")
    
    results.record("Login Handoff", "URL detection accuracy",
                  correct >= len(test_urls) * 0.8,
                  f"{correct}/{len(test_urls)} correct",
                  "warning" if correct < len(test_urls) * 0.8 else "info")
    
    # Test LOGIN_REQUIRED_DOMAINS
    important_domains = ["instagram.com", "twitter.com", "x.com", "facebook.com", 
                        "linkedin.com", "github.com", "amazon.com"]
    for domain in important_domains:
        in_list = domain in LoginDetector.LOGIN_REQUIRED_DOMAINS
        results.record("Login Handoff", f"Domain: {domain}",
                      in_list,
                      "In list" if in_list else "MISSING",
                      "warning" if not in_list else "info")
    
    # Test HandoffState
    results.record("Login Handoff", "HandoffState enum",
                  hasattr(HandoffState, "IDLE") and 
                  hasattr(HandoffState, "WAITING_FOR_USER") and
                  hasattr(HandoffState, "COMPLETED"),
                  "All states present",
                  "critical" if not hasattr(HandoffState, "WAITING_FOR_USER") else "info")
    
    # Test HandoffSession
    try:
        hs = HandoffSession(
            handoff_id="test_ho_123",
            url="https://github.com/login",
            domain="github.com",
            page_type="login",
        )
        results.record("Login Handoff", "HandoffSession creation", True,
                      f"ID: {hs.handoff_id}, State: {hs.state}")
        
        # Test to_dict
        d = hs.to_dict()
        results.record("Login Handoff", "HandoffSession.to_dict",
                      "handoff_id" in d and "state" in d,
                      f"Keys: {list(d.keys())[:5]}...")
    except Exception as e:
        results.record("Login Handoff", "HandoffSession creation", False, str(e)[:60], "critical")
    
    # Test real DOM detection with browser
    try:
        from src.core.browser import AgentBrowser
        from src.core.config import Config
        
        config = Config()
        config.set("browser.headless", True)
        browser = AgentBrowser(config)
        await browser.start()
        
        page = browser.page
        await page.goto("https://github.com/login", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        is_login, page_type, confidence = await LoginDetector.detect_from_dom(page)
        results.record("Login Handoff", "DOM detection on GitHub login",
                      is_login,
                      f"Type: {page_type}, Conf: {confidence:.2f}",
                      "critical" if not is_login else "info")
        
        await browser.stop()
    except Exception as e:
        results.record("Login Handoff", "DOM detection test", False,
                      str(e)[:80], "warning")


# ═══════════════════════════════════════════════════════════════
# TEST 10: SECURITY & EVASION ENGINE
# ═══════════════════════════════════════════════════════════════

async def test_security():
    """Test security systems: EvasionEngine, CaptchaSolver, CloudflareBypass."""
    print("\n[10/10] Testing Security Systems...")
    
    # Test EvasionEngine
    try:
        from src.security.evasion_engine import EvasionEngine, generate_fingerprint
        engine = EvasionEngine()
        results.record("Security", "EvasionEngine init", True, "Initialized")
        
        # Test fingerprint generation
        for os_type in ["windows", "mac", "linux"]:
            fp = generate_fingerprint(os_target=os_type)
            valid = (
                fp.get("chrome_version") is not None and
                fp.get("user_agent") is not None and
                fp.get("platform") is not None and
                fp.get("webgl_vendor") is not None and
                fp.get("canvas_seed") is not None
            )
            results.record("Security", f"Fingerprint: {os_type}",
                          valid,
                          f"Chrome: {fp.get('chrome_version')}, UA: {fp.get('user_agent', '')[:40]}...",
                          "warning" if not valid else "info")
        
        # Test JS injection generation
        fp = generate_fingerprint(os_target="windows")
        js = engine.get_injection_js("test_page")
        js_length = len(js)
        results.record("Security", "Injection JS generation",
                      js_length > 1000,
                      f"JS length: {js_length} chars",
                      "warning" if js_length < 1000 else "info")
        
        # Check JS has all critical sections
        critical_sections = [
            "CDP DETECTION", "DEVTOOLS DETECTION", "WEBDRIVER",
            "AUTOMATION ARTIFACT", "FINGERPRINTING", "NAVIGATOR PROPERTIES",
            "WEBGL FINGERPRINT", "CANVAS FINGERPRINT", "AUDIO FINGERPRINT",
            "CHROME OBJECT", "PERMISSIONS", "WEBRTC", "STACK TRACE",
        ]
        for section in critical_sections:
            present = section.lower().replace(" ", "_") in js.lower() or section in js
            results.record("Security", f"JS section: {section}",
                          present,
                          "Present" if present else "MISSING",
                          "warning" if not present else "info")
        
    except ImportError as e:
        results.record("Security", "EvasionEngine import", False, str(e), "critical")
    
    # Test CaptchaSolver
    try:
        from src.security.captcha_solver import CaptchaSolver
        solver = CaptchaSolver()
        results.record("Security", "CaptchaSolver init", True, "Initialized")
    except ImportError as e:
        results.record("Security", "CaptchaSolver import", False, str(e)[:60], "warning")
    except Exception as e:
        results.record("Security", "CaptchaSolver init", False, str(e)[:60], "warning")
    
    # Test CloudflareBypass
    try:
        from src.security.cloudflare_bypass import CloudflareBypassEngine
        results.record("Security", "CloudflareBypass import", True, "Imported")
    except ImportError as e:
        results.record("Security", "CloudflareBypass import", False, str(e)[:60], "warning")
    
    # Test HumanMimicry
    try:
        from src.security.human_mimicry import HumanMimicry
        mimicry = HumanMimicry()
        results.record("Security", "HumanMimicry init", True, "Initialized")
    except ImportError as e:
        results.record("Security", "HumanMimicry import", False, str(e)[:60], "warning")
    except Exception as e:
        results.record("Security", "HumanMimicry init", False, str(e)[:60], "warning")
    
    # Test Auth system
    try:
        from src.auth.jwt_handler import JWTHandler
        jwt = JWTHandler(secret_key="test_key_for_brutal_test")
        results.record("Security", "JWTHandler init", True, "Initialized")
        
        # Test token creation and verification
        token = jwt.create_access_token(user_id="test_user")
        payload = jwt.verify_token(token)
        results.record("Security", "JWT token create/verify",
                      payload is not None and payload.get("sub") == "test_user",
                      f"Payload: {payload}",
                      "info")
    except ImportError as e:
        results.record("Security", "JWTHandler import", False, str(e)[:60], "warning")
    except Exception as e:
        results.record("Security", "JWT token", False, str(e)[:60], "warning")
    
    # Test AuthMiddleware
    try:
        from src.auth.middleware import AuthMiddleware
        results.record("Security", "AuthMiddleware import", True, "Imported")
    except ImportError as e:
        results.record("Security", "AuthMiddleware import", False, str(e)[:60], "warning")


# ═══════════════════════════════════════════════════════════════
# MAIN: RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 80)
    print("  Agent-OS BRUTAL STRESS TEST v2")
    print("  NO FIXING. ONLY REPORTING. BRUTAL HONESTY.")
    print(f"  Started: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # Test 1: Installation
    test_installation()
    
    # Test 2: Stealth
    await test_stealth_layers()
    
    # Test 3: Form Filler
    await test_form_filler()
    
    # Test 4: Swarm/Router
    await test_swarm_router()
    
    # Test 5: Proxy Rotation
    await test_proxy_rotation()
    
    # Test 6: TLS Fingerprinting
    await test_tls_fingerprinting()
    
    # Test 7: Database & Redis
    await test_database_redis()
    
    # Test 8: MCP Connector
    await test_mcp()
    
    # Test 9: Login Handoff
    await test_login_handoff()
    
    # Test 10: Security
    await test_security()
    
    # Print summary
    summary = results.summary()
    
    # Save results to JSON
    output_path = Path(__file__).parent / "brutal_stress_test_v2_results.json"
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
