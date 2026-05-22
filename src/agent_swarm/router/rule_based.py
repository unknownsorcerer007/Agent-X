"""Tier 1: Rule-based query router using regex patterns and keyword matching.

Production-ready: comprehensive patterns for all 5 categories with proper
priority ordering, anti-false-positive guards, and sub-category routing.
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class QueryCategory(str, Enum):
    """Query classification categories."""
    NEEDS_WEB = "needs_web"
    NEEDS_KNOWLEDGE = "needs_knowledge"
    NEEDS_CALCULATION = "needs_calculation"
    NEEDS_CODE = "needs_code"
    NEEDS_SECURITY = "needs_security"
    AMBIGUOUS = "ambiguous"


@dataclass
class QueryClassification:
    """Result of query classification."""
    category: QueryCategory
    confidence: float
    reason: str
    source: str = "rule_based"
    suggested_agents: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# SECURITY PATTERNS — checked FIRST (highest priority)
# Captcha, anti-bot, bypass queries must NOT be routed to calculation
# ═══════════════════════════════════════════════════════════════════

SECURITY_PATTERNS = [
    # Captcha solving / detection
    (r"(?i)\b(solve|bypass|beat|crack|break)\b.{0,20}\b(captcha|recaptcha|hcaptcha|turnstile|challenge)\b", 0.96),
    (r"(?i)\b(captcha|recaptcha|hcaptcha|turnstile)\b.{0,20}\b(solve|bypass|beat|crack|break|detect)\b", 0.96),
    (r"(?i)\b(captcha|recaptcha|hcaptcha)\b", 0.90),
    (r"(?i)\bsolve\b\s+(the\s+)?(captcha|recaptcha|hcaptcha|turnstile)\b", 0.97),

    # Cloudflare bypass / detection
    (r"(?i)\b(bypass|beat|crack|break|avoid|circumvent)\b.{0,25}\b(cloudflare|cf-|cf_|waf|firewall|bot\s+protect|protection)\b", 0.96),
    (r"(?i)\b(cloudflare|perimeterx|datadome|akamai|imperva|kasada|shape\s+security|arkose)\b.{0,25}\b(bypass|beat|crack|break|avoid|circumvent|detect|challenge)\b", 0.96),
    (r"(?i)\b(cloudflare|perimeterx|datadome|akamai\s+bot)\b.{0,15}\b(protect|protection|block|detect|challenge|bypass|fingerprint)\b", 0.95),
    (r"(?i)\b(bypass|beat|crack|break|avoid|circumvent)\b.{0,25}\b(protection|anti\s*bot|bot\s*guard|bot\s*shield)\b", 0.94),
    (r"(?i)\b(anti\s*bot|bot\s*detect|bot\s*protect|waf\s*bypass|fingerprint\s*spoof)\b", 0.94),

    # Stealth / evasion
    (r"(?i)\b(stealth|undetect|hide\s+fingerprint|spoof\s+fingerprint|tls\s+fingerprint|ja3|ja4)\b", 0.92),
    (r"(?i)\b(headless|webdriver|automation\s+detect|navigator\.webdriver)\b", 0.91),

    # Login / form automation (security-related browser tasks)
    (r"(?i)\b(fill|auto\s*fill|complete)\b.{0,20}\b(login|sign\s*in|auth|credential|form)\b", 0.88),
    (r"(?i)\b(fill|auto\s*fill|complete)\b\s+(the\s+)?(login|sign\s*in|auth|credential)\b", 0.92),
    (r"(?i)\b(auto\s*login|credential\s*vault|session\s*hijack|cookie\s*steal)\b", 0.90),
]

# ═══════════════════════════════════════════════════════════════════
# CALCULATION PATTERNS — checked SECOND (high priority)
# Math/conversion queries should NEVER be routed to web search
# BUT: "solve the captcha" must NOT match here — overridden by security
# ═══════════════════════════════════════════════════════════════════

CALCULATION_PATTERNS = [
    # Explicit math operators
    (r"(?i)\b\d+\s*[\+\-\*\/\^%]\s*\d+", 0.97),
    (r"(?i)\b\d+\s*(plus|minus|times|divided\s+by|multiplied\s+by|mod)\s*\d+", 0.95),

    # Explicit calculation keywords (but NOT "solve captcha")
    (r"(?i)\b(calculate|compute|eval)\b", 0.93),
    (r"(?i)\bsolve\b(?!.{0,25}\b(captcha|recaptcha|hcaptcha|turnstile|challenge|puzzle)\b)", 0.90),
    (r"(?i)\b(what\s+is)\s+\d+\s*[\+\-\*\/\^%]", 0.95),

    # Math functions
    (r"(?i)\b(sqrt|square\s+root|cube\s+root|nth\s+root)\b", 0.93),
    (r"(?i)\b(log|ln|log10|log2|logarithm)\b\s+(of|base)", 0.92),
    (r"(?i)\b(sin|cos|tan|arcsin|arccos|arctan|sec|csc|cot|sine|cosine|tangent)\b", 0.92),
    (r"(?i)\b(factorial|fibonacci|permutation|combination)\b", 0.91),

    # Matrix / linear algebra (standalone "matrix" + combined patterns)
    (r"(?i)\b(matrix|matrices)\b.{0,20}\b(determinant|inverse|transpose|eigenvalue|eigenvector|rank|trace|multiply|product)\b", 0.94),
    (r"(?i)\b(determinant|inverse|transpose|eigenvalue|eigenvector)\b.{0,20}\b(matrix|matrices)\b", 0.94),
    (r"(?i)\b(matrix\s+determinant|determinant\s+of\s+(a\s+)?matrix)\b", 0.95),
    (r"(?i)\b(calculate|compute|find|solve)\b.{0,15}\b(matrix|matrices)\b", 0.93),
    (r"(?i)\b(matrix)\b.{0,30}\b(multiply|add|subtract|divide|row|column|vector|scalar)\b", 0.92),

    # Compound interest / financial math (standalone "interest" + combined)
    (r"(?i)\b(compound\s+interest|simple\s+interest|amortization|annuity)\b", 0.95),
    (r"(?i)\b(calculate|compute|find|what\s+is)\b.{0,15}\b(interest|amortiz|annuity|principal)\b", 0.94),
    (r"(?i)\b(interest\s+rate|interest\s+on|rate\s+of\s+interest)\b", 0.93),
    (r"(?i)\b\d+%\s*interest\b", 0.92),

    # Geometry calculations (hypotenuse, pythagorean)
    (r"(?i)\b(hypotenuse|pythagorean)\b", 0.93),
    (r"(?i)\b(find|calculate|compute)\b.{0,15}\b(hypotenuse|distance|length\s+of)\b", 0.91),
    (r"(?i)\b(right\s+triangle|right-angled\s+triangle)\b.{0,20}\b(hypotenuse|side|length)\b", 0.92),

    # Percentage / fraction
    (r"(?i)\b(percentage\s+of|percent\s+of|percent\s+change|what\s+percent)\b", 0.92),
    (r"(?i)\b\d+\s*%\s*(of|off|increase|decrease|discount)\b", 0.91),
    (r"(?i)\b\d+\s*(percent|pc)\b", 0.85),

    # Unit conversions (length, weight, temperature, data, time)
    (r"(?i)\b(convert)\b.{0,20}\b(to|into|in)\b", 0.93),
    (r"(?i)\b(celsius|fahrenheit|kelvin)\b.{0,15}\b(to|in)\b", 0.93),
    (r"(?i)\b(km|miles?|meters?|yards?|feet|foot|inches?|cm|mm)\b.{0,10}\b(to|in)\b.{0,10}\b(km|miles?|meters?|yards?|feet|foot|inches?|cm|mm)\b", 0.94),
    (r"(?i)\b(kg|lbs?|pounds?|grams?|ounces?|oz|tonnes?)\b.{0,10}\b(to|in)\b.{0,10}\b(kg|lbs?|pounds?|grams?|ounces?|oz|tonnes?)\b", 0.94),
    (r"(?i)\b(bytes?|kb|mb|gb|tb|pb)\b.{0,10}\b(to|in)\b.{0,10}\b(bytes?|kb|mb|gb|tb|pb)\b", 0.92),

    # Area/volume
    (r"(?i)\b(area\s+of)\b.{0,20}\b(circle|triangle|rectangle|square|sphere|cylinder|cone|trapezoid|rhombus|parallelogram)\b", 0.94),
    (r"(?i)\b(volume\s+of)\b.{0,20}\b(sphere|cylinder|cone|cube|cuboid|box|pyramid)\b", 0.94),
    (r"(?i)\b(perimeter\s+of|circumference\s+of)\b.{0,20}\b(circle|triangle|rectangle|square)\b", 0.93),

    # Common math queries
    (r"(?i)\b(gcd|lcm|hcf)\b.{0,10}\b(of|and)\b", 0.92),
    (r"(?i)\b(standard\s+deviation|variance|mean|median|mode)\b.{0,15}\b(of|for)\b", 0.91),
    (r"(?i)\b(standard\s+deviation|variance|mean|median|mode)\b\s*\[", 0.92),
    (r"(?i)\b(derivative|integral|differentiate|integrate)\b", 0.91),
    (r"(?i)\b(average|mean)\b.{0,10}\b(of|for)\b", 0.85),
    (r"(?i)\b(binary|hex|hexadecimal|octal)\b.{0,10}\b(of|for|convert)\b", 0.90),
    (r"(?i)\b(prime\s+number|is\s+\d+\s+prime)\b", 0.90),
    (r"(?i)\b(factorial\s+of)\b", 0.91),
    (r"(?i)\b(power\s+of|raised\s+to|to\s+the\s+power)\b", 0.92),
    (r"(?i)\b\d+\s*(\^|\*\*)\s*\d+\b", 0.95),
    (r"(?i)\b(round|floor|ceil)\b.{0,10}\b(\d+|number|value)\b", 0.87),

    # "n choose k" / combinations
    (r"(?i)\b\d+\s+choose\s+\d+", 0.94),
    (r"(?i)\bcombination|permutation\b.{0,10}\b(of|calculate)\b", 0.90),

    # Time/seconds conversions
    (r"(?i)\b(seconds?|minutes?|hours?|days?)\b.{0,10}\b(in|per)\b.{0,10}\b(day|hour|minute|week|month|year)\b", 0.90),

    # Roman numerals
    (r"(?i)\b(roman\s+numeral)\b.{0,10}\b(for|of|convert)\b", 0.91),
]


# ═══════════════════════════════════════════════════════════════════
# CODE PATTERNS — checked SECOND
# Code generation/debugging/implementation queries
# ═══════════════════════════════════════════════════════════════════

CODE_PATTERNS = [
    # Explicit code generation
    (r"(?i)\b(write|create|generate|build)\b.{0,30}\b(code|program|script|function|class|module|api|rest|endpoint|service|app|application)\b", 0.90),
    (r"(?i)\b(code|program|script|function|class|module)\b.{0,15}\b(for|that|which|to)\b", 0.85),

    # Language-specific code
    (r"(?i)(?:python|javascript|java|cpp|c\+\+|rust|typescript|golang|ruby|c#|sql|node\.?js|php|swift|kotlin|scala|r\b|matlab|perl|dart|lua|elixir|haskell).{0,40}(?:code|example|snippet|program|function|class|method|implementation|module|linked\s+list|binary\s+tree|hash\s+map|stack|queue|graph)", 0.89),
    (r"(?i)\b(implement|code|write|create|build)\b.{0,30}\b(in\s+(python|javascript|java|cpp|c\+\+|rust|typescript|golang|ruby|c#|sql|node\.?js|php|swift|kotlin|scala))\b", 0.91),
    (r"(?i)\b(implement|create|write|build)\b.{0,30}\b(linked\s+list|binary\s+tree|hash\s+map|stack|queue|graph|sort|search|algorithm|data\s+structure)\b", 0.90),

    # Debugging / fixing
    (r"(?i)\b(debug|fix|refactor|optimize|troubleshoot)\b.{0,30}\b(code|bug|error|issue|exception|crash|stack\s+trace|performance|query|sql|database|memory\s+leak)\b", 0.88),
    (r"(?i)\b(error|exception|bug|crash)\b.{0,20}\b(in\s+(my|the|this)\s+)?(code|program|script|app|application)\b", 0.86),

    # How to implement
    (r"(?i)\b(how\s+to\s+(implement|code|write|create|build|develop))\b", 0.83),

    # Infrastructure / DevOps code
    (r"(?i)\b(dockerfile|docker-compose|kubernetes|k8s|helm|terraform|ansible)\b", 0.87),
    (r"(?i)\b(ci.?cd|pipeline|jenkins|github\s+actions|gitlab\s+ci)\b", 0.86),
    (r"(?i)\b(create|build|write|generate)\b.{0,30}\b(dockerfile|docker-compose|kubernetes|deployment|yaml|config|manifest)\b", 0.88),

    # Design patterns / architecture
    (r"(?i)\b(implement|create|build)\b.{0,30}\b(pub.?sub|observer|factory|singleton|middleware|rate\s+limit|caching|cache|proxy|adapter|strategy|event\s+sourcing|load\s+balancer|message\s+queue)\b", 0.87),
    (r"(?i)\b(load\s+balancer|message\s+queue|rate\s+limiter|circuit\s+breaker|service\s+mesh|api\s+gateway)\b", 0.86),
    (r"(?i)\b(refactor)\b.{0,20}\b(class|module|code|pattern|architecture|composition)\b", 0.86),

    # Write X in Y language (e.g., "write a load balancer in Go", "code a Fibonacci sequence in Python")
    # This MUST have higher confidence than calculation's fibonacci/factorial patterns
    # because "code/write/implement X in Python" is unambiguously asking for code
    (r"(?i)\b(write|code|create|build|implement)\b.{0,40}\b(in\s+(python|javascript|java|cpp|c\+\+|rust|typescript|golang|go|ruby|c#|sql|node\.?js|php|swift|kotlin|scala))\b", 0.93),

    # Database / schema code
    (r"(?i)\b(create|design|write)\b.{0,20}\b(schema|migration|sql|query|database|table|index)\b", 0.86),
    (r"(?i)\b(regex|regular\s+expression)\b.{0,15}\b(for|to|match|validate|pattern)\b", 0.88),

    # API / web service code
    (r"(?i)\b(rest\s+api|graphql|endpoint|microservice|backend|webhook)\b.{0,20}\b(create|build|implement|develop|node|python|java)\b", 0.87),
    (r"(?i)\b(create|build|develop)\b.{0,20}\b(rest\s+api|graphql|endpoint|microservice|backend|webhook|server)\b", 0.87),

    # Optimization
    (r"(?i)\b(optimize|tune|improve)\b.{0,20}\b(sql|query|database|performance|latency|throughput|algorithm|code)\b", 0.85),
]


# ═══════════════════════════════════════════════════════════════════
# KNOWLEDGE PATTERNS — checked THIRD
# Static knowledge / definitions / explanations / history
# These should NOT trigger web search if they're about timeless facts
# ═══════════════════════════════════════════════════════════════════

KNOWLEDGE_PATTERNS = [
    # Definitions and explanations
    (r"(?i)\b(what\s+is|what\s+are|define|definition\s+of|meaning\s+of|explain|explained)\b", 0.90),
    (r"(?i)\b(tell\s+me\s+about|describe|overview\s+of|describe)\b", 0.82),

    # How does X work (static, not "how to do X")
    (r"(?i)\b(how\s+(does|do|did))\b(?!.{0,30}\b(now|today|current|latest|price|cost|rate|stock|weather|score)\b)", 0.80),

    # Why questions
    (r"(?i)\b(why\s+(is|does|do|are|did|was|were|has|have|can|could|should|would))\b", 0.78),

    # History / origins / inventions
    (r"(?i)\b(history\s+of|origin\s+of|who\s+invented|when\s+was\s+.+\s+invented|who\s+discovered|who\s+founded|who\s+created)\b", 0.91),
    (r"(?i)\b(inventor\s+of|founder\s+of|creator\s+of|father\s+of)\b", 0.89),

    # Translations / synonyms / language
    (r"(?i)\b(translate|translation|synonym|antonym|opposite\s+of|word\s+for)\b", 0.89),
    (r"(?i)\b(how\s+(do\s+you\s+)?say)\b.{0,20}\b(in\s+spanish|in\s+french|in\s+german|in\s+hindi|in\s+japanese|in\s+chinese|in\s+korean)\b", 0.90),

    # Formulas (reference, not calculation)
    (r"(?i)\b(formula\s+for|equation\s+for|law\s+of|theorem|principle\s+of|theory\s+of)\b", 0.85),

    # Science / academic knowledge
    (r"(?i)\b(what\s+causes|what\s+is\s+the\s+cause)\b", 0.82),
    (r"(?i)\b(theory\s+of|concept\s+of|principles?\s+of)\b", 0.80),

    # "Who is" / "Who was" (biographical, not current role)
    (r"(?i)\b(who\s+(is|are|was|were))\b(?!.{0,30}\b(now|currently|today|ceo|president|owner|prime\s+minister|governor|senator)\b)", 0.75),

    # "Difference between" (static knowledge)
    (r"(?i)\b(difference\s+between)\b(?!.{0,30}\b(price|cost|rate|stock|latest|today)\b)", 0.78),

    # General knowledge queries
    (r"(?i)\b(types\s+of|kinds\s+of|examples\s+of|list\s+of)\b(?!.{0,30}\b(price|cost|rate|stock|latest|today|current)\b)", 0.77),
    (r"(?i)\b(how\s+many)\b(?!.{0,30}\b(price|cost|rate|stock|latest|today|current|now)\b)", 0.70),
    (r"(?i)\b(how\s+big|how\s+large|how\s+long|how\s+far|how\s+old|how\s+tall|how\s+deep|how\s+wide|how\s+much\s+does)\b(?!.{0,30}\b(cost|price|rate|stock|today|current)\b)", 0.75),
]


# ═══════════════════════════════════════════════════════════════════
# WEB PATTERNS — checked LAST (lowest priority, catch-all for live data)
# These all indicate a need for CURRENT / LIVE / REAL-TIME data
# ═══════════════════════════════════════════════════════════════════

WEB_PATTERNS = [
    # ─── Scraping / extraction (always needs browser) ───
    (r"(?i)\b(scrape|scraping|crawl|crawling|extract|extraction)\b.{0,20}\b(data|product|price|content|email|image|link|info|listing)\b", 0.92),
    (r"(?i)\b(data|product|price|content|email)\b.{0,20}\b(scrape|scraping|crawl|crawling|extract|extraction|harvest)\b", 0.92),
    (r"(?i)\b(web\s*scrape|screen\s*scrape|data\s*mine|content\s*extract|page\s*extract)\b", 0.91),

    # ─── Form filling (needs browser interaction) ───
    (r"(?i)\b(fill|complete|submit)\b.{0,15}\b(form|field|input|application|survey|questionnaire|checkout)\b", 0.88),
    (r"(?i)\b(form|checkout|application|registration)\b.{0,15}\b(fill|complete|submit|auto\s*fill)\b", 0.87),

    # ─── Breaking / urgent / live ───
    (r"(?i)\b(breaking|developing|urgent|just\s+in|alert|outage)\b", 0.96),
    (r"(?i)\b(live|real.?time|realtime)\b(?!.{0,20}\b(code|program|implement|stream)\b)", 0.92),
    (r"(?i)\b(current\s+events)\b", 0.91),

    # ─── Time-anchored queries ───
    (r"(?i)\b(latest|recent|current|today|now|tonight)\b.{0,25}\b(news|updates?|prices?|weather|stocks?|scores?|results?|releases?|version|report|status|data|info|information)\b", 0.95),
    (r"(?i)\b(news|updates?|prices?|weather|stocks?|scores?|results?|releases?|version)\b.{0,25}\b(latest|recent|current|today|now|tonight)\b", 0.94),
    (r"(?i)\b(what\s+happened)\b.{0,15}\b(today|this\s+week|recently|lately|now|yesterday)\b", 0.93),
    (r"(?i)\b(recent)\b.{0,25}\b(releases?|news|update|development|event|outage|changes)\b", 0.90),
    (r"(?i)\b(this\s+(week|month|year))\b.{0,20}\b(news|update|release|event|report|data)\b", 0.89),

    # ─── Sports scores / live ───
    (r"(?i)\b(nba|nfl|mlb|nhl|fifa|ipl)\b.{0,20}\b(scores?|standings|results?|game|match|playoffs?|highlights?|bracket)\b", 0.95),
    (r"(?i)\b(scores?|standings|results?)\b.{0,20}\b(nba|nfl|mlb|nhl|fifa|ipl)\b", 0.94),
    (r"(?i)\b(cricket|tennis|football|basketball|baseball|hockey|soccer|rugby|golf)\b.{0,20}\b(scores?|match|game|results?|live|standings|highlights?|rankings?)\b", 0.91),
    (r"(?i)\b(premier|nba|nfl|league|series|tournament)\b.{0,20}\b(standings|scores?|results?|table|rankings?|bracket|fixtures?)\b", 0.90),
    (r"(?i)\b(game|match|tournament)\b.{0,20}\b(scores?|standings|results?|highlights?|live|tonight|today)\b", 0.89),

    # ─── Financial / market ───
    (r"(?i)\b(stock\s+price|exchange\s+rate|market\s+(cap|price|value))\b", 0.94),
    (r"(?i)\b(bitcoin|ethereum|crypto|btc|eth)\b.{0,20}\b(price|value|market|trading|portfolio|chart)\b", 0.93),
    (r"(?i)\b(stock|market|trading|portfolio|share)\b.{0,15}\b(price|value|cap|today|current|latest|update)\b", 0.91),
    (r"(?i)\b(nasdaq|dow\s+jones|s&p\s*500|nifty|sensex|ftse|nikkei|dax|cac)\b", 0.90),

    # ─── Weather ───
    (r"(?i)\b(weather|temperature|forecast|rain|snow|humidity|wind)\b.{0,15}\b(today|now|current|tomorrow|this\s+week|tonight|weekend)\b", 0.94),
    (r"(?i)\b(will\s+it\s+rain|is\s+it\s+raining|how\s+(hot|cold|warm)\s+is)\b", 0.90),

    # ─── Prices / shopping (live data) ───
    (r"(?i)\b(how\s+much\s+(does|is|do))\b.{0,20}\b(cost|price|sell)\b", 0.88),
    (r"(?i)\b(price|cost)\b.{0,20}\b(of|for|compare|check|vs)\b", 0.85),
    (r"(?i)\b(compare|comparison|vs|versus)\b.{0,30}\b(price|cost|rate|plan|model|spec|feature)\b", 0.85),
    # Generic product comparison (e.g., "compare iPhone vs Samsung")
    (r"(?i)\b(compare|comparison)\b.{0,30}\b(vs|versus|and|or)\b", 0.84),
    # X vs Y pattern (direct comparison of two things)
    (r"(?i)\b\w+\s+(vs|versus)\s+\w+\b", 0.83),
    (r"(?i)\b(discount|deal|offer|sale|coupon|promo|clearance|coupon)\b", 0.84),
    (r"(?i)\b(buy|order|purchase|cheap|best\s+price|lowest\s+price)\b", 0.82),
    (r"(?i)\b(near\s+me|nearby|closest|around\s+me)\b", 0.91),

    # ─── News / media ───
    (r"(?i)\b(news|headline|report|journalist|press\s+release)\b", 0.82),
    (r"(?i)\b(who\s+(is|are))\b.{0,20}\b(now|currently|today|ceo|president|owner|prime\s+minister|governor|senator|leader)\b", 0.88),
    (r"(?i)\b(what\s+(is|are))\b.{0,20}\b(new|latest|current|best|top|trending)\b", 0.83),

    # ─── Social media (always needs web) ───
    (r"(?i)\b(instagram|twitter|facebook|tiktok|linkedin|threads|snapchat|whatsapp|discord|telegram|weibo|wechat)\b", 0.93),
    (r"(?i)\b(x\.com|youtube\.com|reddit\.com)\b", 0.91),
    (r"(?i)\b(social\s+media)\b", 0.88),
    (r"(?i)\b(open|check|browse|visit|go\s+to)\b.{0,20}\b(instagram|twitter|facebook|tiktok|linkedin|youtube|reddit|snapchat)\b", 0.95),
    (r"(?i)\b(trending|viral|influencer|followers|hashtag|dm|post|retweet|reel|story|feed|timeline)\b", 0.86),

    # ─── Technology (version/release/install needs web) ───
    (r"(?i)\b(release|launch|version|update)\b.{0,25}\b(date|time|schedule|when|latest|changelog)\b", 0.88),
    (r"(?i)\b(date|time|when)\b.{0,25}\b(release|launch|version|update|announcement)\b", 0.87),
    (r"(?i)\b(2024|2025|2026)\b.{0,20}\b(release|launch|announce|update|conference|event)\b", 0.86),
    (r"(?i)\b(download|install|setup)\b.{0,20}\b(latest|version|new|python|node|rust|go|ruby|java)\b", 0.85),
    (r"(?i)\b(how\s+to\s+(install|setup|configure|deploy|use))\b", 0.80),
    (r"(?i)\b(tutorial|guide|walkthrough|example)\b(?!.{0,30}\b(code|program|function|implement|create|write|build)\b)", 0.76),
    (r"(?i)\b(documentation|docs|api\s+reference)\b", 0.76),

    # ─── AI/ML (rapidly evolving, usually needs web) ───
    (r"(?i)\b(ai|artificial\s+intelligence|machine\s+learning|deep\s+learning|llm|gpt|chatbot)\b.{0,20}\b(news|update|release|model|latest|research|paper|launch)\b", 0.90),
    (r"(?i)\b(neural\s+network|transformer|diffusion|openai|claude|gemini|mistral|llama)\b", 0.86),

    # ─── Health (treatment updates need web) ───
    (r"(?i)\b(health|medical|disease|symptom|treatment|doctor|medicine|diagnosis|hospital|pharma)\b.{0,20}\b(latest|update|news|current|new|recent|today|clinic|near)\b", 0.88),
    (r"(?i)\b(health|medical|disease|symptom|treatment|doctor|medicine)\b", 0.77),
    (r"(?i)\b(vaccine|vaccination|clinical|trial|patient)\b.{0,20}\b(latest|update|news|current|new|recent|progress|result)\b", 0.87),

    # ─── Jobs / travel / entertainment (time-sensitive) ───
    (r"(?i)\b(job|career|hiring|salary|position|employment|recruitment|freelance|resume|interview)\b", 0.80),
    (r"(?i)\b(job|career|hiring|salary|position|employment|recruitment)\b.{0,20}\b(opening|available|now|today|current|latest|remote)\b", 0.86),
    (r"(?i)\b(freelance|resume|interview|cover\s+letter|remote\s+work)\b", 0.80),
    (r"(?i)\b(travel|hotel|flight|vacation|booking|tourist|trip)\b.{0,20}\b(deal|price|book|cheap|best|available|now)\b", 0.87),
    (r"(?i)\b(travel|hotel|flight|vacation|booking|tourist|trip)\b", 0.78),
    (r"(?i)\b(movie|film|tv\s+show|series|netflix|spotify|streaming)\b.{0,20}\b(new|latest|release|top|best|recommend|watch|on)\b", 0.84),
    (r"(?i)\b(new|latest|recent)\b.{0,15}\b(movie|film|series|show|album|music|game)\b", 0.85),
    (r"(?i)\b(movie|film|series|show)\b.{0,10}\b(review|rating|trailer|cast|actor|director)\b", 0.83),

    # ─── Catch-all web triggers (lower confidence) ───
    (r"(?i)\b(find|search|look\s+up|google|lookup)\b", 0.82),
    (r"(?i)\b(where\s+(to|can|is))\b.{0,20}\b(buy|find|download|watch|read|get|book)\b", 0.84),
    (r"(?i)\b(best|top|recommended|popular)\b.{0,20}\b(2024|2025|2026|this\s+year|right\s+now)\b", 0.85),
    (r"(?i)\b(hours|open|closed|schedule)\b.{0,15}\b(today|now|sunday|monday|saturday|weekend)\b", 0.89),
]


# ═══════════════════════════════════════════════════════════════════
# ANTI-FALSE-POSITIVE GUARDS
# Patterns that OVERRIDE a web/calc/code classification and redirect
# ═══════════════════════════════════════════════════════════════════

# Queries that LOOK like calculations but actually need web data
CALC_WEB_OVERRIDE_PATTERNS = [
    (r"(?i)(stock|share|crypto|bitcoin|ethereum|price|market|portfolio)\b.{0,30}(calculate|compute|convert)\b", QueryCategory.NEEDS_WEB),
    (r"(?i)\b(calculate|compute)\b.{0,20}\b(stock|price|cost|rate|mortgage|loan|tax|salary|income|profit)\b", QueryCategory.NEEDS_WEB),
    (r"(?i)\bconvert\b.{0,20}\b(currency|usd|eur|gbp|inr|jpy|cny|aud|cad|chf)\b", QueryCategory.NEEDS_WEB),
    # BUT: compound interest / simple interest are MATH formulas, not live data
    # So we do NOT override compound/simple interest here — they stay as calculation
]

# Queries that LOOK like code but actually need web data
CODE_WEB_OVERRIDE_PATTERNS = [
    (r"(?i)\b(latest|new|recent|current|best)\b.{0,30}\b(library|framework|package|version|release|tool)\b", QueryCategory.NEEDS_WEB),
    (r"(?i)\b(install|setup|download|getting\s+started)\b.{0,20}\b(python|node|rust|go|java|ruby|docker|kubernetes)\b", QueryCategory.NEEDS_WEB),
]

# Queries that LOOK like calculation but are actually code requests
# "code a Fibonacci sequence in Python" — the "in Python" makes it unambiguously code
CALC_CODE_OVERRIDE_PATTERNS = [
    (r"(?i)\b(write|code|create|build|implement)\b.{0,40}\b(in\s+(python|javascript|java|cpp|c\+\+|rust|typescript|golang|go|ruby|c#|sql|node\.?js|php|swift|kotlin|scala))\b", QueryCategory.NEEDS_CODE),
]

# Queries that LOOK like calculation but are actually knowledge (reference formulas)
CALC_KNOWLEDGE_OVERRIDE_PATTERNS = [
    (r"(?i)\b(formula\s+for|equation\s+for)\b", QueryCategory.NEEDS_KNOWLEDGE),
]

# Queries that LOOK like knowledge but actually need web data
KNOWLEDGE_WEB_OVERRIDE_PATTERNS = [
    (r"(?i)\b(what\s+is|who\s+is)\b.{0,20}\b(prices?|cost|rate|stocks?|weather|scores?|latest|current|today|now)\b", QueryCategory.NEEDS_WEB),
    (r"(?i)\b(how\s+(does|do))\b.{0,30}\b(prices?|cost|rate|stocks?|weather|scores?|market)\b", QueryCategory.NEEDS_WEB),
]


# ═══════════════════════════════════════════════════════════════════
# CATEGORY → AGENT MAPPING
# ═══════════════════════════════════════════════════════════════════

CATEGORY_AGENTS = {
    QueryCategory.NEEDS_WEB: {
        "news": ["news_hound", "generalist"],
        "price": ["price_checker", "generalist"],
        "tech": ["tech_scanner", "deep_researcher"],
        "weather": ["generalist"],
        "sports": ["sports_analyst", "news_hound"],
        "social": ["social_media_tracker", "generalist"],
        "finance": ["finance_analyst", "news_hound"],
        "health": ["health_researcher", "deep_researcher"],
        "jobs": ["job_scout", "generalist"],
        "entertainment": ["entertainment_guide", "generalist"],
        "travel": ["travel_scout", "generalist"],
        "ai": ["ai_watcher", "tech_scanner"],
        "shopping": ["price_checker", "generalist"],
        "scraping": ["deep_researcher", "tech_scanner"],
        "forms": ["generalist", "tech_scanner"],
        "default": ["generalist", "deep_researcher"],
    },
    QueryCategory.NEEDS_SECURITY: {
        "captcha": ["tech_scanner", "generalist"],
        "cloudflare": ["tech_scanner", "generalist"],
        "stealth": ["tech_scanner", "generalist"],
        "forms": ["generalist", "tech_scanner"],
        "default": ["tech_scanner", "generalist"],
    },
    QueryCategory.NEEDS_KNOWLEDGE: ["generalist", "deep_researcher"],
    QueryCategory.NEEDS_CALCULATION: ["generalist"],
    QueryCategory.NEEDS_CODE: ["tech_scanner"],
}


class RuleBasedRouter:
    """Tier 1: Rule-based query classification using patterns and keywords.

    Priority order: calculation > code > knowledge > web
    Then applies anti-false-positive override guards.
    """

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile all regex patterns for performance."""
        self.compiled_security = [(re.compile(p), c) for p, c in SECURITY_PATTERNS]
        self.compiled_calculation = [(re.compile(p), c) for p, c in CALCULATION_PATTERNS]
        self.compiled_code = [(re.compile(p), c) for p, c in CODE_PATTERNS]
        self.compiled_knowledge = [(re.compile(p), c) for p, c in KNOWLEDGE_PATTERNS]
        self.compiled_web = [(re.compile(p), c) for p, c in WEB_PATTERNS]

        # Anti-false-positive override patterns
        self.compiled_calc_web_override = [(re.compile(p), cat) for p, cat in CALC_WEB_OVERRIDE_PATTERNS]
        self.compiled_calc_code_override = [(re.compile(p), cat) for p, cat in CALC_CODE_OVERRIDE_PATTERNS]
        self.compiled_calc_knowledge_override = [(re.compile(p), cat) for p, cat in CALC_KNOWLEDGE_OVERRIDE_PATTERNS]
        self.compiled_code_web_override = [(re.compile(p), cat) for p, cat in CODE_WEB_OVERRIDE_PATTERNS]
        self.compiled_knowledge_web_override = [(re.compile(p), cat) for p, cat in KNOWLEDGE_WEB_OVERRIDE_PATTERNS]

    def classify(self, query: str) -> QueryClassification:
        """Classify a query using rule-based pattern matching.

        Strategy:
        1. Check each category in priority order (calc → code → knowledge → web)
        2. Apply anti-false-positive override guards
        3. Return best match with agents and search queries
        """
        # Step 1: Find best match in priority order
        result = None

        # Check security FIRST (captcha/bypass/stealth must never go to calculation)
        sec_match = self._match_patterns(query, self.compiled_security, QueryCategory.NEEDS_SECURITY)
        if sec_match and sec_match.confidence >= self.confidence_threshold:
            result = sec_match

        # Check calculation second
        calc_match = None
        if result is None:
            calc_match = self._match_patterns(query, self.compiled_calculation, QueryCategory.NEEDS_CALCULATION)
            if calc_match and calc_match.confidence >= self.confidence_threshold:
                # Apply calc→code override guards ("code X in Python" is unambiguously code)
                for pattern, override_cat in self.compiled_calc_code_override:
                    if pattern.search(query):
                        calc_match = QueryClassification(
                            category=override_cat,
                            confidence=max(calc_match.confidence, 0.93),
                            reason=f"override:calc_to_code:{pattern.pattern[:40]}",
                            source="rule_based",
                        )
                        break
                else:
                    # Apply calc→knowledge override guards ("formula for X" is reference, not computation)
                    for pattern, override_cat in self.compiled_calc_knowledge_override:
                        if pattern.search(query):
                            calc_match = QueryClassification(
                                category=override_cat,
                                confidence=max(calc_match.confidence, 0.90),
                                reason=f"override:calc_to_knowledge:{pattern.pattern[:40]}",
                                source="rule_based",
                            )
                            break
                    else:
                        # Apply calc→web override guards
                        for pattern, override_cat in self.compiled_calc_web_override:
                            if pattern.search(query):
                                calc_match = QueryClassification(
                                    category=override_cat,
                                    confidence=max(calc_match.confidence, 0.88),
                                    reason=f"override:calc_to_web:{pattern.pattern[:40]}",
                                    source="rule_based",
                                )
                                break
                result = calc_match

        # Check code if no result yet
        if result is None:
            code_match = self._match_patterns(query, self.compiled_code, QueryCategory.NEEDS_CODE)
            if code_match and code_match.confidence >= self.confidence_threshold:
                # Apply code→web override guards
                for pattern, override_cat in self.compiled_code_web_override:
                    if pattern.search(query):
                        code_match = QueryClassification(
                            category=override_cat,
                            confidence=max(code_match.confidence, 0.86),
                            reason=f"override:code_to_web:{pattern.pattern[:40]}",
                            source="rule_based",
                        )
                        break
                result = code_match

        # Check knowledge if no result yet
        if result is None:
            know_match = self._match_patterns(query, self.compiled_knowledge, QueryCategory.NEEDS_KNOWLEDGE)
            if know_match and know_match.confidence >= self.confidence_threshold:
                # Apply knowledge→web override guards
                for pattern, override_cat in self.compiled_knowledge_web_override:
                    if pattern.search(query):
                        know_match = QueryClassification(
                            category=override_cat,
                            confidence=max(know_match.confidence, 0.87),
                            reason=f"override:knowledge_to_web:{pattern.pattern[:40]}",
                            source="rule_based",
                        )
                        break
                result = know_match

        # Check web if no result yet
        if result is None:
            web_match = self._match_patterns(query, self.compiled_web, QueryCategory.NEEDS_WEB)
            if web_match and web_match.confidence >= self.confidence_threshold:
                result = web_match

        # If still no match, return ambiguous with default agents
        if result is None:
            result = QueryClassification(
                category=QueryCategory.AMBIGUOUS,
                confidence=0.0,
                reason="no_pattern_matched",
                source="rule_based",
            )
            result.suggested_agents = ["generalist", "deep_researcher"]
            result.search_queries = [query]
            return result

        # Step 2: Attach agents and search queries
        result.suggested_agents = self._suggest_agents(query, result.category)
        result.search_queries = self._generate_search_queries(query, result.category)
        return result

    def _match_patterns(self, query: str, patterns: list[tuple], category: QueryCategory) -> Optional[QueryClassification]:
        """Match query against a list of compiled patterns."""
        best_confidence = 0.0
        best_reason = ""

        for pattern, confidence in patterns:
            if pattern.search(query):
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_reason = f"pattern_matched:{pattern.pattern[:50]}"

        if best_confidence > 0:
            return QueryClassification(
                category=category,
                confidence=best_confidence,
                reason=best_reason,
                source="rule_based",
            )
        return None

    def _suggest_agents(self, query: str, category: QueryCategory) -> list[str]:
        """Suggest which agent profiles to use based on query content."""
        if category not in CATEGORY_AGENTS or not CATEGORY_AGENTS[category]:
            return ["generalist"]

        agents_map = CATEGORY_AGENTS[category]
        query_lower = query.lower()

        if category == QueryCategory.NEEDS_SECURITY:
            if isinstance(agents_map, dict):
                if any(kw in query_lower for kw in ["captcha", "recaptcha", "hcaptcha", "turnstile", "challenge"]):
                    return agents_map.get("captcha", agents_map["default"])
                if any(kw in query_lower for kw in ["cloudflare", "perimeterx", "datadome", "akamai", "waf", "bot"]):
                    return agents_map.get("cloudflare", agents_map["default"])
                if any(kw in query_lower for kw in ["stealth", "undetect", "fingerprint", "headless", "webdriver"]):
                    return agents_map.get("stealth", agents_map["default"])
                if any(kw in query_lower for kw in ["fill", "form", "login", "credential"]):
                    return agents_map.get("forms", agents_map["default"])
                return agents_map["default"]
            return ["security_agent", "generalist"]

        if category == QueryCategory.NEEDS_WEB:
            # Social media platforms take priority over news/price
            social_platforms = ["instagram", "twitter", "facebook", "tiktok", "linkedin", "threads", "x.com", "youtube", "snapchat", "whatsapp", "discord", "telegram"]
            if any(platform in query_lower for platform in social_platforms):
                return agents_map.get("social", agents_map["default"])
            if any(kw in query_lower for kw in ["social media", "tweet", "viral", "trending", "influencer", "followers", "profile", "post", "dm", "hashtag", "reel", "story"]):
                return agents_map.get("social", agents_map["default"])
            if any(kw in query_lower for kw in ["stock", "market", "crypto", "bitcoin", "investment", "portfolio", "trading", "nasdaq", "dow jones", "share price", "dividend", "ipo", "exchange rate"]):
                return agents_map.get("finance", agents_map["default"])
            if any(kw in query_lower for kw in ["travel", "hotel", "flight", "vacation", "booking", "tourist", "attraction", "trip", "airbnb"]):
                return agents_map.get("travel", agents_map["default"])
            # Entertainment must come BEFORE tech — "Netflix new releases" etc.
            if any(kw in query_lower for kw in ["movie", "film", "tv show", "series", "music", "song", "album", "gaming", "actor", "celebrity", "streaming", "netflix", "spotify", "hulu", "disney", "amazon prime", "youtube", "new release", "release date", "watch"]):
                return agents_map.get("entertainment", agents_map["default"])
            if any(kw in query_lower for kw in ["scrape", "scraping", "crawl", "extract", "harvest", "data mine"]):
                return agents_map.get("scraping", agents_map["default"])
            if any(kw in query_lower for kw in ["fill", "form", "submit", "application", "checkout", "register"]):
                return agents_map.get("forms", agents_map["default"])
            if any(kw in query_lower for kw in ["price", "cost", "buy", "cheap", "discount", "deal", "shop", "order", "purchase", "compare", "vs", "versus"]):
                return agents_map.get("price", agents_map["default"])
            if any(kw in query_lower for kw in ["news", "update", "breaking", "headline"]):
                return agents_map.get("news", agents_map["default"])
            if any(kw in query_lower for kw in ["ai", "artificial intelligence", "machine learning", "deep learning", "neural network", "llm", "gpt", "transformer", "chatbot", "diffusion"]):
                return agents_map.get("ai", agents_map["default"])
            if any(kw in query_lower for kw in ["tech", "software", "programming", "api", "github", "code", "python", "javascript", "install", "tutorial", "documentation", "release", "version"]):
                return agents_map.get("tech", agents_map["default"])
            if any(kw in query_lower for kw in ["health", "medical", "disease", "symptom", "treatment", "doctor", "medicine", "diagnosis", "vaccine", "clinical", "patient"]):
                return agents_map.get("health", agents_map["default"])
            if any(kw in query_lower for kw in ["job", "career", "hiring", "salary", "position", "employment", "recruitment", "resume", "interview", "freelance"]):
                return agents_map.get("jobs", agents_map["default"])
            if any(kw in query_lower for kw in ["score", "game", "match", "sports", "nba", "nfl", "football", "cricket", "tennis", "fifa", "olympics"]):
                return agents_map.get("sports", agents_map["default"])
            if any(kw in query_lower for kw in ["weather", "temperature", "rain", "forecast"]):
                return agents_map.get("weather", agents_map["default"])
            return agents_map["default"]

        # For non-WEB categories, agents_map is a list
        if isinstance(agents_map, list):
            return agents_map
        return ["generalist"]

    def _generate_search_queries(self, query: str, category: QueryCategory) -> list[str]:
        """Generate optimized search queries for each agent."""
        if category == QueryCategory.NEEDS_CALCULATION:
            return [query, f"how to calculate {query}", f"{query} formula"]
        if category == QueryCategory.NEEDS_CODE:
            return [query, f"{query} code example tutorial", f"how to implement {query}"]
        if category == QueryCategory.NEEDS_KNOWLEDGE:
            return [query, f"{query} explained", f"{query} definition"]
        if category != QueryCategory.NEEDS_WEB:
            return [query]

        queries = [query]
        import datetime
        current_year = datetime.datetime.now().year
        if str(current_year) not in query and str(current_year - 1) not in query:
            queries.append(f"{query} {current_year}")

        query_lower = query.lower()
        if any(kw in query_lower for kw in ["news", "update", "release"]):
            if "latest" not in query_lower:
                queries.append(f"latest {query}")
        if any(kw in query_lower for kw in ["price", "cost", "buy"]):
            queries.append(f"{query} best price {current_year}")
        if any(kw in query_lower for kw in ["vs", "versus", "compare"]):
            queries.append(f"{query} comparison {current_year}")

        return queries
