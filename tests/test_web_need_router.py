"""
Tests for Web-Need Router — the decision engine that determines if a query
needs web/browser access or can be answered from knowledge.
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.web_need_router import (
    WebNeedRouter, RouteResult, route_query, get_routing_stats,
    SELF_ASK_PROMPT, QUICK_ROUTING_GUIDE,
)


# ─── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def router():
    """Create a fresh WebNeedRouter for each test."""
    return WebNeedRouter()


# ─── Core Routing Tests ────────────────────────────────────────

class TestNoWebNeeded:
    """Queries that should NOT need web access."""

    def test_math_question(self, router):
        result = router.route("What is 2 + 2?")
        assert result.needs_web is False
        assert result.action == "answer_from_knowledge"

    def test_definition(self, router):
        result = router.route("What is the definition of photosynthesis?")
        assert result.needs_web is False
        assert result.action == "answer_from_knowledge"

    def test_historical_fact(self, router):
        result = router.route("Who invented the telephone?")
        assert result.needs_web is False

    def test_programming_help(self, router):
        result = router.route("How to write a Python function to reverse a string?")
        assert result.needs_web is False
        assert result.action == "answer_from_knowledge"

    def test_explanation(self, router):
        result = router.route("Explain how neural networks work")
        assert result.needs_web is False

    def test_difference_question(self, router):
        result = router.route("What is the difference between TCP and UDP?")
        assert result.needs_web is False

    def test_creative_writing(self, router):
        result = router.route("Write a poem about the ocean")
        assert result.needs_web is False

    def test_translate(self, router):
        result = router.route("How to say hello in Japanese?")
        assert result.needs_web is False

    def test_code_debug(self, router):
        result = router.route("Fix this Python error: IndexError list index out of range")
        assert result.needs_web is False

    def test_formula_question(self, router):
        result = router.route("What is the formula for calculating compound interest?")
        assert result.needs_web is False


class TestSearchWebNeeded:
    """Queries that need live/current data — search is sufficient."""

    def test_weather(self, router):
        result = router.route("What's the weather in Delhi right now?")
        assert result.needs_web is True
        assert result.action in ("search", "browse")

    def test_stock_price(self, router):
        result = router.route("What is the current price of Apple stock?")
        assert result.needs_web is True
        assert result.action in ("search", "browse")

    def test_latest_news(self, router):
        result = router.route("What are the latest news headlines today?")
        assert result.needs_web is True

    def test_bitcoin_price(self, router):
        result = router.route("What is the current Bitcoin price?")
        assert result.needs_web is True

    def test_flight_status(self, router):
        result = router.route("What is the flight status of AI-101 today?")
        assert result.needs_web is True

    def test_exchange_rate(self, router):
        result = router.route("What is the USD to INR exchange rate today?")
        assert result.needs_web is True

    def test_trending(self, router):
        result = router.route("What is trending on Twitter right now?")
        assert result.needs_web is True

    def test_ipl_score(self, router):
        result = router.route("What is the IPL score today?")
        assert result.needs_web is True

    def test_recent_events(self, router):
        result = router.route("What happened in the world this week?")
        assert result.needs_web is True


class TestBrowseWebNeeded:
    """Queries that need full browser interaction."""

    def test_instagram_login(self, router):
        result = router.route("Log in to Instagram and check my DMs")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_facebook_post(self, router):
        result = router.route("Post a message on Facebook")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_fill_form(self, router):
        result = router.route("Fill out the application form on the website")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_book_flight(self, router):
        result = router.route("Book a flight from Delhi to Mumbai on MakeMyTrip")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_buy_product(self, router):
        result = router.route("Buy this laptop on Amazon")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_screenshot_page(self, router):
        result = router.route("Take a screenshot of the Google homepage")
        assert result.needs_web is True

    def test_send_email(self, router):
        result = router.route("Send an email to john@example.com via Gmail")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_apply_job(self, router):
        result = router.route("Apply for the software engineer job on LinkedIn")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_auto_login(self, router):
        result = router.route("Auto-login to github.com and check my repos")
        assert result.needs_web is True
        assert result.action == "browse"


class TestURLDetection:
    """Test URL detection and fetch vs browse decision."""

    def test_wikipedia_url(self, router):
        result = router.route("Read this article: https://en.wikipedia.org/wiki/Python_(programming_language)")
        assert result.needs_web is True
        # Wikipedia should be fetchable
        assert result.action in ("search", "browse")

    def test_instagram_url(self, router):
        result = router.route("Go to https://www.instagram.com and check my feed")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_github_url(self, router):
        result = router.route("Check out https://github.com/microsoft/vscode")
        assert result.needs_web is True

    def test_amazon_url(self, router):
        result = router.route("Go to https://www.amazon.com/dp/B0BR4JD8QD")
        assert result.needs_web is True
        assert result.action == "browse"


class TestHybridCases:
    """Queries with mixed signals."""

    def test_compare_current_with_knowledge(self, router):
        result = router.route("Compare today's weather with historical average")
        assert result.needs_web is True
        # Has both live data and knowledge components

    def test_recent_tech_with_explanation(self, router):
        result = router.route("Explain the latest AI developments and how transformers work")
        # Should recognize "latest" needs web, but "how transformers work" is knowledge
        assert result.needs_web is True


class TestConfidence:
    """Test confidence levels."""

    def test_high_confidence_browser(self, router):
        result = router.route("Log in to Instagram and post a photo")
        assert result.confidence >= 0.7

    def test_high_confidence_knowledge(self, router):
        result = router.route("What is the capital of France?")
        assert result.confidence >= 0.4  # May be moderate due to low signal

    def test_confidence_range(self, router):
        result = router.route("What is the latest stock price of Tesla?")
        assert 0.0 <= result.confidence <= 1.0


class TestSuggestedCommands:
    """Test that correct commands are suggested."""

    def test_browse_suggests_navigate(self, router):
        result = router.route("Log in to Facebook")
        assert "navigate" in result.suggested_commands or "smart-navigate" in result.suggested_commands

    def test_search_suggests_fetch(self, router):
        result = router.route("What is the latest news today?")
        assert any(cmd in result.suggested_commands for cmd in ["fetch", "smart-navigate"])

    def test_knowledge_no_commands(self, router):
        result = router.route("What is 2 + 2?")
        assert result.suggested_commands == []


class TestSearchQueries:
    """Test search query generation."""

    def test_generates_search_queries(self, router):
        result = router.route("What is the current Bitcoin price?")
        assert len(result.search_queries) >= 1

    def test_max_three_queries(self, router):
        result = router.route("What is the current Bitcoin price and Ethereum price and stock market status today?")
        assert len(result.search_queries) <= 3


class TestCustomRules:
    """Test custom rule addition."""

    def test_add_browser_rule(self, router):
        router.add_browser_rule(r"\b(zomato)\b", "Zomato requires browser", 1.5)
        result = router.route("Order food from Zomato")
        assert result.needs_web is True
        assert result.action == "browse"

    def test_add_live_data_rule(self, router):
        router.add_live_data_rule(r"\b(cryptocurrency)\b", "Crypto prices change constantly", 1.0)
        result = router.route("What is the current cryptocurrency market cap?")
        assert result.needs_web is True

    def test_add_knowledge_rule(self, router):
        router.add_knowledge_rule(r"\b(recipe)\b", "Recipes are general knowledge", 1.0)
        result = router.route("Give me a recipe for pasta carbonara")
        assert result.needs_web is False


class TestStats:
    """Test routing statistics."""

    def test_stats_tracking(self, router):
        router.route("What is 2 + 2?")
        router.route("What's the weather today?")
        router.route("Log in to Instagram")

        stats = router.get_stats()
        assert stats["total_routed"] == 3
        assert stats["avg_confidence"] > 0.0

    def test_stats_content(self, router):
        stats = router.get_stats()
        assert "browser_rules" in stats
        assert "live_data_rules" in stats
        assert "knowledge_rules" in stats
        assert "browser_domains" in stats
        assert "fetch_domains" in stats
        assert stats["browser_domains"] > 0


class TestConvenienceFunction:
    """Test the module-level convenience function."""

    def test_route_query(self):
        result = route_query("What is the weather in Mumbai?")
        assert isinstance(result, dict)
        assert "needs_web" in result
        assert "action" in result
        assert "confidence" in result

    def test_route_query_knowledge(self):
        result = route_query("What is the capital of Japan?")
        assert result["needs_web"] is False

    def test_get_routing_stats(self):
        stats = get_routing_stats()
        assert isinstance(stats, dict)
        assert "total_routed" in stats


class TestRouteResult:
    """Test RouteResult dataclass."""

    def test_to_dict(self):
        result = RouteResult(
            needs_web=True,
            action="browse",
            confidence=0.85,
            reason="Browser interaction needed",
            suggested_commands=["navigate"],
            suggested_urls=["https://instagram.com"],
            search_queries=["instagram feed"],
        )
        d = result.to_dict()
        assert d["needs_web"] is True
        assert d["action"] == "browse"
        assert d["confidence"] == 0.85
        assert d["reason"] == "Browser interaction needed"
        assert d["suggested_commands"] == ["navigate"]
        assert "instagram.com" in d["suggested_urls"][0]
        assert d["search_queries"] == ["instagram feed"]


class TestSystemPrompts:
    """Test that system prompt constants are defined."""

    def test_self_ask_prompt_exists(self):
        assert len(SELF_ASK_PROMPT) > 100
        assert "KNOWLEDGE CHECK" in SELF_ASK_PROMPT
        assert "FRESHNESS CHECK" in SELF_ASK_PROMPT
        assert "INTERACTION CHECK" in SELF_ASK_PROMPT

    def test_quick_routing_guide_exists(self):
        assert len(QUICK_ROUTING_GUIDE) > 50
        assert "No browser needed" in QUICK_ROUTING_GUIDE
        assert "browser_fetch" in QUICK_ROUTING_GUIDE


class TestPerformance:
    """Test that routing is fast (sub-millisecond for most queries)."""

    def test_routing_speed(self, router):
        import time
        queries = [
            "What is 2 + 2?",
            "What's the weather today?",
            "Log in to Instagram",
            "Read https://en.wikipedia.org/wiki/Python",
            "Explain quantum computing",
        ]
        start = time.time()
        for q in queries:
            router.route(q)
        elapsed = time.time() - start
        avg_ms = (elapsed / len(queries)) * 1000
        # Should be well under 10ms per query (usually <1ms)
        assert avg_ms < 10.0, f"Average routing time {avg_ms:.2f}ms is too slow"


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_query(self, router):
        result = router.route("")
        # Should not crash
        assert isinstance(result, RouteResult)

    def test_very_long_query(self, router):
        query = "What is the weather? " * 1000
        result = router.route(query)
        assert isinstance(result, RouteResult)

    def test_special_characters(self, router):
        result = router.route("What is the price of AAPL @ $???")
        assert isinstance(result, RouteResult)

    def test_hindi_mix_query(self, router):
        result = router.route("Aaj ka weather kya hai Delhi mein?")
        # "weather" keyword should trigger web need
        assert result.needs_web is True

    def test_context_parameter(self, router):
        result = router.route("Book it", context="I was looking at flights on MakeMyTrip")
        # Context should help determine browsing intent
        assert isinstance(result, RouteResult)

    def test_multiple_urls(self, router):
        result = router.route("Compare https://www.amazon.com/dp/123 and https://www.flipkart.com/p/456")
        assert result.needs_web is True
        assert len(result.suggested_urls) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
