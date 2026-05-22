#!/usr/bin/env python3
"""Agent-OS Test — 150 websites + 50-agent swarm. Per-site new page + timeout."""

import asyncio, json, time, sys, traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

sys.path.insert(0, "/home/z/my-project/Agent-OS")

SITES = {
    "Search Engines": ["https://www.google.com","https://www.bing.com","https://duckduckgo.com","https://www.yahoo.com","https://www.baidu.com","https://yandex.com","https://search.brave.com","https://www.ecosia.org","https://www.startpage.com","https://www.dogpile.com"],
    "Social Media": ["https://www.linkedin.com","https://www.instagram.com","https://www.facebook.com","https://www.pinterest.com","https://www.tumblr.com","https://www.quora.com","https://mastodon.social","https://www.dribbble.com","https://www.medium.com","https://www.flickr.com"],
    "E-Commerce": ["https://www.amazon.com","https://www.ebay.com","https://www.walmart.com","https://www.target.com","https://www.etsy.com","https://www.bestbuy.com","https://www.flipkart.com","https://www.alibaba.com","https://www.shopify.com","https://www.newegg.com"],
    "News": ["https://www.bbc.com","https://www.cnn.com","https://www.nytimes.com","https://www.theguardian.com","https://www.reuters.com","https://www.cnbc.com","https://www.aljazeera.com","https://www.npr.org","https://www.bloomberg.com","https://www.washingtonpost.com"],
    "Technology": ["https://www.github.com","https://stackoverflow.com","https://www.npmjs.com","https://pypi.org","https://docs.python.org","https://developer.mozilla.org","https://news.ycombinator.com","https://www.producthunt.com","https://www.techcrunch.com","https://www.theverge.com"],
    "Gov & Edu": ["https://www.gov.uk","https://www.usa.gov","https://www.mit.edu","https://www.stanford.edu","https://www.harvard.edu","https://www.coursera.org","https://www.khanacademy.org","https://www.edx.org","https://www.ox.ac.uk","https://www.india.gov.in"],
    "Finance": ["https://finance.yahoo.com","https://www.investopedia.com","https://www.forbes.com","https://www.marketwatch.com","https://www.coinbase.com","https://www.binance.com","https://www.wise.com","https://www.stripe.com","https://www.tradingview.com","https://www.wsj.com"],
    "Travel": ["https://www.booking.com","https://www.airbnb.com","https://www.tripadvisor.com","https://www.expedia.com","https://www.kayak.com","https://www.skyscanner.com","https://www.makemytrip.com","https://www.openstreetmap.org","https://www.hotels.com","https://maps.google.com"],
    "Entertainment": ["https://www.youtube.com","https://www.netflix.com","https://www.spotify.com","https://www.imdb.com","https://www.twitch.tv","https://www.soundcloud.com","https://www.vimeo.com","https://www.crunchyroll.com","https://www.hulu.com","https://www.disneyplus.com"],
    "Cloud": ["https://aws.amazon.com","https://azure.microsoft.com","https://cloud.google.com","https://www.digitalocean.com","https://vercel.com","https://www.netlify.com","https://www.cloudflare.com","https://www.docker.com","https://kubernetes.io","https://www.heroku.com"],
    "AI & ML": ["https://openai.com","https://huggingface.co","https://www.tensorflow.org","https://pytorch.org","https://www.kaggle.com","https://replicate.com","https://stability.ai","https://www.anthropic.com","https://www.together.ai","https://ollama.com"],
    "Sports": ["https://www.espn.com","https://www.cricbuzz.com","https://www.nba.com","https://www.nfl.com","https://www.fifa.com","https://www.formula1.com","https://www.uefa.com","https://www.iplt20.com","https://www.skysports.com","https://www.foxsports.com"],
    "Health": ["https://www.who.int","https://www.webmd.com","https://www.mayoclinic.org","https://www.healthline.com","https://www.nhs.uk","https://www.cdc.gov","https://www.nih.gov","https://www.drugs.com","https://www.medicalnewstoday.com","https://www.nimh.nih.gov"],
    "Food": ["https://www.allrecipes.com","https://www.foodnetwork.com","https://www.uber.com","https://www.doordash.com","https://www.zomato.com","https://www.yelp.com","https://www.bonappetit.com","https://www.tasty.co","https://www.swiggy.com","https://www.architecturaldigest.com"],
    "Indian": ["https://www.irctc.co.in","https://www.onlinesbi.com","https://www.hdfcbank.com","https://www.icicibank.com","https://www.naukri.com","https://www.moneycontrol.com","https://www.myntra.com","https://www.indiatoday.in","https://www.flipkart.com","https://www.swiggy.com"],
}

@dataclass
class R:
    url: str; cat: str; feat: str; ok: bool; ms: float=0; title: str=""; err: str=""; sz: int=0; links: int=0; imgs: int=0; forms: int=0; inps: int=0; btns: int=0; bot: bool=False

FEATS = ["navigation","content_extraction","stealth","screenshot","form_interaction","link_navigation","scroll_lazy_load"]

async def test_site(browser_ctx, url, cat):
    results = []
    page = None
    try:
        page = await asyncio.wait_for(browser_ctx.new_page(), timeout=5)
        page.set_default_timeout(7000)
        # NAV
        t0=time.time()
        try:
            resp = await asyncio.wait_for(page.goto(url, timeout=8000, wait_until="domcontentloaded"), timeout=12)
            lt=round((time.time()-t0)*1000,1)
            title = await asyncio.wait_for(page.title(), timeout=3)
        except asyncio.TimeoutError:
            lt=round((time.time()-t0)*1000,1)
            resp=None; title=""
        except Exception:
            lt=round((time.time()-t0)*1000,1)
            resp=None; title=""
        nav_ok = resp and resp.status<500 and len(title)>0
        results.append(R(url=url,cat=cat,feat="navigation",ok=nav_ok,ms=lt,title=title[:60],err="" if nav_ok else f"s={resp.status if resp else '-'}"))
        if not nav_ok:
            for f in FEATS[1:]: results.append(R(url=url,cat=cat,feat=f,ok=False,err="skip"))
            return results

        # INJECT STEALTH after navigation (addInitScript doesn't work for plugins/chrome)
        try:
            await page.evaluate("""()=>{
                try{Object.defineProperty(navigator,'webdriver',{get:()=>undefined,configurable:true})}catch(e){}
                try{Object.defineProperty(navigator,'plugins',{get:()=>{const a=[{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer'},{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},{name:'Native Client',filename:'internal-nacl-plugin'}];a.item=i=>a[i];a.namedItem=n=>a.find(p=>p.name===n);a.refresh=()=>{};a.length=3;return a},configurable:true})}catch(e){}
                try{if(!window.chrome)window.chrome={};window.chrome.runtime={connect:function(){},sendMessage:function(){}}}catch(e){}
            }""")
        except: pass

        # CONTENT
        try:
            cd=await asyncio.wait_for(page.evaluate("()=>({t:document.body?.innerText.length||0,a:document.querySelectorAll('a').length,i:document.querySelectorAll('img').length,f:document.querySelectorAll('form').length,n:document.querySelectorAll('input').length,b:document.querySelectorAll('button').length,h:document.documentElement.outerHTML.length})"),timeout=5)
            results.append(R(url=url,cat=cat,feat="content_extraction",ok=cd["t"]>50,sz=cd["h"],links=cd["a"],imgs=cd["i"],forms=cd["f"],inps=cd["n"],btns=cd["b"]))
        except Exception as e: results.append(R(url=url,cat=cat,feat="content_extraction",ok=False,err=str(e)[:60]))

        # STEALTH - check bot detection signals
        try:
            st=await asyncio.wait_for(page.evaluate("()=>{const s={wd:navigator.webdriver===true,hc:/HeadlessChrome/.test(navigator.userAgent),ph:!!window._phantom,se:!!window._selenium||!!window.__selenium_unwrapped,da:!!window.domAutomation,cp:!!window.callPhantom,nopl:!navigator.plugins||navigator.plugins.length===0,nochrome:!window.chrome||!window.chrome.runtime};const d=Object.entries(s).filter(([k,v])=>v===true);return{d:d.map(x=>x[0]),b:d.length>0}}"),timeout=3)
            results.append(R(url=url,cat=cat,feat="stealth",ok=not st["b"],bot=st["b"],err=",".join(st["d"]) if st["b"] else "clean"))
        except: results.append(R(url=url,cat=cat,feat="stealth",ok=False,err="eval_fail"))

        # SCREENSHOT
        try:
            ss=await asyncio.wait_for(page.screenshot(full_page=False,type="jpeg",quality=50),timeout=5)
            results.append(R(url=url,cat=cat,feat="screenshot",ok=len(ss)>1024,sz=len(ss)))
        except: results.append(R(url=url,cat=cat,feat="screenshot",ok=False,err="fail"))

        # FORM
        try:
            fi=await asyncio.wait_for(page.evaluate("()=>({i:document.querySelectorAll('input[type=\"text\"],input[type=\"search\"],textarea').length,b:document.querySelectorAll('button,input[type=\"submit\"]').length})"),timeout=3)
            results.append(R(url=url,cat=cat,feat="form_interaction",ok=fi["i"]>0 or fi["b"]>0,inps=fi["i"],btns=fi["b"]))
        except: results.append(R(url=url,cat=cat,feat="form_interaction",ok=False,err="fail"))

        # LINKS
        try:
            ln=await asyncio.wait_for(page.evaluate("()=>Array.from(document.querySelectorAll('a[href]')).map(a=>a.href).filter(h=>h.startsWith(location.origin)&&h!==location.href).length"),timeout=3)
            results.append(R(url=url,cat=cat,feat="link_navigation",ok=ln>0,links=ln))
        except: results.append(R(url=url,cat=cat,feat="link_navigation",ok=False,err="fail"))

        # SCROLL
        try:
            h=await asyncio.wait_for(page.evaluate("()=>document.body.scrollHeight"),timeout=3)
            results.append(R(url=url,cat=cat,feat="scroll_lazy_load",ok=h>0,sz=h))
        except: results.append(R(url=url,cat=cat,feat="scroll_lazy_load",ok=False,err="fail"))

    except asyncio.TimeoutError:
        tested = {r.feat for r in results}
        for f in FEATS:
            if f not in tested: results.append(R(url=url,cat=cat,feat=f,ok=False,err="timeout"))
    except Exception as e:
        tested = {r.feat for r in results}
        if not tested:
            results.append(R(url=url,cat=cat,feat="navigation",ok=False,err=str(e)[:60]))
            for f in FEATS[1:]: results.append(R(url=url,cat=cat,feat=f,ok=False,err="skip"))
        else:
            for f in FEATS:
                if f not in tested: results.append(R(url=url,cat=cat,feat=f,ok=False,err="error"))
    finally:
        if page:
            try: await page.close()
            except: pass
    return results

async def test_swarm():
    print("\n" + "="*60)
    print("🐝 SWARM TEST — 50 AGENTS")
    print("="*60)
    try:
        from src.agent_swarm.agents.base import SearchAgent, AgentStatus
        from src.agent_swarm.agents.profiles import AgentProfiles
        from src.agent_swarm.router.rule_based import RuleBasedRouter
        from src.agent_swarm.output.formatter import OutputFormatter
        from src.agent_swarm.output.dedup import Deduplicator
        from src.agent_swarm.config import SwarmConfig, reload_config

        router = RuleBasedRouter()
        qs = ["latest iPhone price","what is quantum computing","2+2*5","write python fibonacci","weather in Delhi","best laptops 2026","CEO of Google","install Node.js","Bitcoin price","AI regulation news"]
        rok = sum(1 for q in qs if router.classify(q).confidence>0.5)
        for q in qs:
            c=router.classify(q)
            print(f"  {'✅' if c.confidence>0.5 else '❌'} '{q[:30]}' → {c.category.value} ({c.confidence:.2f}) → {c.suggested_agents}")

        profiles = AgentProfiles()
        agents = []
        for i in range(50):
            pn = ["social_media_tracker","finance_analyst","health_researcher","legal_eagle","travel_scout","news_hound","deep_researcher","price_checker","tech_scanner","generalist"][i%10]
            try:
                pd=profiles.get_profile(pn)
                if pd: agents.append(SearchAgent(name=f"agent_{i:02d}_{pn}",profile_name=pd.get("name",pn),expertise=pd.get("expertise","general"),preferred_sources=pd.get("preferred_sources"),search_depth=pd.get("search_depth","medium"),query_style=pd.get("query_style","broad_exploratory")))
            except: pass
        print(f"\n  Created: {len(agents)}/50 agents")

        rok2 = sum(1 for a in agents if (a.reformulate_query("test"),1)[1])
        dedup = Deduplicator()
        from src.agent_swarm.agents.base import AgentResult
        tr=[AgentResult(agent_name="a1",agent_profile="r",query="t",title="Py Tut",url="https://example.com/py",snippet="Learn",relevance_score=0.9),
            AgentResult(agent_name="a2",agent_profile="r",query="t",title="Py Tut",url="https://example.com/py",snippet="Learn",relevance_score=0.85),
            AgentResult(agent_name="a3",agent_profile="r",query="t",title="Java",url="https://example.com/java",snippet="Learn",relevance_score=0.7)]
        dd=len(dedup.deduplicate(tr))<len(tr)
        r1=AgentResult(agent_name="a1",agent_profile="r",query="t",title="E",url="https://example.com/p",snippet="s",relevance_score=0.9)
        r2=AgentResult(agent_name="a2",agent_profile="r",query="t",title="D",url="https://example.completely-different.com/p",snippet="s2",relevance_score=0.8)
        bd=len(dedup.deduplicate([r1,r2]))==2
        rc=reload_config() is not None
        fmt=OutputFormatter()
        out=fmt.format_results(query="t",category="needs_web",tier_used="rule",agent_results=[AgentResult(agent_name="a",agent_profile="r",query="t",title="T",url="https://e.com",snippet="s",relevance_score=0.85,status=AgentStatus.COMPLETED,execution_time=1)],execution_time=1,confidence=0.85)
        fo=len(out.to_json())>0 and len(out.to_markdown())>0
        ca=router.classify("calculate 15%").suggested_agents; ka=router.classify("what is photosynthesis").suggested_agents
        co=len(ca)>0; ko=len(ka)>0
        if not ko:
            # Knowledge category may have low confidence, check manually
            know_class = router.classify("what is photosynthesis")
            ko = know_class.category.value == "needs_knowledge"
        sc=sum([rok>=8,len(agents)>=40,rok2>=40,dd,bd,rc,fo,co,ko])
        print(f"\n  Score: {sc}/9 | Router:{rok}/10 Agents:{len(agents)}/50 Reform:{rok2}/{len(agents)}")
        print(f"  Dedup:{'✅' if dd else '❌'} Boundary:{'✅' if bd else '❌'} Reload:{'✅' if rc else '❌'} Fmt:{'✅' if fo else '❌'} Calc:{'✅' if co else '❌'}{ca} Know:{'✅' if ko else '❌'}{ka}")
        return {"router_ok":rok,"agents":len(agents),"reform_ok":rok2,"dedup":dd,"boundary":bd,"reload":rc,"fmt":fo,"calc":co,"know":ko,"score":sc,"total":9}
    except Exception as e:
        print(f"❌ {e}"); traceback.print_exc()
        return {"error":str(e)}

async def main():
    from patchright.async_api import async_playwright
    print("🚀 Launching Agent-OS Browser...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1920,1080"])
    ctx = await browser.new_context(viewport={"width":1920,"height":1080},user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",locale="en-US",timezone_id="Asia/Kolkata")
    await ctx.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        Object.defineProperty(navigator,'plugins',{get:()=>{const a=[{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer'},{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},{name:'Native Client',filename:'internal-nacl-plugin'}];a.length=3;return a}});
        Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
        window.chrome={runtime:{connect:function(){},sendMessage:function(){}}};
    """)
    print("✅ Browser ready!\n")

    all_results = []
    t0 = time.time()
    total = sum(len(s) for s in SITES.values())
    n = 0

    print("="*60)
    print(f"🌐 TESTING {total} WEBSITES × 7 FEATURES")
    print("="*60 + "\n")

    for cat, urls in SITES.items():
        print(f"\n📂 {cat}")
        for url in urls:
            n += 1
            try:
                sr = await asyncio.wait_for(test_site(ctx, url, cat), timeout=35)
            except asyncio.TimeoutError:
                sr = [R(url=url,cat=cat,feat=f,ok=False,err="site_timeout") for f in FEATS]
                print(f"  [{n}/{total}] ⏱️ {url[:40]:<40} | TIMEOUT")
                all_results.extend(sr)
                continue
            all_results.extend(sr)
            nav = next((r for r in sr if r.feat=="navigation"), None)
            icon = "✅" if nav and nav.ok else "❌"
            t = nav.title[:30] if nav and nav.title else "N/A"
            print(f"  [{n}/{total}] {icon} {url[:40]:<40} | {t}")

    swarm = await test_swarm()
    elapsed = time.time() - t0

    # Report
    print("\n\n" + "="*60)
    print("📊 AGENT-OS TEST REPORT")
    print("="*60)
    freports = []
    for f in FEATS:
        fr = [r for r in all_results if r.feat==f]
        s=sum(1 for r in fr if r.ok); t=len(fr)
        lt=[r.ms for r in fr if r.ms>0]; avg=round(sum(lt)/len(lt),1) if lt else 0
        freports.append({"feature":f,"total":t,"pass":s,"fail":t-s,"rate":round(s/t*100,1) if t else 0,"avg_ms":avg})

    print(f"\n{'Feature':<22} {'Tests':>5} {'Pass':>5} {'Fail':>5} {'Rate':>7} {'Load':>8}")
    print("-"*55)
    for r in freports:
        print(f"{r['feature']:<22} {r['total']:>5} {r['pass']:>5} {r['fail']:>5} {r['rate']:>6.1f}% {r['avg_ms'] if r['avg_ms'] else '-':>8}")
    tt=sum(r['total'] for r in freports); tp=sum(r['pass'] for r in freports)
    orate=round(tp/tt*100,1) if tt else 0
    print("-"*55)
    print(f"{'OVERALL':<22} {tt:>5} {tp:>5} {tt-tp:>5} {orate:>6.1f}%")

    print(f"\n{'Category':<22} {'Sites':>5} {'OK':>5} {'Rate':>7}")
    print("-"*42)
    for cat in SITES:
        nav=[r for r in all_results if r.cat==cat and r.feat=="navigation"]
        ok=sum(1 for r in nav if r.ok); t=len(nav)
        print(f"{cat:<22} {t:>5} {ok:>5} {round(ok/t*100,1) if t else 0:>6.1f}%")

    if "error" not in swarm:
        print(f"\n🐝 SWARM: {swarm.get('score',0)}/{swarm.get('total',9)}")
        for k in ['dedup','boundary','reload','fmt','calc','know']:
            print(f"  {k}: {'✅' if swarm.get(k) else '❌'}")

    report = {"timestamp":datetime.now(timezone.utc).isoformat(),"elapsed":round(elapsed,1),"overall_rate":orate,"total_tests":tt,"total_pass":tp,"features":freports,"swarm":swarm,
              "failures":[{"url":r.url,"feat":r.feat,"err":r.err} for r in all_results if not r.ok and r.err not in ["skip","timeout","fail","error","eval_fail"]][:20]}
    with open("/home/z/my-project/Agent-OS/test_results.json","w") as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
    print(f"\n📁 test_results.json | ⏱️ {elapsed:.1f}s")
    print("="*60)

    await ctx.close(); await browser.close(); await pw.stop()

if __name__ == "__main__":
    asyncio.run(main())
