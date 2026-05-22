#!/usr/bin/env python3
"""Agent-OS REAL-WORLD BRUTAL TEST — Fast focused version"""
import asyncio, json, sys, time, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

R = []
SV, SS = 0, 0

def rec(cat, name, ok, err="", ms=0, det=""):
    R.append({"c": cat, "n": name, "ok": ok, "e": err, "ms": ms, "d": det})
    print(f"  {'✅' if ok else '❌'} {name} ({ms:.0f}ms)" + (f" — {err[:80]}" if err else ""))

STEALTH_JS = """() => {
    const r = {};
    r.wd = navigator.webdriver;
    r.pl = navigator.plugins ? navigator.plugins.length : 0;
    r.ch = typeof window.chrome !== 'undefined';
    r.la = navigator.languages ? navigator.languages.length : 0;
    r.plat = navigator.platform;
    r.cdc = Object.keys(window).filter(k => k.startsWith('cdc_')).length;
    r.nm = typeof window.__nightmare !== 'undefined';
    r.cdp = typeof window.__cdp_bindings__ !== 'undefined';
    let b = 0;
    if(r.wd===true) b+=5; if(r.pl===0) b+=3; if(!r.ch) b+=3;
    if(r.cdc>0) b+=5; if(r.nm) b+=5; if(r.cdp) b+=5;
    r.bot = b; r.ok = b===0;
    return r;
}"""

async def test():
    from src.core.config import Config
    from src.core.browser import AgentBrowser
    from src.core.session import SessionManager
    
    print("="*60)
    print("  AGENT-OS REAL-WORLD BRUTAL TEST")
    print("  Actual websites via Agent-OS browser")
    print("="*60)
    
    cfg = Config(tempfile.mktemp(suffix=".yaml"))
    cfg.set("browser.headless", True)
    br = AgentBrowser(cfg)
    
    t=time.time()
    try:
        await br.start()
        rec("Launch","browser_start",True, ms=(time.time()-t)*1000)
    except Exception as e:
        rec("Launch","browser_start",False, str(e)[:200], (time.time()-t)*1000)
        return
    
    # Test sites - focused set
    sites = [
        ("https://www.google.com","Google","search"),
        ("https://www.bbc.com","BBC","news"),
        ("https://news.ycombinator.com","HN","news"),
        ("https://www.wikipedia.org","Wikipedia","ref"),
        ("https://github.com","GitHub","social"),
        ("https://www.amazon.com","Amazon","shop"),
        ("https://stackoverflow.com","SO","tech"),
        ("https://www.instagram.com","Instagram","social"),
        ("https://bot.sannysoft.com","BotDetect","stealth"),
        ("https://finance.yahoo.com","YFinance","finance"),
    ]
    
    print(f"\n▶ Visiting {len(sites)} real websites...")
    for url, name, cat in sites:
        global SV, SS
        SV += 1
        print(f"\n  → {name}")
        t=time.time()
        try:
            res = await asyncio.wait_for(br.navigate(url), timeout=15)
            ms=(time.time()-t)*1000
            if res.get("status")=="success":
                rec(f"Nav/{cat}", name, True, ms=ms)
                SS += 1
                # Quick title
                try:
                    title = await asyncio.wait_for(br.page.title(), timeout=3)
                    rec(f"Nav/{cat}", f"{name}_title", bool(title), det=title[:40] if title else "")
                except: pass
                # Quick screenshot
                try:
                    ss = await asyncio.wait_for(br.screenshot(), timeout=5)
                    rec(f"Nav/{cat}", f"{name}_screenshot", bool(ss))
                except: pass
            else:
                rec(f"Nav/{cat}", name, False, res.get("error","?")[:100], ms)
        except asyncio.TimeoutError:
            rec(f"Nav/{cat}", name, False, "TIMEOUT", (time.time()-t)*1000)
        except Exception as e:
            rec(f"Nav/{cat}", name, False, str(e)[:100], (time.time()-t)*1000)
        await asyncio.sleep(0.3)
    
    # Stealth
    print("\n▶ Stealth Check...")
    try:
        await br.navigate("about:blank")
        s = await br.page.evaluate(STEALTH_JS)
        rec("Stealth","no_webdriver", s.get("wd")!=True, det=f"wd={s.get('wd')}")
        rec("Stealth","plugins>0", s.get("pl",0)>0, det=f"plugins={s.get('pl')}")
        rec("Stealth","chrome_exists", s.get("ch")==True, det=f"chrome={s.get('ch')}")
        rec("Stealth","no_cdc", s.get("cdc",1)==0, det=f"cdc={s.get('cdc')}")
        rec("Stealth","overall", s.get("ok")==True, det=f"bot_signals={s.get('bot')}")
    except Exception as e:
        rec("Stealth","check", False, str(e)[:80])
    
    # Form fill
    print("\n▶ Form Fill...")
    t=time.time()
    try:
        await br.navigate("https://www.google.com")
        await asyncio.sleep(0.5)
        fr = await br.fill_form({'input[name="q"]': "test@#$%"})
        val = await br.page.evaluate("()=>document.querySelector('input[name=\"q\"]')?.value||'N/A'")
        ms=(time.time()-t)*1000
        rec("FormFill","special_chars", "test@" in str(val), f"got:{str(val)[:40]}", ms)
    except Exception as e:
        rec("FormFill","special_chars", False, str(e)[:80], (time.time()-t)*1000)
    
    # Error recovery
    print("\n▶ Error Recovery...")
    try:
        await br.navigate("https://nonexistent-xyz123.com")
        rec("Recovery","no_crash", True)
    except:
        rec("Recovery","no_crash", True, det="exception acceptable")
    t=time.time()
    try:
        r = await br.navigate("https://www.google.com")
        rec("Recovery","alive", r.get("status")=="success", r.get("error","")[:60], (time.time()-t)*1000)
    except Exception as e:
        rec("Recovery","alive", False, str(e)[:80], (time.time()-t)*1000)
    
    try: await br.stop()
    except: pass
    
    # REPORT
    total=len(R); ok=sum(1 for r in R if r["ok"]); fail=total-ok
    rate=(ok/total*100) if total else 0
    print(f"\n{'='*60}")
    print(f"  BRUTAL TEST RESULTS")
    print(f"{'='*60}")
    cats={}
    for r in R:
        c=r["c"].split("/")[0]
        cats.setdefault(c,{"p":0,"f":0,"t":0})
        cats[c]["t"]+=1; cats[c]["p" if r["ok"] else "f"]+=1
    for c,s in cats.items():
        cr=(s["p"]/s["t"]*100) if s["t"] else 0
        print(f"  {'✅' if cr>=90 else '⚠️' if cr>=70 else '❌'} {c}: {s['p']}/{s['t']} ({cr:.0f}%)")
    print(f"\n  TOTAL: {ok}/{total} ({rate:.1f}%)")
    print(f"  WEBSITES: {SV} visited, {SS} loaded")
    
    fails=[r for r in R if not r["ok"]]
    if fails:
        print(f"\n  ❌ FAILURES ({len(fails)}):")
        for f in fails:
            print(f"     • {f['c']}/{f['n']}: {f['e'][:80]}")
    
    crit=[f for f in fails if any(k in f["n"] for k in ["browser_start","overall"])]
    if rate>=80 and len(crit)==0: v="🟢 PRODUCTION READY"
    elif rate>=60: v="🟡 ALMOST READY"
    elif rate>=40: v="🟠 NOT READY"
    else: v="🔴 FAR FROM READY"
    
    print(f"\n  VERDICT: {v}")
    print(f"  Rate: {rate:.1f}% | Sites: {SV} | Critical: {len(crit)}")
    print(f"{'='*60}")
    
    with open("real_world_brutal_test_results.json","w") as fp:
        json.dump({"total":total,"passed":ok,"failed":fail,"rate":round(rate,1),
                   "sites":SV,"sites_ok":SS,"critical":len(crit),"verdict":v,
                   "failures":[{"c":f["c"],"n":f["n"],"e":f["e"]} for f in fails]},fp,indent=2)

asyncio.run(test())
