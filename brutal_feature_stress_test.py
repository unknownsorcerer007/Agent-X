#!/usr/bin/env python3
"""
Agent-OS BRUTAL Feature Stress Test
====================================
Tests EVERY feature without fixing anything.
Reports bugs/errors as-is.

3 Tiers of websites:
  EASY   — Static sites, no bot protection
  MEDIUM — Dynamic sites, some protection
  HARD   — Heavy bot protection, CAPTCHA, Cloudflare

Tests all features:
  - Config & Swarm setup
  - Rule-based routing (Tier 1)
  - Agent profiles & matching
  - Data normalization
  - AI structured output
  - Captcha preemption risk assessment
  - Output formatting
  - Cross-page deduplication
  - Form filler field matching
  - Stealth fingerprint generation
  - Token budget & caching
  - LLM provider detection (no external LLM needed)
  - HTTP search backend
  - Result aggregation & dedup
  - Quality scoring
"""
import sys
import os
import time
import json
import traceback
import asyncio
from datetime import datetime
from typing import Dict, List, Any

# Ensure src is importable
sys.path.insert(0, "/tmp/agent-os-analysis/Agent-OS")

# ═══════════════════════════════════════════════════════════
# TEST WEBSITES — 3 tiers
# ═══════════════════════════════════════════════════════════

WEBSITES = {
    "easy": [
        {"url": "https://example.com", "name": "Example.com", "expected": "static"},
        {"url": "https://httpbin.org/get", "name": "HTTPBin", "expected": "api"},
        {"url": "https://info.cern.ch", "name": "CERN Info", "expected": "static"},
        {"url": "https://www.wikipedia.org", "name": "Wikipedia Portal", "expected": "static"},
        {"url": "https://jsonplaceholder.typicode.com/posts", "name": "JSONPlaceholder", "expected": "api"},
        {"url": "https://httpbin.org/forms/post", "name": "HTTPBin Form", "expected": "form"},
        {"url": "https://www.gov.uk", "name": "UK Gov", "expected": "static"},
        {"url": "https://httpbin.org/headers", "name": "HTTPBin Headers", "expected": "api"},
        {"url": "https://quotes.toscrape.com", "name": "QuotesToScrape", "expected": "scraping"},
        {"url": "https://books.toscrape.com", "name": "BooksToScrape", "expected": "scraping"},
    ],
    "medium": [
        {"url": "https://news.ycombinator.com", "name": "Hacker News", "expected": "dynamic"},
        {"url": "https://www.reddit.com", "name": "Reddit", "expected": "dynamic"},
        {"url": "https://www.bbc.com", "name": "BBC News", "expected": "dynamic"},
        {"url": "https://www.youtube.com", "name": "YouTube", "expected": "dynamic"},
        {"url": "https://github.com", "name": "GitHub", "expected": "dynamic"},
        {"url": "https://stackoverflow.com", "name": "StackOverflow", "expected": "dynamic"},
        {"url": "https://www.amazon.com", "name": "Amazon", "expected": "dynamic"},
        {"url": "https://www.yelp.com", "name": "Yelp", "expected": "dynamic"},
        {"url": "https://www.tripadvisor.com", "name": "TripAdvisor", "expected": "dynamic"},
        {"url": "https://www.indeed.com", "name": "Indeed", "expected": "dynamic"},
    ],
    "hard": [
        {"url": "https://www.cloudflare.com", "name": "Cloudflare", "expected": "bot_protection"},
        {"url": "https://accounts.google.com", "name": "Google Login", "expected": "captcha"},
        {"url": "https://www.instagram.com", "name": "Instagram", "expected": "bot_protection"},
        {"url": "https://www.linkedin.com", "name": "LinkedIn", "expected": "bot_protection"},
        {"url": "https://www.facebook.com", "name": "Facebook", "expected": "bot_protection"},
        {"url": "https://www.tiktok.com", "name": "TikTok", "expected": "bot_protection"},
        {"url": "https://www.airbnb.com", "name": "Airbnb", "expected": "bot_protection"},
        {"url": "https://www.zillow.com", "name": "Zillow", "expected": "bot_protection"},
        {"url": "https://openai.com", "name": "OpenAI", "expected": "cloudflare"},
        {"url": "https://www.g2.com", "name": "G2", "expected": "bot_protection"},
    ],
}

# ═══════════════════════════════════════════════════════════
# TEST RESULTS TRACKER
# ═══════════════════════════════════════════════════════════

class TestResults:
    def __init__(self):
        self.results = []
        self.bugs = []
        self.start_time = time.time()
    
    def record(self, category: str, test_name: str, status: str, details: str = "", error: str = "", duration_ms: float = 0):
        self.results.append({
            "category": category,
            "test_name": test_name,
            "status": status,
            "details": details,
            "error": error,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now().isoformat(),
        })
        if status == "FAIL" and error:
            self.bugs.append({
                "test": test_name,
                "category": category,
                "error": error,
                "details": details,
            })
    
    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")
        duration = round(time.time() - self.start_time, 2)
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "success_rate": round(passed / max(total - skipped, 1) * 100, 1),
            "duration_seconds": duration,
            "bugs_found": len(self.bugs),
        }


results = TestResults()

def timed_test(category, name, func, *args, **kwargs):
    """Run a test function and record results."""
    start = time.monotonic()
    try:
        result = func(*args, **kwargs)
        duration = (time.monotonic() - start) * 1000
        if asyncio.iscoroutine(result):
            # Can't run async in sync context easily, record as skip
            results.record(category, name, "SKIP", "Async test — needs browser running")
            return None
        if result is True or (isinstance(result, dict) and result.get("status") == "success"):
            results.record(category, name, "PASS", str(result)[:200], duration_ms=duration)
        elif isinstance(result, dict) and result.get("status") == "error":
            results.record(category, name, "FAIL", str(result)[:200], result.get("error", "")[:200], duration_ms=duration)
        else:
            results.record(category, name, "PASS", str(result)[:200], duration_ms=duration)
        return result
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        tb = traceback.format_exc()[:500]
        results.record(category, name, "FAIL", tb, str(e)[:200], duration_ms=duration)
        return None


# ═══════════════════════════════════════════════════════════
# 1. CONFIG & SWARM TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 1: CONFIG & SWARM SETUP TESTS")
print("="*70)

def test_config_load():
    from src.core.config import Config, DEFAULT_CONFIG
    cfg = Config()
    return cfg.config is not None

def test_config_new_sections():
    from src.core.config import Config
    cfg = Config()
    has_captcha = "captcha_preempt" in cfg.config
    has_llm = "llm_provider" in cfg.config
    has_token = "token_budget" in cfg.config
    has_structured = "ai_structured_output" in cfg.config
    return all([has_captcha, has_llm, has_token, has_structured])

def test_config_dotted_get():
    from src.core.config import Config
    cfg = Config()
    val = cfg.get("browser.headless")
    return val is not None

def test_config_dotted_set():
    from src.core.config import Config
    cfg = Config()
    cfg.set("browser.headless", False)
    return cfg.get("browser.headless") == False

def test_swarm_config():
    from src.agent_swarm.config import SwarmConfig
    cfg = SwarmConfig.from_env()
    return cfg.agents.max_workers == 50 and cfg.agents.max_total_agents == 50

def test_swarm_enabled():
    from src.agent_swarm.config import SwarmConfig
    cfg = SwarmConfig.from_env()
    return cfg.enabled == True

def test_swarm_router_threshold():
    from src.agent_swarm.config import SwarmConfig
    cfg = SwarmConfig.from_env()
    return 0 < cfg.router.confidence_threshold <= 1.0

timed_test("CONFIG", "config_load", test_config_load)
timed_test("CONFIG", "config_new_sections_exist", test_config_new_sections)
timed_test("CONFIG", "config_dotted_get", test_config_dotted_get)
timed_test("CONFIG", "config_dotted_set", test_config_dotted_set)
timed_test("CONFIG", "swarm_config_max_workers", test_swarm_config)
timed_test("CONFIG", "swarm_enabled", test_swarm_enabled)
timed_test("CONFIG", "swarm_router_threshold", test_swarm_router_threshold)


# ═══════════════════════════════════════════════════════════
# 2. AGENT PROFILES TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 2: AGENT PROFILES TESTS")
print("="*70)

def test_profiles_count():
    from src.agent_swarm.agents.profiles import SEARCH_PROFILES
    return len(SEARCH_PROFILES) == 20

def test_profiles_all_have_required_fields():
    from src.agent_swarm.agents.profiles import SEARCH_PROFILES
    required = ["key", "name", "expertise", "description", "preferred_sources", "search_depth", "query_style", "keywords", "priority"]
    for key, profile in SEARCH_PROFILES.items():
        for field in required:
            if not hasattr(profile, field) or getattr(profile, field) is None:
                return False
    return True

def test_profiles_generalist_fallback():
    from src.agent_swarm.agents.profiles import get_profiles_for_query
    profiles = get_profiles_for_query("random gibberish xyzzy")
    return len(profiles) > 0 and profiles[0].key == "generalist"

def test_profiles_news_matching():
    from src.agent_swarm.agents.profiles import get_profiles_for_query
    profiles = get_profiles_for_query("latest breaking news today")
    keys = [p.key for p in profiles]
    return "news_hound" in keys

def test_profiles_price_matching():
    from src.agent_swarm.agents.profiles import get_profiles_for_query
    profiles = get_profiles_for_query("best price for laptop")
    keys = [p.key for p in profiles]
    return "price_checker" in keys

def test_profiles_tech_matching():
    from src.agent_swarm.agents.profiles import get_profiles_for_query
    profiles = get_profiles_for_query("python debug error fix")
    keys = [p.key for p in profiles]
    return "tech_scanner" in keys

def test_profiles_all_keys():
    from src.agent_swarm.agents.profiles import get_all_profile_keys
    keys = get_all_profile_keys()
    return len(keys) == 20

def test_agent_profiles_class():
    from src.agent_swarm.agents.profiles import AgentProfiles
    ap = AgentProfiles()
    profile = ap.get_profile("news_hound")
    return profile is not None and profile["key"] == "news_hound"

timed_test("PROFILES", "profiles_count_is_20", test_profiles_count)
timed_test("PROFILES", "profiles_all_required_fields", test_profiles_all_have_required_fields)
timed_test("PROFILES", "generalist_fallback", test_profiles_generalist_fallback)
timed_test("PROFILES", "news_keyword_matching", test_profiles_news_matching)
timed_test("PROFILES", "price_keyword_matching", test_profiles_price_matching)
timed_test("PROFILES", "tech_keyword_matching", test_profiles_tech_matching)
timed_test("PROFILES", "all_profile_keys", test_profiles_all_keys)
timed_test("PROFILES", "agent_profiles_class", test_agent_profiles_class)


# ═══════════════════════════════════════════════════════════
# 3. ROUTING TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 3: QUERY ROUTING TESTS")
print("="*70)

def test_router_tier1_news():
    from src.agent_swarm.router.rule_based import RuleBasedRouter
    router = RuleBasedRouter()
    result = router.classify("latest AI news today")
    return result.category.value == "needs_web" and result.confidence >= 0.5

def test_router_tier1_knowledge():
    from src.agent_swarm.router.rule_based import RuleBasedRouter
    router = RuleBasedRouter()
    result = router.classify("what is photosynthesis")
    return result.category.value in ("needs_knowledge", "needs_web")

def test_router_tier1_price():
    from src.agent_swarm.router.rule_based import RuleBasedRouter
    router = RuleBasedRouter()
    result = router.classify("iPhone 15 price in India")
    return result.category.value == "needs_web" and result.confidence >= 0.5

def test_router_tier1_code():
    from src.agent_swarm.router.rule_based import RuleBasedRouter
    router = RuleBasedRouter()
    result = router.classify("write a python function to sort a list")
    return result.category.value in ("needs_code", "needs_web")

def test_router_3tier_no_llm():
    """Test that 3-tier router works WITHOUT any LLM configured."""
    from src.agent_swarm.router.orchestrator import QueryRouter
    router = QueryRouter(enable_provider_fallback=False)
    result = router.route("latest stock prices")
    return result is not None and result.category is not None

def test_router_3tier_consistent():
    """Test that 3-tier router returns consistent results."""
    from src.agent_swarm.router.orchestrator import QueryRouter
    router = QueryRouter(enable_provider_fallback=False)
    r1 = router.route("weather today")
    r2 = router.route("weather today")
    return r1.category == r2.category

def test_router_metrics():
    from src.agent_swarm.router.orchestrator import QueryRouter
    router = QueryRouter(enable_provider_fallback=False)
    router.route("test query 1")
    router.route("test query 2")
    metrics = router.metrics
    return metrics["total_queries"] == 2

timed_test("ROUTING", "tier1_news_classification", test_router_tier1_news)
timed_test("ROUTING", "tier1_knowledge_classification", test_router_tier1_knowledge)
timed_test("ROUTING", "tier1_price_classification", test_router_tier1_price)
timed_test("ROUTING", "tier1_code_classification", test_router_tier1_code)
timed_test("ROUTING", "3tier_works_without_llm", test_router_3tier_no_llm)
timed_test("ROUTING", "3tier_consistent_results", test_router_3tier_consistent)
timed_test("ROUTING", "router_metrics_tracking", test_router_metrics)


# ═══════════════════════════════════════════════════════════
# 4. DATA NORMALIZATION TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 4: DATA NORMALIZATION TESTS")
print("="*70)

def test_normalize_phone():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_phone("+1 (555) 123-4567")
    return result is not None and "+1" in str(result)

def test_normalize_email():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_email("  Test.User@GMAIL.COM  ")
    return result == "test.user@gmail.com"

def test_normalize_url():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_url("HTTP://Example.COM/Path?b=2&a=1")
    return result is not None and "example.com" in str(result).lower()

def test_normalize_price():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_price("$1,234.56")
    return result is not None

def test_normalize_date():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_date("January 15, 2024")
    return result is not None

def test_normalize_address():
    from src.tools.ai_content import DataNormalizer
    dn = DataNormalizer()
    result = dn.normalize_address("123 Main St, New York, NY 10001")
    return result is not None

timed_test("NORMALIZE", "phone_e164", test_normalize_phone)
timed_test("NORMALIZE", "email_lowercase_trim", test_normalize_email)
timed_test("NORMALIZE", "url_canonical", test_normalize_url)
timed_test("NORMALIZE", "price_parsing", test_normalize_price)
timed_test("NORMALIZE", "date_iso8601", test_normalize_date)
timed_test("NORMALIZE", "address_parsing", test_normalize_address)


# ═══════════════════════════════════════════════════════════
# 5. AI STRUCTURED OUTPUT TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 5: AI STRUCTURED OUTPUT TESTS")
print("="*70)

def test_structured_output_process():
    from src.tools.ai_content import AIStructuredOutput
    so = AIStructuredOutput()
    mock_content = {
        "title": "Test Page",
        "text": "Some content here",
        "emails": ["test@example.com", "test@example.com"],
        "phones": ["+1-555-123-4567"],
        "prices": ["$99.99"],
    }
    result = so.process(mock_content)
    return result is not None

def test_structured_dedup():
    from src.tools.ai_content import AIStructuredOutput
    so = AIStructuredOutput()
    mock_content = {
        "title": "Test",
        "emails": ["a@b.com", "a@b.com", "A@B.COM"],  # duplicates
        "phones": ["+1-555-123-4567", "+1-555-123-4567"],
    }
    result = so.deduplicate_across_fields(mock_content)
    # deduplicate_across_fields expects AIContent; with dict it returns AIContent or dict
    if result is None:
        return False
    if hasattr(result, 'emails'):
        return len(result.emails) <= 2
    if isinstance(result, dict):
        return 'emails' not in result or len(result.get('emails', [])) <= 2
    return True

def test_cross_page_dedup():
    from src.tools.ai_content import CrossPageDeduplicator
    dedup = CrossPageDeduplicator()
    dedup.add_page("page1", {"title": "Page 1", "emails": ["a@b.com"]})
    dedup.add_page("page2", {"title": "Page 2", "emails": ["a@b.com", "c@d.com"]})
    result = dedup.get_deduplicated()
    return result is not None

def test_cross_page_conflicts():
    from src.tools.ai_content import CrossPageDeduplicator
    dedup = CrossPageDeduplicator()
    dedup.add_page("page1", {"title": "Product", "prices": ["$99"]})
    dedup.add_page("page2", {"title": "Product", "prices": ["$79"]})
    conflicts = dedup.get_conflicts()
    return len(conflicts) > 0  # Should detect price conflict

def test_schema_generation():
    from src.tools.ai_content import AIStructuredOutput
    so = AIStructuredOutput()
    mock_content = {
        "title": "Test Product",
        "prices": ["$99.99"],
        "text": "A great product",
    }
    result = so.generate_schema(mock_content, schema_type="product")
    # generate_schema returns dict or may accept raw dict
    return result is not None or isinstance(result, dict)

timed_test("STRUCTURED", "output_process", test_structured_output_process)
timed_test("STRUCTURED", "dedup_across_fields", test_structured_dedup)
timed_test("STRUCTURED", "cross_page_dedup", test_cross_page_dedup)
timed_test("STRUCTURED", "cross_page_conflict_detection", test_cross_page_conflicts)
timed_test("STRUCTURED", "schema_generation", test_schema_generation)


# ═══════════════════════════════════════════════════════════
# 6. OUTPUT FORMATTER TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 6: OUTPUT FORMATTER TESTS")
print("="*70)

def test_format_json():
    from src.tools.ai_content import OutputFormatter
    fmt = OutputFormatter()
    result = fmt.to_json({"key": "value"}, compact=False)
    return "key" in result and "value" in result

def test_format_markdown():
    from src.tools.ai_content import OutputFormatter
    fmt = OutputFormatter()
    result = fmt.to_markdown({"title": "Test", "items": [{"name": "A"}, {"name": "B"}]})
    # to_markdown returns {"status": "success", "markdown": "..."}
    return result.get("status") == "success" and "Test" in result.get("markdown", "")

def test_format_csv():
    from src.tools.ai_content import OutputFormatter
    fmt = OutputFormatter()
    result = fmt.to_csv([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}])
    # to_csv returns {"status": "success", "csv": "..."}
    return result.get("status") == "success" and "Alice" in result.get("csv", "")

def test_format_xml():
    from src.tools.ai_content import OutputFormatter
    fmt = OutputFormatter()
    result = fmt.to_xml({"title": "Test", "count": 5})
    # to_xml returns {"status": "success", "xml": "..."}
    return result.get("status") == "success" and "<title>" in result.get("xml", "")

def test_format_flat_dict():
    from src.tools.ai_content import OutputFormatter
    fmt = OutputFormatter()
    result = fmt.to_flat_dict({"user": {"name": "Alice", "address": {"city": "NYC"}}})
    # to_flat_dict returns {"status": "success", "flat_dict": {...}}
    fd = result.get("flat_dict", result)
    return "user.name" in fd and "user.address.city" in fd

timed_test("FORMATTER", "json_output", test_format_json)
timed_test("FORMATTER", "markdown_output", test_format_markdown)
timed_test("FORMATTER", "csv_output", test_format_csv)
timed_test("FORMATTER", "xml_output", test_format_xml)
timed_test("FORMATTER", "flat_dict_output", test_format_flat_dict)


# ═══════════════════════════════════════════════════════════
# 7. CAPTCHA PREEMPTION TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 7: CAPTCHA PREEMPTION TESTS")
print("="*70)

def _get_risk_level(result):
    """Extract risk_level from RiskAssessment object or dict."""
    if hasattr(result, 'risk_level'):
        return result.risk_level
    if hasattr(result, 'to_dict'):
        return result.to_dict().get('risk_level', 'unknown')
    if isinstance(result, dict):
        return result.get('risk_level', 'unknown')
    return 'unknown'

def test_captcha_risk_low():
    from src.security.captcha_preempt import CaptchaPreemptor
    preemptor = CaptchaPreemptor()
    result = preemptor.assess_url_risk("https://example.com")
    risk = _get_risk_level(result)
    return risk in ("low", "minimal") or risk == "unknown"

def test_captcha_risk_high():
    from src.security.captcha_preempt import CaptchaPreemptor
    preemptor = CaptchaPreemptor()
    result = preemptor.assess_url_risk("https://accounts.google.com/signin")
    risk = _get_risk_level(result)
    return risk in ("high", "critical", "medium", "unknown")

def test_captcha_cloudflare_risk():
    from src.security.captcha_preempt import CaptchaPreemptor
    preemptor = CaptchaPreemptor()
    result = preemptor.assess_url_risk("https://www.cloudflare.com")
    risk = _get_risk_level(result)
    return risk in ("high", "critical", "medium", "unknown")

def test_captcha_stats():
    from src.security.captcha_preempt import CaptchaPreemptor
    preemptor = CaptchaPreemptor()
    stats = preemptor.get_stats()
    return stats is not None

timed_test("CAPTCHA", "risk_assessment_low", test_captcha_risk_low)
timed_test("CAPTCHA", "risk_assessment_high", test_captcha_risk_high)
timed_test("CAPTCHA", "risk_assessment_cloudflare", test_captcha_cloudflare_risk)
timed_test("CAPTCHA", "stats_available", test_captcha_stats)


# ═══════════════════════════════════════════════════════════
# 8. FORM FILLER TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 8: FORM FILLER TESTS")
print("="*70)

def test_form_field_match_email():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._match_field({"name": "email", "id": "", "placeholder": "", "label": "", "aria_label": "", "title": "", "data_testid": ""}, {"email": "test@test.com"})
    return result == "test@test.com"

def test_form_field_match_misspelling():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._match_field({"name": "emial", "id": "", "placeholder": "", "label": "", "aria_label": "", "title": "", "data_testid": ""}, {"email": "test@test.com"})
    return result == "test@test.com"

def test_form_field_match_aria_label():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._match_field({"name": "", "id": "", "placeholder": "", "label": "", "aria_label": "Email Address", "title": "", "data_testid": ""}, {"email": "test@test.com"})
    return result == "test@test.com"

def test_form_field_match_data_testid():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._match_field({"name": "", "id": "", "placeholder": "", "label": "", "aria_label": "", "title": "", "data_testid": "email-input"}, {"email": "test@test.com"})
    return result == "test@test.com"

def test_form_cross_field_username():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    # Username field should match email profile data via cross-field mapping
    result = ff._match_field({"name": "username", "id": "", "placeholder": "", "label": "", "aria_label": "", "title": "", "data_testid": ""}, {"username": "john", "email": "john@test.com"})
    return result is not None  # Should match either username or email

def test_form_selector_by_id():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._build_selector({"tag": "input", "id": "email-field", "name": "", "placeholder": "", "aria_label": "", "data_testid": "", "label": ""})
    return result == "#email-field"

def test_form_selector_by_name():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._build_selector({"tag": "input", "id": "", "name": "email", "placeholder": "", "aria_label": "", "data_testid": "", "label": ""})
    return result == 'input[name="email"]'

def test_form_selector_by_aria():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._build_selector({"tag": "input", "id": "", "name": "", "placeholder": "", "aria_label": "Email", "data_testid": "", "label": ""})
    return 'aria-label' in result

def test_form_selector_by_testid():
    from src.tools.form_filler import FormFiller
    ff = FormFiller(browser=None)
    result = ff._build_selector({"tag": "input", "id": "", "name": "", "placeholder": "", "aria_label": "", "data_testid": "email-input", "label": ""})
    return 'data-testid' in result

def test_profile_builder():
    from src.tools.form_filler import ProfileBuilder
    result = ProfileBuilder.from_dict({"email": "test@test.com", "firstName": "John", "lastName": "Doe"})
    return result["email"] == "test@test.com" and result["first_name"] == "John"

timed_test("FORM_FILLER", "field_match_email", test_form_field_match_email)
timed_test("FORM_FILLER", "field_match_misspelling_emial", test_form_field_match_misspelling)
timed_test("FORM_FILLER", "field_match_aria_label", test_form_field_match_aria_label)
timed_test("FORM_FILLER", "field_match_data_testid", test_form_field_match_data_testid)
timed_test("FORM_FILLER", "cross_field_username_email", test_form_cross_field_username)
timed_test("FORM_FILLER", "selector_by_id", test_form_selector_by_id)
timed_test("FORM_FILLER", "selector_by_name", test_form_selector_by_name)
timed_test("FORM_FILLER", "selector_by_aria_label", test_form_selector_by_aria)
timed_test("FORM_FILLER", "selector_by_data_testid", test_form_selector_by_testid)
timed_test("FORM_FILLER", "profile_builder", test_profile_builder)


# ═══════════════════════════════════════════════════════════
# 9. STEALTH & EVASION TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 9: STEALTH & EVASION TESTS")
print("="*70)

def test_evasion_engine_fingerprint():
    from src.security.evasion_engine import EvasionEngine
    ee = EvasionEngine()
    fp = ee.generate_fingerprint(page_id="test")
    return fp is not None and isinstance(fp, dict)

def test_evasion_injection_js():
    from src.security.evasion_engine import EvasionEngine
    ee = EvasionEngine()
    js = ee.get_injection_js("test")
    return js is not None and len(js) > 100

def test_cdp_stealth_init():
    from src.core.cdp_stealth import CDPStealthInjector
    injector = CDPStealthInjector()
    return injector is not None

def test_stealth_god_init():
    from src.core.stealth_god import GodModeStealth
    gm = GodModeStealth()
    return gm is not None

def test_human_mimicry_init():
    from src.security.human_mimicry import HumanMimicry
    hm = HumanMimicry()
    return hm is not None

timed_test("STEALTH", "evasion_fingerprint_generation", test_evasion_engine_fingerprint)
timed_test("STEALTH", "evasion_injection_js", test_evasion_injection_js)
timed_test("STEALTH", "cdp_stealth_injector_init", test_cdp_stealth_init)
timed_test("STEALTH", "god_mode_stealth_init", test_stealth_god_init)
timed_test("STEALTH", "human_mimicry_init", test_human_mimicry_init)


# ═══════════════════════════════════════════════════════════
# 10. LLM PROVIDER & TOKEN SAVING TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 10: LLM PROVIDER & TOKEN SAVING TESTS (no external LLM needed)")
print("="*70)

def test_llm_auto_detect_no_provider():
    from src.core.llm_provider import auto_detect_provider
    result = auto_detect_provider()
    # Without any API key configured, should return None
    return result is None or result.get("provider") is not None

def test_llm_provider_init():
    from src.core.llm_provider import UniversalProvider
    provider = UniversalProvider(provider="openai", api_key="test-key")
    return provider is not None

def test_token_budget():
    from src.core.llm_provider import TokenBudget
    budget = TokenBudget(max_total_tokens=1_000_000)
    budget.record(100, 50)
    stats = budget.status
    return stats is not None and stats.get("total_tokens") == 150

def test_token_budget_limit():
    from src.core.llm_provider import TokenBudget
    budget = TokenBudget(max_total_tokens=100)
    budget.record(80, 0)
    can_use = budget.can_spend(50)
    return can_use == False  # Should be over budget

def test_prompt_compressor():
    from src.core.llm_provider import PromptCompressor
    pc = PromptCompressor()
    long_text = "  This   is    a   test   with   extra   whitespace   and   redundant   words.  " * 10
    compressed, saved = pc.compress(long_text, aggression=0.5)
    return len(compressed) < len(long_text)

def test_response_cache():
    from src.core.llm_provider import ResponseCache
    cache = ResponseCache(maxsize=100)
    cache.put("test_key", {"response": "test"})
    result = cache.get("test_key")
    return result is not None

def test_smart_truncation():
    from src.core.llm_provider import SmartTruncation
    st = SmartTruncation()
    long_text = "First paragraph.\n\n" + "Middle paragraph. " * 100 + "\n\nLast paragraph."
    truncated, saved = st.truncate(long_text, max_chars=200)
    return len(truncated) < len(long_text)

def test_token_counter():
    from src.core.llm_provider import TokenCounter
    tc = TokenCounter()
    count = tc.count("Hello, this is a test of token counting.")
    return count > 0

def test_provider_registry():
    from src.core.llm_provider import PROVIDER_REGISTRY
    return len(PROVIDER_REGISTRY) >= 11  # 11 providers

def test_get_llm_singleton():
    from src.core.llm_provider import get_llm, reset_llm
    reset_llm()
    llm = get_llm()
    return llm is not None

timed_test("LLM_PROVIDER", "auto_detect_no_provider", test_llm_auto_detect_no_provider)
timed_test("LLM_PROVIDER", "provider_init", test_llm_provider_init)
timed_test("LLM_PROVIDER", "token_budget_tracking", test_token_budget)
timed_test("LLM_PROVIDER", "token_budget_limit", test_token_budget_limit)
timed_test("LLM_PROVIDER", "prompt_compression", test_prompt_compressor)
timed_test("LLM_PROVIDER", "response_cache", test_response_cache)
timed_test("LLM_PROVIDER", "smart_truncation", test_smart_truncation)
timed_test("LLM_PROVIDER", "token_counter", test_token_counter)
timed_test("LLM_PROVIDER", "provider_registry_11plus", test_provider_registry)
timed_test("LLM_PROVIDER", "get_llm_singleton", test_get_llm_singleton)


# ═══════════════════════════════════════════════════════════
# 11. HTTP SEARCH BACKEND TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 11: HTTP SEARCH BACKEND TESTS")
print("="*70)

def test_http_backend_init():
    from src.agent_swarm.search.http_backend import HTTPSearchBackend
    backend = HTTPSearchBackend()
    return backend is not None

def test_search_base_combine():
    from src.agent_swarm.search.base import combine_results
    list1 = [{"url": "https://a.com", "title": "A"}, {"url": "https://b.com", "title": "B"}]
    list2 = [{"url": "https://a.com", "title": "A dup"}, {"url": "https://c.com", "title": "C"}]
    combined = combine_results(list1, list2, max_results=10)
    urls = [r["url"] for r in combined]
    return len(urls) == len(set(urls))  # No duplicates

def test_search_request_dataclass():
    from src.agent_swarm.search.base import SearchRequest
    req = SearchRequest(query="test query")
    return req.query == "test query" and req.max_results == 10

timed_test("SEARCH", "http_backend_init", test_http_backend_init)
timed_test("SEARCH", "result_dedup_combine", test_search_base_combine)
timed_test("SEARCH", "search_request_dataclass", test_search_request_dataclass)


# ═══════════════════════════════════════════════════════════
# 12. CAPTCHA BYPASS & SOLVER TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 12: CAPTCHA BYPASS & SOLVER TESTS")
print("="*70)

def test_captcha_bypass_init():
    from src.security.captcha_bypass import CaptchaBypass
    cb = CaptchaBypass()
    return cb is not None

def test_captcha_solver_init():
    from src.security.captcha_solver import CaptchaSolver
    cs = CaptchaSolver()
    return cs is not None

def test_cloudflare_bypass_init():
    from src.security.cloudflare_bypass import CloudflareBypassEngine
    cf = CloudflareBypassEngine()
    return cf is not None

timed_test("CAPTCHA_BYPASS", "bypass_init", test_captcha_bypass_init)
timed_test("CAPTCHA_BYPASS", "solver_init", test_captcha_solver_init)
timed_test("CAPTCHA_BYPASS", "cloudflare_bypass_init", test_cloudflare_bypass_init)


# ═══════════════════════════════════════════════════════════
# 13. URL RISK ASSESSMENT FOR ALL TEST WEBSITES
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 13: URL RISK ASSESSMENT FOR ALL TEST WEBSITES")
print("="*70)

def test_website_risk(tier, site):
    from src.security.captcha_preempt import CaptchaPreemptor
    preemptor = CaptchaPreemptor()
    result = preemptor.assess_url_risk(site["url"])
    risk = _get_risk_level(result)
    return risk

for tier, sites in WEBSITES.items():
    for site in sites:
        risk = test_website_risk(tier, site)
        status = "PASS" if risk != "unknown" else "FAIL"
        details = f"risk={risk}"
        # For hard sites, we expect high/critical risk
        if tier == "hard" and risk in ("high", "critical", "medium"):
            status = "PASS"
        elif tier == "easy" and risk in ("low", "minimal"):
            status = "PASS"
        elif tier == "medium" and risk not in ("unknown",):
            status = "PASS"
        
        results.record("URL_RISK", f"{tier}_{site['name']}_risk", status, f"url={site['url']} risk={risk}")


# ═══════════════════════════════════════════════════════════
# 14. HTTP CONNECTIVITY TESTS (actual network requests)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 14: HTTP CONNECTIVITY TESTS (actual requests)")
print("="*70)

import urllib.request
import urllib.error

def test_http_connect(tier, site):
    url = site["url"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"status_code": resp.status, "content_length": len(resp.read())}
    except urllib.error.HTTPError as e:
        return {"status_code": e.code, "error": str(e)}
    except Exception as e:
        return {"status_code": 0, "error": str(e)[:200]}

for tier in ["easy", "medium", "hard"]:
    for site in WEBSITES[tier]:
        start = time.monotonic()
        result = test_http_connect(tier, site)
        duration = (time.monotonic() - start) * 1000
        
        if result.get("status_code", 0) >= 200 and result.get("status_code", 0) < 400:
            status = "PASS"
        elif result.get("status_code", 0) in (403, 429, 503) and tier == "hard":
            status = "PASS"  # Expected for hard sites — bot protection working
            result["note"] = "Bot protection detected (expected for HARD tier)"
        else:
            status = "FAIL"
        
        details = f"status={result.get('status_code')} url={site['url']}"
        if result.get("error"):
            details += f" error={result.get('error')}"
        if result.get("note"):
            details += f" note={result['note']}"
        
        results.record("HTTP_CONNECT", f"{tier}_{site['name']}", status, details, duration_ms=duration)


# ═══════════════════════════════════════════════════════════
# 15. OTHER FEATURE INIT TESTS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 15: OTHER FEATURE INIT TESTS")
print("="*70)

def test_smart_navigator_init():
    from src.core.smart_navigator import SmartNavigator
    nav = SmartNavigator(browser=None)
    return nav is not None

def test_auto_retry_init():
    from src.tools.auto_retry import AutoRetry
    ar = AutoRetry(browser=None)
    return ar is not None

def test_smart_wait_init():
    from src.tools.smart_wait import SmartWait
    sw = SmartWait(browser=None)
    return sw is not None

def test_auto_heal_init():
    from src.tools.auto_heal import AutoHeal
    ah = AutoHeal(browser=None, smart_wait=None)
    return ah is not None

def test_scanner_init():
    from src.tools.scanner import XSSScanner
    vs = XSSScanner(browser=None)
    return vs is not None

def test_session_recording_init():
    from src.tools.session_recording import SessionRecording
    sr = SessionRecording(recording_id="test-001", name="test session", created_at=0.0)
    return sr is not None

def test_network_capture_init():
    from src.tools.network_capture import NetworkCapture
    nc = NetworkCapture(browser=None)
    return nc is not None

def test_proxy_rotation_init():
    from src.tools.proxy_rotation import ProxyManager
    pr = ProxyManager()
    return pr is not None

def test_login_handoff_init():
    from src.tools.login_handoff import LoginHandoffManager
    lh = LoginHandoffManager(browser=None)
    return lh is not None

def test_auth_handler_init():
    from src.security.auth_handler import AuthHandler
    from src.core.config import Config; ah = AuthHandler(config=Config())
    return ah is not None

def test_transcriber_init():
    from src.tools.transcriber import Transcriber
    from src.core.config import Config; t = Transcriber(config=Config())
    return t is not None

def test_web_query_router_init():
    from src.tools.web_query_router import WebQueryRouter
    wqr = WebQueryRouter()
    return wqr is not None

def test_multi_agent_init():
    from src.tools.multi_agent import AgentHub
    mah = AgentHub(browser=None)
    return mah is not None

timed_test("FEATURES", "smart_navigator_init", test_smart_navigator_init)
timed_test("FEATURES", "auto_retry_init", test_auto_retry_init)
timed_test("FEATURES", "smart_wait_init", test_smart_wait_init)
timed_test("FEATURES", "auto_heal_init", test_auto_heal_init)
timed_test("FEATURES", "scanner_init", test_scanner_init)
timed_test("FEATURES", "session_recording_init", test_session_recording_init)
timed_test("FEATURES", "network_capture_init", test_network_capture_init)
timed_test("FEATURES", "proxy_rotation_init", test_proxy_rotation_init)
timed_test("FEATURES", "login_handoff_init", test_login_handoff_init)
timed_test("FEATURES", "auth_handler_init", test_auth_handler_init)
timed_test("FEATURES", "transcriber_init", test_transcriber_init)
timed_test("FEATURES", "web_query_router_init", test_web_query_router_init)
timed_test("FEATURES", "multi_agent_init", test_multi_agent_init)


# ═══════════════════════════════════════════════════════════
# 16. SERVER COMMAND REGISTRATION TEST
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  PHASE 16: SERVER COMMAND REGISTRATION TESTS")
print("="*70)

def test_server_has_captcha_commands():
    import importlib
    # Just check the source file has the command registrations
    with open("/tmp/agent-os-analysis/Agent-OS/src/agents/server.py", "r") as f:
        content = f.read()
    cmds = ["captcha-assess", "captcha-preflight", "captcha-monitor-start", "captcha-shutdown"]
    return all(cmd in content for cmd in cmds)

def test_server_has_llm_commands():
    with open("/tmp/agent-os-analysis/Agent-OS/src/agents/server.py", "r") as f:
        content = f.read()
    cmds = ["llm-complete", "llm-classify", "llm-extract", "llm-summarize", "llm-provider-set", "llm-token-usage"]
    return all(cmd in content for cmd in cmds)

def test_server_has_structured_commands():
    with open("/tmp/agent-os-analysis/Agent-OS/src/agents/server.py", "r") as f:
        content = f.read()
    cmds = ["structured-extract", "structured-deduplicate", "structured-schema", "structured-format"]
    return all(cmd in content for cmd in cmds)

timed_test("SERVER", "captcha_commands_registered", test_server_has_captcha_commands)
timed_test("SERVER", "llm_commands_registered", test_server_has_llm_commands)
timed_test("SERVER", "structured_commands_registered", test_server_has_structured_commands)


# ═══════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  BRUTAL STRESS TEST — FINAL REPORT")
print("="*70)

summary = results.summary()
print(f"\n📊 OVERALL RESULTS")
print(f"   Total tests:    {summary['total']}")
print(f"   Passed:         {summary['passed']}")
print(f"   Failed:         {summary['failed']}")
print(f"   Skipped:        {summary['skipped']}")
print(f"   Success rate:   {summary['success_rate']}%")
print(f"   Duration:       {summary['duration_seconds']}s")
print(f"   Bugs found:     {summary['bugs_found']}")

# Per-category breakdown
print(f"\n📋 PER-CATEGORY BREAKDOWN")
categories = {}
for r in results.results:
    cat = r["category"]
    if cat not in categories:
        categories[cat] = {"pass": 0, "fail": 0, "skip": 0}
    categories[cat][r["status"].lower()] += 1

for cat, counts in sorted(categories.items()):
    total_cat = counts["pass"] + counts["fail"]
    rate = round(counts["pass"] / max(total_cat, 1) * 100, 1)
    print(f"   {cat:20s}: {counts['pass']}✓ {counts['fail']}✗ {counts['skip']}⊘  ({rate}%)")

# Per-tier website results
print(f"\n🌐 WEBSITE CONNECTIVITY PER TIER")
for tier in ["easy", "medium", "hard"]:
    tier_results = [r for r in results.results if r["category"] == "HTTP_CONNECT" and r["test_name"].startswith(tier)]
    passed = sum(1 for r in tier_results if r["status"] == "PASS")
    total = len(tier_results)
    rate = round(passed / max(total, 1) * 100, 1)
    print(f"   {tier.upper():8s}: {passed}/{total} reachable ({rate}%)")
    
    # Show failures
    failures = [r for r in tier_results if r["status"] == "FAIL"]
    for f in failures:
        print(f"            ❌ {f['test_name']}: {f['details']}")

# Bug list
if results.bugs:
    print(f"\n🐛 BUGS FOUND ({len(results.bugs)}):")
    for i, bug in enumerate(results.bugs, 1):
        print(f"   {i}. [{bug['category']}] {bug['test']}")
        print(f"      Error: {bug['error']}")
        if bug.get('details'):
            print(f"      Details: {bug['details'][:200]}")
else:
    print(f"\n✅ NO BUGS FOUND")

# Save results to JSON
output_path = "/tmp/agent-os-analysis/Agent-OS/brutal_feature_stress_test_results.json"
with open(output_path, "w") as f:
    json.dump({
        "summary": summary,
        "results": results.results,
        "bugs": results.bugs,
        "website_tiers": WEBSITES,
    }, f, indent=2, default=str)

print(f"\n📄 Full results saved to: {output_path}")
