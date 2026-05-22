"""
Agent-OS Web Query Router
=========================
Rule-based classification engine that determines whether a query requires
web/browser access or can be answered from existing knowledge — WITHOUT
using any LLM.

This is critical for AI agents: if they don't know WHEN to use the browser,
the tool is useless. This router tells them.

Usage::

    from src.tools.web_query_router import WebQueryRouter

    router = WebQueryRouter()
    result = router.classify("What's the weather in Delhi?")
    # → {"needs_web": True, "confidence": 0.95, "reason": "...", "category": "real_time_data"}

    result = router.classify("What is 2 + 2?")
    # → {"needs_web": False, "confidence": 0.97, "reason": "...", "category": "math"}

    result = router.classify("Tell me about Python")
    # → {"needs_web": False, "confidence": 0.6, "reason": "...", "category": "general_knowledge"}
"""
import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("agent-os.web_query_router")


# ═══════════════════════════════════════════════════════════════════
# Signal Definitions — Each signal contributes a score
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """A single classification signal with weight and description."""
    pattern: str                     # Regex pattern to match
    weight: float                    # Positive = web, Negative = no-web
    category: str                    # Category name
    reason: str                      # Human-readable reason
    flags: int = re.IGNORECASE       # Regex flags


# ── STRONG WEB SIGNALS (high confidence that browser is needed) ──

STRONG_WEB_SIGNALS: List[Signal] = [
    # URL patterns — almost certainly need browser
    Signal(r"https?://\S+", 3.0, "url", "Query contains a URL — browser needed to access it"),
    Signal(r"www\.\S+", 2.5, "url", "Query contains a www URL"),
    Signal(r"\b(go to|open|visit|navigate to|browse)\s+(https?://|www\.)?\S+", 2.8, "url",
           "Direct navigation command"),

    # Real-time / temporal keywords
    Signal(r"\b(today|right now|currently|this morning|this evening|tonight|just now)\b", 2.5,
           "real_time_data", "Query refers to current time — data changes frequently"),
    Signal(r"\b(latest|recent|breaking|just released|newest|updated|up-to-date)\b", 2.2,
           "real_time_data", "Query asks for latest/recent information"),
    Signal(r"\b(live|real-?time|streaming|ongoing|happening now)\b", 2.5,
           "real_time_data", "Query asks for live/real-time data"),
    Signal(r"\b(this week|this month|this year|this quarter)\b", 2.0,
           "real_time_data", "Query refers to current time period"),

    # Web-specific actions
    Signal(r"\b(search (?:for|on|the web|google|online)|google|look up|look online|find online)\b", 2.8,
           "web_search", "Query explicitly asks to search the web"),
    Signal(r"\b(browse|surf|check (?:online|the web|the internet|website))\b", 2.5,
           "web_search", "Query explicitly asks to browse the web"),
    Signal(r"\b(scrape|crawl|extract (?:from|data)|parse (?:the |web )?page)\b", 2.5,
           "web_scraping", "Query asks to scrape/extract web data"),
    Signal(r"\b(screenshot|snapshot|capture (?:the |a |web )?page)\b", 2.3,
           "web_action", "Query asks for a browser action (screenshot)"),
    Signal(r"\b(fill (?:out|in|the)|submit|click|login|sign in|log in)\b", 2.0,
           "web_action", "Query asks for a browser interaction"),

    # Real-time data categories
    Signal(r"\b(weather|temperature|forecast|rain|snow|humid)\b", 2.5,
           "real_time_data", "Weather data is real-time and location-specific"),
    Signal(r"\b(stock (?:price|market|exchange)|share price|nifty|sensex|dow jones|nasdaq|s&p)\b", 2.5,
           "real_time_data", "Stock prices are real-time data"),
    Signal(r"\b(cryptocurrency|bitcoin|btc|ethereum|eth|crypto price|dogecoin)\b", 2.5,
           "real_time_data", "Crypto prices are real-time data"),
    Signal(r"\b(news|headline|breaking news|current events|top stories)\b", 2.3,
           "real_time_data", "News is real-time information"),
    Signal(r"\b(score|match result|game result|won|lost|tournament|ipl|world cup|olympics)\b", 2.2,
           "real_time_data", "Sports scores are real-time data"),
    Signal(r"\b(price of|cost of|how much (?:does|is)|cheapest|best deal|discount|offer)\b", 2.0,
           "real_time_data", "Prices change frequently"),
    Signal(r"\b(flight|train|bus|movie (?:showtime|ticket)|booking|availability|seat)\b", 2.2,
           "real_time_data", "Booking/availability data is real-time"),
    Signal(r"\b(traffic|road condition|transit|delay|closure)\b", 2.0,
           "real_time_data", "Traffic data is real-time"),
    Signal(r"\b(covid|cases|vaccination|pandemic)\b", 2.0,
           "real_time_data", "Health statistics are time-sensitive"),
    Signal(r"\b(election|poll|vote|result|ballot)\b", 2.2,
           "real_time_data", "Election results are time-sensitive"),
    Signal(r"\b(exchange rate|currency|forex|usd to|inr to|eur to)\b", 2.3,
           "real_time_data", "Exchange rates change constantly"),

    # Location-specific (needs local data)
    Signal(r"\b(near (?:me|by|my)|around me|in my area|nearby|closest|nearest)\b", 2.3,
           "location_specific", "Query is location-specific — needs local web data"),
    Signal(r"\b(in (?:delhi|mumbai|new york|london|tokyo|paris|berlin|sydney|toronto|beijing|shanghai|bangalore|chennai|kolkata|hyderabad|pune|ahmedabad|jaipur|lucknow))\b", 1.8,
           "location_specific", "Query is location-specific"),
    Signal(r"\b(restaurant|hotel|cafe|store|shop|pharmacy|hospital|atm|bank)\b", 1.8,
           "location_specific", "Local business query — needs web data"),

    # Comparison/review (needs current data)
    Signal(r"\b(vs\.?|versus|compared to|better than|review|rating|top \d|best \w+)\b", 1.5,
           "comparison", "Comparison/review queries often need current data"),
    Signal(r"\b(release date|launch date|coming soon|available|out yet)\b", 2.0,
           "real_time_data", "Release/availability is time-sensitive"),

    # Social media
    Signal(r"\b(twitter|tweet|x\.com|instagram|reddit|linkedin|facebook|youtube|tiktok)\b", 2.0,
           "social_media", "Social media content requires browser access"),

    # Specific website mentions
    Signal(r"\b(amazon|flipkart|ebay|walmart|zomato|swiggy|uber|ola|airbnb|booking\.com)\b", 2.0,
           "website_specific", "Query mentions a specific website/platform"),
]

# ── MODERATE WEB SIGNALS ──────────────────────────────────────────

MODERATE_WEB_SIGNALS: List[Signal] = [
    Signal(r"\b(what is the current|what are the current|who is the current)\b", 2.0,
           "real_time_data", "Asking about current state — may have changed"),
    Signal(r"\b(how (?:many|much) (?:does|is|are|was))\b", 1.2,
           "potentially_realtime", "Could be asking about current data"),
    Signal(r"\b(who (?:is|was|are|were) (?:the |a |an ))\b", 1.0,
           "potentially_realtime", "Could be asking about current people/roles"),
    Signal(r"\b(trending|popular|viral|hot|buzzing)\b", 1.8,
           "real_time_data", "Trending data is time-sensitive"),
    Signal(r"\b(how to (?:find|get|check|download|install|buy|book|watch))\b", 1.5,
           "action_oriented", "Action-oriented query may need web resources"),
    Signal(r"\b(map|direction|route|navigate|location|address|pin code|zip code)\b", 1.8,
           "location_specific", "Location/direction queries need web data"),
    Signal(r"\b(recipe|how to (?:cook|make|bake|prepare))\b", 1.0,
           "potentially_web", "Recipe queries could use web but also may be known"),
    Signal(r"\b(translate|translation|meaning (?:of|in))\b", 1.0,
           "potentially_web", "Translation may need web for context"),
    Signal(r"\b(image|photo|picture|video|watch|listen|play)\b", 1.2,
           "media", "Media queries often need web access"),
    Signal(r"\b(download|install|setup|configure)\b", 1.3,
           "action_oriented", "Download/install queries need current sources"),
    Signal(r"\b API\b", 1.5, "technical_web", "API queries often need documentation from web"),
    Signal(r"\b(documentation|docs|readme|changelog|release notes)\b", 1.5,
           "technical_web", "Documentation may be updated online"),
]

# ── STRONG NO-WEB SIGNALS (high confidence that browser is NOT needed) ──

STRONG_NO_WEB_SIGNALS: List[Signal] = [
    # Math operations
    Signal(r"\b(calculate|compute|what is \d[\d\s+\-*/^.()×÷=]+[\d)]|solve (?:for|the|equation))\b", -2.8,
           "math", "Mathematical computation — no web needed"),
    Signal(r"^[\d\s+\-*/^.()×÷=]+$", -3.0, "math", "Pure mathematical expression"),
    Signal(r"\b(sqrt|square root|power of|factorial|logarithm|sine|cosine|tangent|integral|derivative)\b", -2.5,
           "math", "Mathematical function — no web needed"),
    Signal(r"\b(convert|conversion)\b", -1.5, "math",
           "Unit conversion — usually no web needed (unless currency)"),

    # Code/programming
    Signal(r"\b(write (?:a |the )?(?:code|program|function|script|class|module|algorithm))\b", -2.5,
           "code", "Code generation — no web needed"),
    Signal(r"\b(debug|fix (?:the |this )?(?:code|error|bug|issue))\b", -2.5,
           "code", "Debugging — no web needed"),
    Signal(r"\b(refactor|optimize|improve (?:the |this )?code)\b", -2.3,
           "code", "Code improvement — no web needed"),
    Signal(r"\b(explain (?:this |the )?(?:code|function|algorithm|regex|pattern))\b", -2.0,
           "code", "Code explanation — no web needed"),
    Signal(r"\b(python|javascript|typescript|java|c\+\+|rust|go|golang|ruby|php|swift|kotlin)\b", -1.5,
           "code", "Programming question — often no web needed"),
    Signal(r"\b(regex|regular expression|pattern match)\b", -2.0,
           "code", "Regex question — no web needed"),
    Signal(r"\b(syntax error|type error|runtime error|compilation error|import error)\b", -2.5,
           "code", "Error diagnosis — no web needed"),
    Signal(r"\b(git |github |docker |kubernetes |terraform )\b", -1.2,
           "technical_knowledge", "DevOps question — often no web needed"),

    # General/factual knowledge (stable)
    Signal(r"\b(what is|what are|define|definition of|meaning of)\b", -1.5,
           "general_knowledge", "Definition query — usually general knowledge"),
    Signal(r"\b(who (?:invented|discovered|founded|created|wrote|designed))\b", -1.5,
           "historical_fact", "Historical fact — stable knowledge"),
    Signal(r"\b(when (?:was|did|were))\b", -1.2,
           "historical_fact", "Historical date — stable knowledge"),
    Signal(r"\b(capital of|largest|smallest|longest|shortest|highest|lowest|oldest|deepest)\b", -1.3,
           "general_knowledge", "Geographic/factual knowledge — stable"),
    Signal(r"\b(how (?:does|do|did|can))\b", -1.0,
           "explanation", "Explanatory question — often general knowledge"),
    Signal(r"\b(why (?:is|are|do|does|did|was|were))\b", -1.0,
           "explanation", "Explanatory question — often general knowledge"),
    Signal(r"\b(difference between|compare (?:and|the))\b", -0.8,
           "general_knowledge", "Conceptual comparison — often general knowledge"),
    Signal(r"\b(history of|origin of|etymology|background of)\b", -1.5,
           "historical_fact", "Historical question — stable knowledge"),
    Signal(r"\b(theory|concept|principle|law of|formula)\b", -1.5,
           "academic_knowledge", "Academic/theoretical knowledge — stable"),

    # Creative/writing tasks
    Signal(r"\b(write (?:a |an )?(?:essay|story|poem|email|letter|article|summary|paragraph))\b", -2.5,
           "creative", "Creative writing — no web needed"),
    Signal(r"\b(rewrite|paraphrase|rephrase|summarize (?:this|the))\b", -2.5,
           "creative", "Text manipulation — no web needed"),
    Signal(r"\b(translate (?:this|the|from))\b", -1.5,
           "language", "Translation of provided text — no web needed"),

    # Logic/reasoning
    Signal(r"\b(solve (?:this|the )?(?:puzzle|riddle|problem|logic))\b", -2.5,
           "logic", "Logic puzzle — no web needed"),
    Signal(r"\b(analyze (?:this|the))\b", -1.5,
           "analysis", "Analysis of provided content — no web needed"),
    Signal(r"\b(prove|proof|show that)\b", -2.0,
           "logic", "Mathematical proof — no web needed"),

    # Formatting/data tasks
    Signal(r"\b(format|sort|filter|parse (?:this|the|csv|json|xml))\b", -2.0,
           "data_processing", "Data processing — no web needed"),
    Signal(r"\b(json|csv|xml|yaml|sql|html|css)\b", -1.2,
           "data_format", "Data format question — usually no web needed"),
]

# ── MODERATE NO-WEB SIGNALS ──────────────────────────────────────

MODERATE_NO_WEB_SIGNALS: List[Signal] = [
    Signal(r"\b(example|sample|template|boilerplate)\b", -1.0,
           "code", "Example code — often no web needed"),
    Signal(r"\b(best practice|design pattern|architecture|clean code)\b", -1.0,
           "technical_knowledge", "Software engineering knowledge — usually stable"),
    Signal(r"\b(philosophy|ethical|morality|opinion)\b", -1.5,
           "subjective", "Subjective/philosophical question — no web needed"),
    Signal(r"\b(list (?:of|the)|types of|kinds of|categories of)\b", -0.8,
           "general_knowledge", "Enumerative question — often general knowledge"),
    Signal(r"\b(synonym|antonym|rhyme|anagram)\b", -1.5,
           "language", "Language question — usually no web needed"),
    Signal(r"\b(is it (?:true|possible|safe|legal|normal))\b", -0.8,
           "general_knowledge", "Yes/no knowledge question"),
]


# ═══════════════════════════════════════════════════════════════════
# Override rules — certain combinations that override normal scoring
# ═══════════════════════════════════════════════════════════════════

# When "convert" appears with currency keywords, it's real-time
CURRENCY_KEYWORDS = r"\b(usd|inr|eur|gbp|jpy|cad|aud|currency|exchange rate|dollar|rupee|euro|pound|yen)\b"

# When "how to" is followed by a web action, it's web
WEB_ACTION_KEYWORDS = r"\b(book|buy|order|reserve|register|sign up|download|watch|stream)\b"

# When programming is combined with "latest" or "update", it might need web
UPDATE_KEYWORDS = r"\b(latest|new|updated|recent|changelog|release|version)\b"


# ═══════════════════════════════════════════════════════════════════
# Main Classifier
# ═══════════════════════════════════════════════════════════════════

class WebQueryRouter:
    """
    Rule-based query classifier that determines if a query needs web access.

    Uses weighted signal matching (no LLM) with override rules for edge cases.

    Classification outputs:
        - needs_web: bool — Whether browser/web access is needed
        - confidence: float — 0.0 to 1.0 confidence in the classification
        - category: str — The primary category driving the decision
        - reason: str — Human-readable explanation
        - signals_matched: list — All signals that matched
        - web_score: float — Positive score (higher = more likely needs web)
        - no_web_score: float — Negative score magnitude (higher = more likely no web)
        - suggested_strategy: str — Recommended approach for the agent
    """

    def __init__(self) -> None:
        self._all_signals: List[Signal] = (
            STRONG_WEB_SIGNALS + MODERATE_WEB_SIGNALS +
            STRONG_NO_WEB_SIGNALS + MODERATE_NO_WEB_SIGNALS
        )
        self._classification_cache: Dict[str, Dict] = {}
        self._cache_max_size = 1000
        self._stats = {
            "total_classified": 0,
            "web_needed": 0,
            "no_web_needed": 0,
            "uncertain": 0,
        }

    def classify(self, query: str) -> Dict:
        """
        Classify a query to determine if it needs web/browser access.

        Args:
            query: The user's query string

        Returns:
            Dict with keys: needs_web, confidence, category, reason,
            signals_matched, web_score, no_web_score, suggested_strategy
        """
        if not query or not query.strip():
            return {
                "needs_web": False,
                "confidence": 1.0,
                "category": "empty",
                "reason": "Empty query — no web access needed",
                "signals_matched": [],
                "web_score": 0.0,
                "no_web_score": 0.0,
                "suggested_strategy": "skip",
            }

        query_clean = query.strip()

        # Check cache
        if query_clean in self._classification_cache:
            cached = self._classification_cache[query_clean]
            return cached

        # ── Signal Matching ──────────────────────────────────
        web_score = 0.0
        no_web_score = 0.0
        matched_signals: List[Dict] = []
        primary_category = "unknown"
        primary_reason = "No strong signals detected"

        for signal in self._all_signals:
            match = re.search(signal.pattern, query_clean, signal.flags)
            if match:
                entry = {
                    "category": signal.category,
                    "weight": signal.weight,
                    "reason": signal.reason,
                    "matched_text": match.group(0),
                }
                matched_signals.append(entry)

                if signal.weight > 0:
                    web_score += signal.weight
                    if signal.weight >= 2.0 and web_score >= abs(no_web_score):
                        primary_category = signal.category
                        primary_reason = signal.reason
                else:
                    no_web_score += abs(signal.weight)
                    if abs(signal.weight) >= 2.0 and abs(no_web_score) >= web_score:
                        primary_category = signal.category
                        primary_reason = signal.reason

        # ── Override Rules ───────────────────────────────────
        # Currency conversion overrides "convert" no-web signal
        if re.search(CURRENCY_KEYWORDS, query_clean, re.IGNORECASE):
            if re.search(r"\bconvert\b", query_clean, re.IGNORECASE):
                web_score += 2.5
                no_web_score -= 1.0  # Counteract the no-web convert signal
                primary_category = "real_time_data"
                primary_reason = "Currency conversion requires real-time exchange rates"

        # "How to" + web action overrides no-web
        if re.search(r"\bhow to\b", query_clean, re.IGNORECASE):
            if re.search(WEB_ACTION_KEYWORDS, query_clean, re.IGNORECASE):
                web_score += 2.0
                primary_category = "action_oriented"
                primary_reason = "Action requires web access (booking/buying/downloading)"

        # Programming + update keywords → might need web
        if re.search(r"\b(python|javascript|react|node|npm|pip)\b", query_clean, re.IGNORECASE):
            if re.search(UPDATE_KEYWORDS, query_clean, re.IGNORECASE):
                web_score += 1.5
                primary_category = "technical_web"
                primary_reason = "Programming question with update/version keyword — may need current docs"

        # ── Scoring & Decision ───────────────────────────────
        net_score = web_score - no_web_score

        # Calculate confidence
        total_score = web_score + no_web_score
        if total_score == 0:
            confidence = 0.3  # Very uncertain with no signals
        else:
            # Confidence based on how dominant the winning side is
            dominance = abs(net_score) / total_score
            confidence = min(0.95, 0.4 + dominance * 0.55)

        # Determine if web is needed
        if net_score > 1.0:
            needs_web = True
        elif net_score < -1.0:
            needs_web = False
        else:
            # Marginal — lean towards no-web but flag as uncertain
            needs_web = net_score > 0
            confidence = min(confidence, 0.5)

        # Determine suggested strategy
        if needs_web and confidence >= 0.7:
            strategy = "use_browser"
        elif needs_web and confidence >= 0.5:
            strategy = "try_http_first"  # Try HTTP client (faster), fall back to browser
        elif not needs_web and confidence >= 0.7:
            strategy = "no_web_needed"
        elif not needs_web and confidence >= 0.5:
            strategy = "probably_no_web"
        else:
            strategy = "uncertain_consider_web"  # Agent should consider web access

        # Build result
        result = {
            "needs_web": needs_web,
            "confidence": round(confidence, 2),
            "category": primary_category,
            "reason": primary_reason,
            "signals_matched": matched_signals[-10:],  # Top 10 most recent matches
            "web_score": round(web_score, 2),
            "no_web_score": round(no_web_score, 2),
            "net_score": round(net_score, 2),
            "suggested_strategy": strategy,
        }

        # Update stats
        self._stats["total_classified"] += 1
        if needs_web and confidence >= 0.5:
            self._stats["web_needed"] += 1
        elif not needs_web and confidence >= 0.5:
            self._stats["no_web_needed"] += 1
        else:
            self._stats["uncertain"] += 1

        # Cache result (LRU eviction)
        if len(self._classification_cache) >= self._cache_max_size:
            # Remove oldest entry
            oldest_key = next(iter(self._classification_cache))
            del self._classification_cache[oldest_key]
        self._classification_cache[query_clean] = result

        return result

    def classify_batch(self, queries: List[str]) -> List[Dict]:
        """Classify multiple queries at once."""
        return [self.classify(q) for q in queries]

    def get_stats(self) -> Dict:
        """Get classification statistics."""
        total = self._stats["total_classified"] or 1
        return {
            **self._stats,
            "web_pct": round(self._stats["web_needed"] / total * 100, 1),
            "no_web_pct": round(self._stats["no_web_needed"] / total * 100, 1),
            "uncertain_pct": round(self._stats["uncertain"] / total * 100, 1),
            "cache_size": len(self._classification_cache),
        }

    def should_use_browser(self, query: str) -> bool:
        """Quick boolean check — should the agent use the browser?"""
        result = self.classify(query)
        return result["needs_web"]

    def get_strategy(self, query: str) -> str:
        """Get the recommended strategy for handling this query."""
        result = self.classify(query)
        return result["suggested_strategy"]


# ═══════════════════════════════════════════════════════════════════
# Singleton instance for global use
# ═══════════════════════════════════════════════════════════════════

_router_instance: Optional[WebQueryRouter] = None


def get_router() -> WebQueryRouter:
    """Get or create the global WebQueryRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = WebQueryRouter()
    return _router_instance
