"""
Agent-OS Web-Need Router — Lightweight Zero-Dependency Decision Engine

Decides whether an AI agent query needs web/browser access or can be answered
from the agent's own knowledge. Uses pure rule-based heuristics — no LLM calls,
no extra dependencies, sub-millisecond performance.

Usage:
    from src.agents.web_need_router import WebNeedRouter

    router = WebNeedRouter()
    result = router.route("What's the weather in Delhi right now?")
    # => {"needs_web": True, "action": "search", "confidence": 0.9, ...}

    result = router.route("What is 2 + 2?")
    # => {"needs_web": False, "action": "answer_from_knowledge", ...}

REST API:
    POST /route  {"query": "your question", "context": "optional"}
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger("agent-os.web_need_router")


# ─── Data Classes ──────────────────────────────────────────────

@dataclass
class RouteResult:
    """Result of routing decision."""
    needs_web: bool
    action: str            # "answer_from_knowledge" | "search" | "browse" | "hybrid"
    confidence: float      # 0.0 - 1.0
    reason: str
    suggested_commands: List[str] = field(default_factory=list)
    suggested_urls: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "needs_web": self.needs_web,
            "action": self.action,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "suggested_commands": self.suggested_commands,
            "suggested_urls": self.suggested_urls,
            "search_queries": self.search_queries,
        }


# ─── Signal Definitions ────────────────────────────────────────

# Patterns that strongly indicate BROWSER interaction is needed
# (login, fill forms, click, post, buy, etc.)
BROWSER_ACTION_PATTERNS = [
    # Social media actions
    r'\b(post|tweet|share|like|follow|unfollow|comment)\b.*\b(on|to|in)\b',
    r'\b(instagram|facebook|twitter|linkedin|reddit|tiktok|youtube)\b',
    # Form / auth actions
    r'\b(log\s*in|sign\s*in|login|signin)\b',
    r'\b(sign\s*up|register|create\s*account)\b',
    r'\b(fill|submit|upload|download|attach)\b.*\b(form|application|document)\b',
    # Transactional
    r'\b(book|buy|purchase|order|checkout|pay|cart|add\s*to\s*cart)\b',
    r'\b(reserve|schedule|appointment)\b',
    # Browser-specific interactions
    r'\b(click|press|select|check|uncheck|toggle)\b.*\b(button|link|tab|checkbox)\b',
    r'\b(navigate|go\s*to|open|visit|browse)\b.*\b(website|page|site|url|portal)\b',
    r'\b(screenshot|capture|snapshot)\b',
    r'\b(take\s+a?\s*screenshot)\b',
    # Web app specific
    r'\b(send|compose|write)\b.*\b(email|message|dm|direct\s*message)\b',
    r'\b(apply|submit)\b.*\b(job|application|form|coupon)\b',
    r'\b(search|find|look\s*for)\b.*\b(on|in|at)\b.*\b(website|site|platform|portal|app)\b',
    r'\b(dashboard|portal|console|admin|panel)\b',
    # Credential management
    r'\b(save\s*(creds|credentials|password|login))\b',
    r'\b(auto[\-\s]?login)\b',
    # Scanning / security
    r'\b(scan)\b.*\b(vulnerability|xss|sqli|security)\b',
    r'\b(scan)\b.*\b(for)\b.*\b(xss|sqli|sensitive)\b',
]

# Patterns that indicate LIVE / REAL-TIME data is needed
# (current prices, news, weather, etc.)
LIVE_DATA_PATTERNS = [
    # Time-sensitive keywords
    r'\b(latest|current|today|now|recent|right\s*now|real[\-\s]?time)\b',
    r'\b(this\s+(week|month|year|quarter|hour|minute))\b',
    r'\b(2025|2026|2027)\b',  # Recent years often indicate current info need
    # Financial / market data
    r'\b(price|stock|share|market|crypto|bitcoin|ethereum|btc|eth)\b',
    r'\b(exchange\s*rate|forex|currency|dollar|rupee|euro)\b',
    r'\b(nifty|sensex|dow|nasdaq|s&p|sp\s*500)\b',
    # News / current events
    r'\b(news|headline|breaking|update|announcement)\b',
    r'\b(trending|viral|popular)\b',
    # Weather / live conditions
    r'\b(weather|temperature|forecast|rain|snow|storm)\b',
    # Scores / live events
    r'\b(score|live\s*match|game\s*today|result)\b',
    r'\b(ipl|world\s*cup|olympics|tournament)\b',
    # Flight / travel live info
    r'\b(flight|train|bus)\b.*\b(status|schedule|delay|timing|fare|availability)\b',
    r'\b(pnr|seat\s*availability|booking\s*status)\b',
    # Live data sources
    r'\b(live|real[\-\s]?time|streaming|feed)\b',
]

# Patterns that indicate KNOWLEDGE-BASED answers (no web needed)
KNOWLEDGE_PATTERNS = [
    # Factual / definitional
    r'\b(what\s+is|define|definition\s+of|meaning\s+of)\b',
    r'\b(who\s+(is|was|are|were|invented|discovered))\b',
    r'\b(when\s+(was|did|were))\b.*\b(invented|discovered|born|created|founded)\b',
    # Explanations
    r'\b(how\s+to|explain|describe|tell\s+me\s+about)\b',
    r'\b(difference\s+between|compare)\b',
    # Math / logic
    r'\b(calculate|compute|solve|math|equation|formula)\b',
    r'\b(\d+\s*[\+\-\*\/\^]\s*\d+)\b',  # arithmetic expressions
    # Programming
    r'\b(how\s+to\s+(write|code|implement|create|build))\b.*\b(in|using|with|python|javascript|java|c\+\+|rust|go)\b',
    r'\b(syntax|function|method|class|api|library|module|package)\b',
    r'\b(error|bug|exception|debug|fix)\b.*\b(code|program|script)\b',
    r'\b(regex|regular\s+expression)\b',
    # General knowledge (historical, scientific)
    r'\b(history\s+of|origin\s+of|story\s+of|background\s+of)\b',
    r'\b(types\s+of|kinds\s+of|categories\s+of)\b',
    r'\b(example\s+of|sample|illustration)\b',
    # Creative / subjective
    r'\b(write|compose|draft|create)\b.*\b(poem|story|essay|letter|email|article)\b',
    r'\b(suggest|recommend|advise|opinion)\b',
    # Language / translation
    r'\b(translate|meaning\s+in|how\s+to\s+say)\b',
]

# Domains that almost always need a real browser (JS-heavy, auth-required, anti-bot)
BROWSER_REQUIRED_DOMAINS = {
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "m.facebook.com",
    "twitter.com", "x.com", "www.twitter.com",
    "linkedin.com", "www.linkedin.com",
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "tiktok.com", "www.tiktok.com",
    "netflix.com", "www.netflix.com",
    "glassdoor.com", "www.glassdoor.com",
    "bloomberg.com", "www.bloomberg.com",
    "wsj.com", "www.wsj.com",
    "nytimes.com", "www.nytimes.com",
    "amazon.com", "www.amazon.com", "amazon.in", "www.amazon.in",
    "flipkart.com", "www.flipkart.com",
    "zomato.com", "www.zomato.com",
    "swiggy.com", "www.swiggy.com",
    "booking.com", "www.booking.com",
    "airbnb.com", "www.airbnb.com",
    "uber.com", "www.uber.com",
    "ola.com", "www.ola.com",
}

# Domains where HTTP fetch is usually enough (static content, docs)
FETCH_SUFFICIENT_DOMAINS = {
    "wikipedia.org", "www.wikipedia.org",
    "docs.python.org", "docs.oracle.com",
    "developer.mozilla.org",
    "stackoverflow.com", "www.stackoverflow.com",
    "github.com", "www.github.com",
    "medium.com", "www.medium.com",
    "arxiv.org",
    "nature.com", "www.nature.com",
    "ieee.org", "www.ieee.org",
    "pypi.org",
    "npmjs.com", "www.npmjs.com",
    "readthedocs.io",
    "w3schools.com", "www.w3schools.com",
    "geeksforgeeks.org", "www.geeksforgeeks.org",
    "w3schools.com",
}


# ─── Router Class ──────────────────────────────────────────────

class WebNeedRouter:
    """
    Lightweight rule-based router that decides if a query needs web access.

    Zero dependencies. Sub-millisecond performance. Extensible via custom rules.

    Decision Pipeline:
        1. URL Detection — if URL present, decide fetch vs browse
        2. Browser Action Signals — strong signals for full browser
        3. Live Data Signals — signals for search/fetch
        4. Knowledge Signals — signals for no-web-needed
        5. Score Combination — weighted decision
        6. Confidence Assessment — how sure are we?
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Weights for different signal types (tuneable)
        self.weight_browser = self.config.get("router.weight_browser", 3.0)
        self.weight_live = self.config.get("router.weight_live", 2.0)
        self.weight_knowledge = self.config.get("router.weight_knowledge", 1.5)

        # Confidence thresholds
        self.threshold_high = self.config.get("router.confidence_high", 0.75)
        self.threshold_low = self.config.get("router.confidence_low", 0.35)

        # Pre-compile regex patterns for performance
        self._browser_patterns = [re.compile(p, re.IGNORECASE) for p in BROWSER_ACTION_PATTERNS]
        self._live_patterns = [re.compile(p, re.IGNORECASE) for p in LIVE_DATA_PATTERNS]
        self._knowledge_patterns = [re.compile(p, re.IGNORECASE) for p in KNOWLEDGE_PATTERNS]
        self._url_pattern = re.compile(
            r'https?://[^\s<>"\']+', re.IGNORECASE
        )
        self._domain_pattern = re.compile(
            r'(?:https?://)?(?:www\.)?([a-z0-9\-]+\.[a-z]{2,}(?:\.[a-z]{2,})?)',
            re.IGNORECASE
        )

        # Custom rules (extensible)
        self._custom_browser_rules: List[Dict] = []
        self._custom_live_rules: List[Dict] = []
        self._custom_knowledge_rules: List[Dict] = []

        # Stats tracking
        self._stats = {
            "total_routed": 0,
            "browse_count": 0,
            "search_count": 0,
            "knowledge_count": 0,
            "hybrid_count": 0,
            "avg_confidence": 0.0,
        }

        logger.info("WebNeedRouter initialized (rule-based, zero-dependency)")

    def add_browser_rule(self, pattern: str, reason: str, weight: float = 1.0):
        """Add a custom browser-action detection rule."""
        self._custom_browser_rules.append({
            "pattern": re.compile(pattern, re.IGNORECASE),
            "reason": reason,
            "weight": weight,
        })

    def add_live_data_rule(self, pattern: str, reason: str, weight: float = 1.0):
        """Add a custom live-data detection rule."""
        self._custom_live_rules.append({
            "pattern": re.compile(pattern, re.IGNORECASE),
            "reason": reason,
            "weight": weight,
        })

    def add_knowledge_rule(self, pattern: str, reason: str, weight: float = 1.0):
        """Add a custom knowledge-based detection rule."""
        self._custom_knowledge_rules.append({
            "pattern": re.compile(pattern, re.IGNORECASE),
            "reason": reason,
            "weight": weight,
        })

    def route(self, query: str, context: Optional[str] = None) -> RouteResult:
        """
        Main routing method. Analyzes query and returns routing decision.

        Args:
            query: The user's question or task description
            context: Optional conversation context for better decisions

        Returns:
            RouteResult with decision, confidence, and suggestions
        """
        start_time = time.time()
        query = query.strip()
        full_text = f"{query} {context}".strip() if context else query

        # Step 1: URL Detection — if URL is present, decide fetch vs browse
        urls_found = self._url_pattern.findall(full_text)
        if urls_found:
            result = self._route_with_url(query, urls_found, full_text)
            self._update_stats(result, time.time() - start_time)
            return result

        # Step 2: Score each signal type
        browser_score, browser_reasons = self._score_signals(
            full_text, self._browser_patterns, self._custom_browser_rules, self.weight_browser
        )
        live_score, live_reasons = self._score_signals(
            full_text, self._live_patterns, self._custom_live_rules, self.weight_live
        )
        knowledge_score, knowledge_reasons = self._score_signals(
            full_text, self._knowledge_patterns, self._custom_knowledge_rules, self.weight_knowledge
        )

        # Step 3: Domain hint scoring
        domain_browser, domain_fetch = self._check_domains(full_text)
        browser_score += domain_browser * self.weight_browser
        live_score += domain_fetch * self.weight_live

        # Step 4: Determine action
        result = self._make_decision(
            query, browser_score, live_score, knowledge_score,
            browser_reasons, live_reasons, knowledge_reasons,
        )

        self._update_stats(result, time.time() - start_time)
        return result

    def _route_with_url(self, query: str, urls: List[str], full_text: str) -> RouteResult:
        """Route when URL(s) are detected in the query."""
        # Check if any URL requires full browser
        needs_browser_url = False
        fetch_ok_urls = []
        browse_urls = []

        for url in urls:
            domain = self._extract_domain(url)
            if domain in BROWSER_REQUIRED_DOMAINS:
                needs_browser_url = True
                browse_urls.append(url)
            elif domain in FETCH_SUFFICIENT_DOMAINS:
                fetch_ok_urls.append(url)
            else:
                # Unknown domain — check if query has interaction intent
                browse_urls.append(url)

        # If query has action intent alongside URL, use browser
        action_intent = any(
            p.search(full_text) for p in self._browser_patterns
        )

        if needs_browser_url or action_intent:
            return RouteResult(
                needs_web=True,
                action="browse",
                confidence=0.92,
                reason=f"URL requires browser interaction: {', '.join(browse_urls[:3])}",
                suggested_commands=["navigate", "smart-navigate"],
                suggested_urls=browse_urls,
                search_queries=[],
            )
        elif fetch_ok_urls and not browse_urls:
            return RouteResult(
                needs_web=True,
                action="search",
                confidence=0.85,
                reason=f"URL can be fetched via HTTP: {', '.join(fetch_ok_urls[:3])}",
                suggested_commands=["fetch", "smart-navigate"],
                suggested_urls=fetch_ok_urls,
                search_queries=[],
            )
        else:
            # Mixed or unknown — use smart-navigate (auto-selects strategy)
            return RouteResult(
                needs_web=True,
                action="browse",
                confidence=0.7,
                reason="URL detected — using browser for reliable access",
                suggested_commands=["smart-navigate"],
                suggested_urls=urls[:3],
                search_queries=[],
            )

    def _score_signals(
        self, text: str, patterns: List[re.Pattern],
        custom_rules: List[Dict], weight: float
    ) -> tuple:
        """Score text against pattern list and return (score, matched_reasons)."""
        score = 0.0
        reasons = []

        for pattern in patterns:
            matches = pattern.findall(text)
            if matches:
                score += len(matches) * weight
                reasons.append(pattern.pattern[:60])

        for rule in custom_rules:
            matches = rule["pattern"].findall(text)
            if matches:
                score += len(matches) * rule["weight"] * weight
                reasons.append(rule["reason"][:60])

        return score, reasons

    def _check_domains(self, text: str) -> tuple:
        """Check for domain mentions that hint at browse vs fetch."""
        browser_hint = 0.0
        fetch_hint = 0.0

        domains = self._domain_pattern.findall(text)
        for domain in domains:
            domain_lower = domain.lower()
            if domain_lower in BROWSER_REQUIRED_DOMAINS:
                browser_hint += 1.0
            elif domain_lower in FETCH_SUFFICIENT_DOMAINS:
                fetch_hint += 0.5

        return browser_hint, fetch_hint

    def _make_decision(
        self, query: str,
        browser_score: float, live_score: float, knowledge_score: float,
        browser_reasons: List[str], live_reasons: List[str], knowledge_reasons: List[str],
    ) -> RouteResult:
        """Make final routing decision based on signal scores."""

        max_score = max(browser_score, live_score, knowledge_score, 0.01)

        # Strong browser signals always win
        if browser_score >= 2.0 and browser_score > live_score:
            confidence = min(browser_score / (browser_score + 1.0), 0.95)
            search_queries = self._extract_search_queries(query, "browse")
            return RouteResult(
                needs_web=True,
                action="browse",
                confidence=confidence,
                reason=f"Browser interaction needed: {', '.join(browser_reasons[:3]) or 'action keywords detected'}",
                suggested_commands=["navigate", "smart-navigate", "click", "fill-form"],
                suggested_urls=[],
                search_queries=search_queries,
            )

        # Live data signals need web but not necessarily browser
        if live_score >= 2.0 and live_score > knowledge_score:
            confidence = min(live_score / (live_score + 1.0), 0.92)
            search_queries = self._extract_search_queries(query, "search")
            return RouteResult(
                needs_web=True,
                action="search",
                confidence=confidence,
                reason=f"Live/current data needed: {', '.join(live_reasons[:3]) or 'time-sensitive keywords detected'}",
                suggested_commands=["smart-navigate", "fetch"],
                suggested_urls=[],
                search_queries=search_queries,
            )

        # Knowledge signals suggest no web needed
        if knowledge_score >= 2.0 and knowledge_score > live_score and knowledge_score > browser_score:
            confidence = min(knowledge_score / (knowledge_score + 1.0), 0.9)
            return RouteResult(
                needs_web=False,
                action="answer_from_knowledge",
                confidence=confidence,
                reason=f"General knowledge question: {', '.join(knowledge_reasons[:3]) or 'factual query detected'}",
                suggested_commands=[],
                suggested_urls=[],
                search_queries=[],
            )

        # Mixed signals — hybrid approach
        if browser_score > 0 and live_score > 0:
            search_queries = self._extract_search_queries(query, "hybrid")
            confidence = min((browser_score + live_score) / (browser_score + live_score + 2.0), 0.8)
            return RouteResult(
                needs_web=True,
                action="hybrid",
                confidence=confidence,
                reason="Mixed signals: may need web verification for part of the answer",
                suggested_commands=["smart-navigate", "fetch"],
                suggested_urls=[],
                search_queries=search_queries,
            )

        # Low signal across the board — lean towards knowledge
        if max_score < 1.0:
            return RouteResult(
                needs_web=False,
                action="answer_from_knowledge",
                confidence=0.5,
                reason="No strong web signals detected — try answering from knowledge first",
                suggested_commands=[],
                suggested_urls=[],
                search_queries=[],
            )

        # Default: moderate signals, suggest search as safe fallback
        if live_score > 0:
            search_queries = self._extract_search_queries(query, "search")
            return RouteResult(
                needs_web=True,
                action="search",
                confidence=0.55,
                reason="Some live-data signals present — web search recommended",
                suggested_commands=["smart-navigate", "fetch"],
                suggested_urls=[],
                search_queries=search_queries,
            )

        return RouteResult(
            needs_web=False,
            action="answer_from_knowledge",
            confidence=0.55,
            reason="No strong web signals — answer from knowledge",
            suggested_commands=[],
            suggested_urls=[],
            search_queries=[],
        )

    def _extract_search_queries(self, query: str, action: str) -> List[str]:
        """Generate suggested search queries from the user's query."""
        queries = [query]

        # Extract key terms for a focused search
        # Remove common filler words
        filler_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "need", "dare", "ought", "used", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between",
            "out", "off", "over", "under", "again", "further", "then",
            "once", "here", "there", "when", "where", "why", "how",
            "all", "each", "every", "both", "few", "more", "most",
            "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just",
            "because", "but", "and", "or", "if", "while", "about",
            "up", "its", "it", "this", "that", "these", "those",
            "me", "my", "we", "our", "you", "your", "he", "she",
            "they", "them", "what", "which", "who", "whom",
            "kya", "hai", "ko", "se", "ke", "ka", "ki", "mein",
            "par", "bhi", "toh", "ho", "kar", "karna", "karo",
        }

        words = re.findall(r'\b\w+\b', query.lower())
        key_words = [w for w in words if w not in filler_words and len(w) > 2]

        if len(key_words) >= 3:
            focused = " ".join(key_words[:8])
            if focused != query.lower():
                queries.append(focused)

        return queries[:3]  # Max 3 search queries

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        match = self._domain_pattern.search(url)
        return match.group(1).lower() if match else ""

    def _update_stats(self, result: RouteResult, elapsed: float):
        """Update routing statistics."""
        self._stats["total_routed"] += 1
        self._stats[f"{result.action}_count"] = self._stats.get(
            f"{result.action}_count", 0
        ) + 1

        # Running average confidence
        n = self._stats["total_routed"]
        old_avg = self._stats["avg_confidence"]
        self._stats["avg_confidence"] = round(
            old_avg + (result.confidence - old_avg) / n, 3
        )

        if elapsed > 0.01:  # Log slow routing (>10ms)
            logger.warning(f"Slow routing decision: {elapsed*1000:.1f}ms for query")

    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return {
            **self._stats,
            "browser_rules": len(BROWSER_ACTION_PATTERNS) + len(self._custom_browser_rules),
            "live_data_rules": len(LIVE_DATA_PATTERNS) + len(self._custom_live_rules),
            "knowledge_rules": len(KNOWLEDGE_PATTERNS) + len(self._custom_knowledge_rules),
            "browser_domains": len(BROWSER_REQUIRED_DOMAINS),
            "fetch_domains": len(FETCH_SUFFICIENT_DOMAINS),
        }


# ─── Self-Ask System Prompt ────────────────────────────────────

SELF_ASK_PROMPT = """Before using any browser tool, ask yourself these questions:

1. KNOWLEDGE CHECK: Can I answer this from my training data confidently?
   - If YES → Answer directly, no browser needed.
   - If UNSURE → Consider web verification.

2. FRESHNESS CHECK: Is this information likely to have changed recently?
   - Stock prices, news, weather → Always needs web.
   - Historical facts, definitions, math → No web needed.

3. INTERACTION CHECK: Does this require clicking, filling, logging in, or posting?
   - Social media, forms, dashboards → Full browser needed.
   - Just reading an article → HTTP fetch may suffice.

4. EFFICIENCY CHECK: What's the lightest tool that can get the job done?
   - browser_fetch (HTTP) → Fastest, for static content.
   - browser_smart_navigate → Auto-selects best strategy.
   - browser_navigate → Full browser, for JS-heavy/auth pages.

5. SCOPE CHECK: What specific information am I looking for?
   - Define your search query BEFORE opening the browser.
   - Know when to stop browsing (set success criteria).

Remember: Browser operations are expensive. Use them only when necessary.
When in doubt, try browser_fetch or browser_smart_navigate first.
"""

# Quick-reference prompt for agents
QUICK_ROUTING_GUIDE = """
Web Access Decision Guide (use before browser tools):
- Factual/math/definitions → No browser needed
- Code/programming help → No browser needed (unless checking docs)
- Current news/prices/weather → Use browser_fetch or smart_navigate
- Login/post/buy/book → Use browser_navigate + interaction tools
- Instagram/Facebook/Twitter → Always needs browser_navigate
- Wikipedia/StackOverflow → browser_fetch usually sufficient
- Unknown site → Use browser_smart_navigate (auto-selects)
"""


# ─── Convenience Function ──────────────────────────────────────

_default_router: Optional[WebNeedRouter] = None


def route_query(query: str, context: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick routing function using a module-level default router.
    Thread-safe for read-only usage.
    """
    global _default_router
    if _default_router is None:
        _default_router = WebNeedRouter()
    return _default_router.route(query, context).to_dict()


def get_routing_stats() -> Dict[str, Any]:
    """Get stats from the default router."""
    global _default_router
    if _default_router is None:
        _default_router = WebNeedRouter()
    return _default_router.get_stats()
