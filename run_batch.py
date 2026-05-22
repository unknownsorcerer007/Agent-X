#!/usr/bin/env python3
"""Batch stress test runner - saves results incrementally."""
import asyncio, sys, time, json, resource, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from src.core.config import Config
from src.core.browser import AgentBrowser

BLOCK_INDICATORS = ['access denied','captcha required','bot detected','just a moment','checking your browser','please verify you are human','unusual traffic','are you a robot','bot or not','access to this page has been denied','blocked by waf','security check required','managed challenge','request denied','your request was blocked','automated access']
SKIP_BLOCK_DOMAINS = ['cloudflare.com','amazon.com','amazon.co.uk']

def is_blocked(title, text, url=''):
    if url and any(d in url.lower() for d in SKIP_BLOCK_DOMAINS): return False
    combined = (title+' '+text[:500]).lower()
    return any(ind in combined for ind in BLOCK_INDICATORS)

async def test_site(browser, tier, name, url, timeout_ms=12000):
    t0 = time.time()
    try:
        page = await browser.context.new_page()
        try:
            resp = await page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
            await asyncio.sleep(1.0)
            title = await page.title()
            sc = resp.status if resp else 0
            body = ''
            try: body = await page.evaluate("() => document.body ? document.body.innerText.substring(0,800) : ''")
            except: pass
            blocked = is_blocked(title, body, url)
            if blocked: return {'tier':tier,'name':name,'passed':False,'blocked':True,'status':'blocked','sc':sc,'time':round(time.time()-t0,2)}
            if resp and resp.status in (200,201,202,301,302,401): return {'tier':tier,'name':name,'passed':True,'blocked':False,'status':'success','sc':sc,'time':round(time.time()-t0,2)}
            if resp and resp.status == 403: return {'tier':tier,'name':name,'passed':False,'blocked':blocked,'status':'blocked' if blocked else 'forbidden','sc':sc,'time':round(time.time()-t0,2)}
            if resp and resp.status == 429: return {'tier':tier,'name':name,'passed':False,'blocked':True,'status':'rate_limited','sc':sc,'time':round(time.time()-t0,2)}
            return {'tier':tier,'name':name,'passed':False,'blocked':blocked,'status':f'http_{sc}','sc':sc,'time':round(time.time()-t0,2)}
        finally: await page.close()
    except asyncio.TimeoutError: return {'tier':tier,'name':name,'passed':False,'blocked':False,'status':'timeout','sc':0,'time':round(time.time()-t0,2),'error':'TIMEOUT'}
    except Exception as e: return {'tier':tier,'name':name,'passed':False,'blocked':False,'status':'error','sc':0,'time':round(time.time()-t0,2),'error':str(e)[:60]}

RESULTS_FILE = Path('/home/z/my-project/download/batch_results.json')

async def run():
    batch = int(os.environ.get('BATCH', '1'))
    config = Config()
    config.set('browser.headless', True)
    config.set('browser.max_ram_mb', 800)
    browser = AgentBrowser(config)
    await browser.start()
    print(f'Browser OK (batch {batch})', flush=True)

    SITES = {
        1: [  # EASY (30)
            ('easy','Example','https://example.com',10000),
            ('easy','HTTPBin','https://httpbin.org/get',10000),
            ('easy','Wikipedia','https://www.wikipedia.org',10000),
            ('easy','WikiEN','https://en.wikipedia.org/wiki/Main_Page',10000),
            ('easy','GNU','https://www.gnu.org',10000),
            ('easy','Kernel','https://www.kernel.org',10000),
            ('easy','Archive','https://archive.org',10000),
            ('easy','Debian','https://www.debian.org',10000),
            ('easy','Ubuntu','https://www.ubuntu.com',10000),
            ('easy','Python','https://www.python.org',10000),
            ('easy','Rust','https://www.rust-lang.org',10000),
            ('easy','Node','https://nodejs.org',10000),
            ('easy','Go','https://golang.org',10000),
            ('easy','SQLite','https://www.sqlite.org',10000),
            ('easy','PostgreSQL','https://www.postgresql.org',10000),
            ('easy','Redis','https://redis.io',10000),
            ('easy','MongoDB','https://www.mongodb.com',10000),
            ('easy','Nginx','https://nginx.org',10000),
            ('easy','Apache','https://httpd.apache.org',10000),
            ('easy','HN','https://news.ycombinator.com',10000),
            ('easy','DDG','https://duckduckgo.com',10000),
            ('easy','HTTPBinIP','https://httpbin.org/ip',10000),
            ('easy','HTTPBinUA','https://httpbin.org/user-agent',10000),
            ('easy','CouchDB','https://couchdb.apache.org',10000),
            ('easy','HTTPBinH','https://httpbin.org/headers',10000),
            ('easy','Caddy','https://caddyserver.com',10000),
            ('easy','Lobsters','https://lobste.rs',10000),
            ('easy','FSF','https://www.fsf.org',10000),
            ('easy','PyDocs','https://docs.python.org',10000),
            ('easy','Ruby','https://www.ruby-lang.org',10000),
        ],
        2: [  # MEDIUM (30)
            ('medium','Cloudflare','https://www.cloudflare.com',15000),
            ('medium','DigitalOcean','https://www.digitalocean.com',15000),
            ('medium','Heroku','https://www.heroku.com',15000),
            ('medium','Netlify','https://www.netlify.com',15000),
            ('medium','Vercel','https://vercel.com',15000),
            ('medium','NPM','https://www.npmjs.com',15000),
            ('medium','Docker','https://www.docker.com',15000),
            ('medium','DockerHub','https://hub.docker.com',15000),
            ('medium','K8s','https://kubernetes.io',15000),
            ('medium','Grafana','https://grafana.com',15000),
            ('medium','Shopify','https://shopify.com',15000),
            ('medium','Stripe','https://www.stripe.com',15000),
            ('medium','PayPal','https://www.paypal.com',15000),
            ('medium','LinkedIn','https://www.linkedin.com',15000),
            ('medium','Microsoft','https://www.microsoft.com',15000),
            ('medium','Apple','https://www.apple.com',15000),
            ('medium','Salesforce','https://www.salesforce.com',15000),
            ('medium','Adobe','https://www.adobe.com',15000),
            ('medium','Medium','https://medium.com',15000),
            ('medium','DevTo','https://dev.to',15000),
            ('medium','SO','https://stackoverflow.com',15000),
            ('medium','GitHub','https://github.com',15000),
            ('medium','GitLab','https://gitlab.com',15000),
            ('medium','Bitbucket','https://bitbucket.org',15000),
            ('medium','Atlassian','https://www.atlassian.com',15000),
            ('medium','Figma','https://www.figma.com',15000),
            ('medium','Notion','https://www.notion.so',15000),
            ('medium','Slack','https://slack.com',15000),
            ('medium','Square','https://squareup.com',15000),
            ('medium','Datadog','https://www.datadog.com',15000),
        ],
        3: [  # HARD (30)
            ('hard','Amazon','https://www.amazon.com',20000),
            ('hard','AmazonUK','https://www.amazon.co.uk',20000),
            ('hard','eBay','https://www.ebay.com',20000),
            ('hard','Walmart','https://www.walmart.com',20000),
            ('hard','Target','https://www.target.com',20000),
            ('hard','BestBuy','https://www.bestbuy.com',20000),
            ('hard','HomeDepot','https://www.homedepot.com',20000),
            ('hard','Lowes','https://www.lowes.com',20000),
            ('hard','Costco','https://www.costco.com',20000),
            ('hard','Etsy','https://www.etsy.com',20000),
            ('hard','Zillow','https://www.zillow.com',20000),
            ('hard','Realtor','https://www.realtor.com',20000),
            ('hard','Indeed','https://www.indeed.com',20000),
            ('hard','Glassdoor','https://www.glassdoor.com',20000),
            ('hard','Reddit','https://www.reddit.com',20000),
            ('hard','RedditOld','https://old.reddit.com',20000),
            ('hard','Quora','https://www.quora.com',20000),
            ('hard','Twitter','https://twitter.com',20000),
            ('hard','Instagram','https://www.instagram.com',20000),
            ('hard','Facebook','https://www.facebook.com',20000),
            ('hard','TikTok','https://www.tiktok.com',20000),
            ('hard','Pinterest','https://www.pinterest.com',20000),
            ('hard','Yelp','https://www.yelp.com',20000),
            ('hard','TripAdvisor','https://www.tripadvisor.com',20000),
            ('hard','Booking','https://www.booking.com',20000),
            ('hard','Expedia','https://www.expedia.com',20000),
            ('hard','Airbnb','https://www.airbnb.com',20000),
            ('hard','Kayak','https://www.kayak.com',20000),
            ('hard','WashPost','https://www.washingtonpost.com',20000),
            ('hard','NYTimes','https://www.nytimes.com',20000),
        ],
        4: [  # EXTREME (30)
            ('extreme','WSJ','https://www.wsj.com',20000),
            ('extreme','Bloomberg','https://www.bloomberg.com',20000),
            ('extreme','Reuters','https://www.reuters.com',20000),
            ('extreme','Guardian','https://www.theguardian.com',20000),
            ('extreme','BBC','https://www.bbc.com',20000),
            ('extreme','CNN','https://www.cnn.com',20000),
            ('extreme','FoxNews','https://www.foxnews.com',20000),
            ('extreme','CNBC','https://www.cnbc.com',20000),
            ('extreme','Forbes','https://www.forbes.com',20000),
            ('extreme','BizInsider','https://www.businessinsider.com',20000),
            ('extreme','Vice','https://www.vice.com',20000),
            ('extreme','Wired','https://www.wired.com',20000),
            ('extreme','TechCrunch','https://techcrunch.com',20000),
            ('extreme','TheVerge','https://www.theverge.com',20000),
            ('extreme','ArsTech','https://arstechnica.com',20000),
            ('extreme','Tumblr','https://www.tumblr.com',20000),
            ('extreme','Trulia','https://www.trulia.com',20000),
            ('extreme','Monster','https://www.monster.com',20000),
            ('extreme','ZipRecruiter','https://www.ziprecruiter.com',20000),
            ('extreme','Priceline','https://www.priceline.com',20000),
            ('extreme','Oracle','https://www.oracle.com',20000),
            ('extreme','SAP','https://www.sap.com',20000),
            ('extreme','ServiceNow','https://www.servicenow.com',20000),
            ('extreme','Workday','https://www.workday.com',20000),
            ('extreme','Twilio','https://www.twilio.com',20000),
            ('extreme','Okta','https://www.okta.com',20000),
            ('extreme','CFDash','https://dash.cloudflare.com',20000),
            ('extreme','Auth0','https://auth0.com',20000),
            ('extreme','Discord','https://discord.com',20000),
            ('extreme','Spotify','https://www.spotify.com',20000),
        ],
        5: [  # NIGHTMARE (30)
            ('nightmare','CreepJS','https://abrahamjuliot.github.io/creepjs/',25000),
            ('nightmare','Pixelscan','https://pixelscan.net',25000),
            ('nightmare','BrowserLeaks','https://browserleaks.com/javascript',25000),
            ('nightmare','FPJS','https://fingerprintjs.github.io/fingerprintjs/',25000),
            ('nightmare','Incolumitas','https://bot.incolumitas.com/',25000),
            ('nightmare','Antcpt','https://antcpt.com/score_detector/',25000),
            ('nightmare','reCAPTCHA','https://www.google.com/recaptcha/api2/demo',25000),
            ('nightmare','CFTest','https://nowsecure.nl',25000),
            ('nightmare','Zappos','https://www.zappos.com',25000),
            ('nightmare','StubHub','https://www.stubhub.com',25000),
            ('nightmare','Ticketmaster','https://www.ticketmaster.com',25000),
            ('nightmare','ArtStation','https://www.artstation.com',25000),
            ('nightmare','FootLocker','https://www.footlocker.com',25000),
            ('nightmare','Slickdeals','https://slickdeals.net',25000),
            ('nightmare','Nike','https://www.nike.com',25000),
            ('nightmare','Adidas','https://www.adidas.com',25000),
            ('nightmare','Samsung','https://www.samsung.com',25000),
            ('nightmare','Canva','https://www.canva.com',25000),
            ('nightmare','DiscordLogin','https://discord.com/login',25000),
            ('nightmare','Coinbase','https://www.coinbase.com',25000),
            ('nightmare','Binance','https://www.binance.com',25000),
            ('nightmare','Robinhood','https://robinhood.com',25000),
            ('nightmare','Chase','https://www.chase.com',25000),
            ('nightmare','BoA','https://www.bankofamerica.com',25000),
            ('nightmare','WellsFargo','https://www.wellsfargo.com',25000),
            ('nightmare','CapitalOne','https://www.capitalone.com',25000),
            ('nightmare','Amex','https://www.americanexpress.com',25000),
            ('nightmare','Schwab','https://www.schwab.com',25000),
            ('nightmare','Fidelity','https://www.fidelity.com',25000),
            ('nightmare','Vanguard','https://investor.vanguard.com',25000),
        ],
    }

    sites = SITES.get(batch, SITES[1])
    results = []

    for i, (tier, name, url, tout) in enumerate(sites, 1):
        r = await test_site(browser, tier, name, url, tout)
        results.append(r)
        icon = 'Y' if r['passed'] else 'N'
        bl = ' [BLK]' if r.get('blocked') else ''
        err = f' [{r.get("error","")[:20]}]' if r.get('error') else ''
        print(f'{icon} [{i:2d}/{len(sites)}] {tier:>10s}|{name:<16s}|{r["time"]:5.1f}s|{r["sc"]:3d}|{r["status"]}{bl}{err}', flush=True)
        await asyncio.sleep(0.2)

    await browser.stop()

    # Save results
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE) as f: existing = json.load(f)
        except: pass
    existing.extend(results)
    with open(RESULTS_FILE, 'w') as f: json.dump(existing, f, indent=2, ensure_ascii=False)

    passed = sum(1 for r in results if r['passed'])
    print(f'\nBatch {batch}: {passed}/{len(results)} passed', flush=True)

asyncio.run(run())
