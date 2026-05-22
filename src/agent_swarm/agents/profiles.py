"""Agent profile definitions - MiroFish-inspired personas adapted for web search."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchProfile:
    """Definition of a search agent profile."""
    key: str
    name: str
    expertise: str
    description: str
    preferred_sources: list[str]
    search_depth: str  # quick, medium, thorough
    query_style: str  # factual_direct, specific_targeted, technical_precise, exploratory_detailed, broad_exploratory
    keywords: list[str]
    priority: int = 0


SEARCH_PROFILES: dict[str, SearchProfile] = {
    "news_hound": SearchProfile(
        key="news_hound",
        name="News Hound",
        expertise="current_events",
        description="Specializes in finding latest news, breaking stories, and current events from reputable news sources.",
        preferred_sources=["reuters.com", "apnews.com", "bbc.com", "cnn.com", "ndtv.com", "timesofindia.indiatimes.com"],
        search_depth="quick",
        query_style="factual_direct",
        keywords=["news", "latest", "breaking", "update", "headline", "today", "current events", "developing"],
        priority=8,
    ),
    "deep_researcher": SearchProfile(
        key="deep_researcher",
        name="Deep Researcher",
        expertise="academic_technical",
        description="Excels at in-depth research, finding academic papers, technical documentation, and comprehensive analyses.",
        preferred_sources=["scholar.google.com", "arxiv.org", "researchgate.net", "medium.com", "wikipedia.org"],
        search_depth="thorough",
        query_style="exploratory_detailed",
        keywords=["research", "study", "analysis", "paper", "academic", "detailed", "comprehensive", "in-depth"],
        priority=5,
    ),
    "price_checker": SearchProfile(
        key="price_checker",
        name="Price Checker",
        expertise="commerce_pricing",
        description="Finds current prices, deals, comparisons, and reviews for products and services.",
        preferred_sources=["amazon.com", "flipkart.com", "price.com", "shopping.google.com", "ebay.com"],
        search_depth="quick",
        query_style="specific_targeted",
        keywords=["price", "cost", "buy", "cheap", "discount", "deal", "offer", "review", "compare", "vs"],
        priority=9,
    ),
    "tech_scanner": SearchProfile(
        key="tech_scanner",
        name="Tech Scanner",
        expertise="technology_software",
        description="Scans tech blogs, documentation, GitHub, and Stack Overflow for technical information and solutions.",
        preferred_sources=["github.com", "stackoverflow.com", "docs.python.org", "developer.mozilla.org", "dev.to"],
        search_depth="medium",
        query_style="technical_precise",
        keywords=["tech", "software", "programming", "api", "code", "github", "bug", "debug", "install", "python", "javascript"],
        priority=7,
    ),
    "generalist": SearchProfile(
        key="generalist",
        name="Generalist",
        expertise="general",
        description="Versatile search agent that handles a wide range of queries with balanced coverage across multiple sources.",
        preferred_sources=["wikipedia.org", "reuters.com"],
        search_depth="medium",
        query_style="broad_exploratory",
        keywords=["general", "help", "assist", "what", "how", "why", "explain", "tell me", "can you", "information", "question", "query", "find", "search", "look up", "about", "info", "how to", "what is", "overview"],
        priority=1,
    ),
    "social_media_tracker": SearchProfile(
        key="social_media_tracker",
        name="Social Media Tracker",
        expertise="social_media",
        description="Specializes in tracking social media trends, posts, influencers, and viral content across Instagram, Twitter, Facebook, LinkedIn, and TikTok.",
        preferred_sources=["twitter.com", "x.com", "instagram.com", "facebook.com", "linkedin.com", "tiktok.com", "threads.net"],
        search_depth="medium",
        query_style="broad_exploratory",
        keywords=["social media", "instagram", "twitter", "facebook", "tiktok", "linkedin", "post", "tweet", "viral", "trending", "influencer", "followers", "profile"],
        priority=9,
    ),
    "finance_analyst": SearchProfile(
        key="finance_analyst",
        name="Finance Analyst",
        expertise="finance_markets",
        description="Finds financial data, stock prices, market analysis, crypto information, and investment insights from leading financial sources.",
        preferred_sources=["finance.yahoo.com", "bloomberg.com", "reuters.com", "marketwatch.com", "investing.com"],
        search_depth="quick",
        query_style="factual_direct",
        keywords=["stock", "market", "crypto", "bitcoin", "investment", "portfolio", "trading", "nasdaq", "dow jones", "share price", "dividend", "ipo"],
        priority=8,
    ),
    "health_researcher": SearchProfile(
        key="health_researcher",
        name="Health Researcher",
        expertise="health_medical",
        description="Specializes in medical and health information, including diseases, treatments, symptoms, and clinical research from authoritative health sources.",
        preferred_sources=["mayoclinic.org", "webmd.com", "who.int", "cdc.gov", "nih.gov", "pubmed.ncbi.nlm.nih.gov"],
        search_depth="thorough",
        query_style="exploratory_detailed",
        keywords=["health", "medical", "disease", "symptom", "treatment", "doctor", "medicine", "diagnosis", "vaccine", "clinical", "patient"],
        priority=7,
    ),
    "legal_eagle": SearchProfile(
        key="legal_eagle",
        name="Legal Eagle",
        expertise="legal_regulatory",
        description="Finds legal and regulatory information, court cases, statutes, compliance guidance, and intellectual property details from legal databases.",
        preferred_sources=["law.cornell.edu", "findlaw.com", "justia.com", "courtlistener.com", "sec.gov"],
        search_depth="thorough",
        query_style="technical_precise",
        keywords=["law", "legal", "regulation", "compliance", "statute", "court", "lawsuit", "patent", "copyright", "attorney", "contract"],
        priority=6,
    ),
    "travel_scout": SearchProfile(
        key="travel_scout",
        name="Travel Scout",
        expertise="travel_local",
        description="Finds travel deals, hotel bookings, flight information, restaurant reviews, and local attractions for trip planning.",
        preferred_sources=["tripadvisor.com", "booking.com", "airbnb.com", "google.com/maps", "yelp.com", "expedia.com"],
        search_depth="quick",
        query_style="specific_targeted",
        keywords=["travel", "hotel", "flight", "restaurant", "vacation", "booking", "tourist", "attraction", "nearby", "review", "trip"],
        priority=7,
    ),
    "entertainment_guide": SearchProfile(
        key="entertainment_guide",
        name="Entertainment Guide",
        expertise="entertainment",
        description="Finds information about movies, TV shows, music, gaming, celebrities, and streaming content from entertainment databases.",
        preferred_sources=["imdb.com", "rottentomatoes.com", "spotify.com", "steam.com", "metacritic.com"],
        search_depth="quick",
        query_style="factual_direct",
        keywords=["movie", "film", "tv show", "series", "music", "song", "album", "game", "gaming", "actor", "celebrity", "streaming", "netflix", "spotify"],
        priority=6,
    ),
    "food_critic": SearchProfile(
        key="food_critic",
        name="Food Critic",
        expertise="food_dining",
        description="Finds recipes, restaurant reviews, food critiques, cooking tips, and dining recommendations from culinary sources.",
        preferred_sources=["allrecipes.com", "yelp.com", "zomato.com", "foodnetwork.com", "epicurious.com"],
        search_depth="medium",
        query_style="specific_targeted",
        keywords=["recipe", "food", "restaurant", "cooking", "cuisine", "meal", "dish", "ingredient", "dining", "chef", "bake"],
        priority=5,
    ),
    "education_hunter": SearchProfile(
        key="education_hunter",
        name="Education Hunter",
        expertise="education_learning",
        description="Finds online courses, tutorials, university programs, certifications, and learning resources from educational platforms.",
        preferred_sources=["coursera.org", "udemy.com", "edx.org", "khanacademy.org", "mit.edu", "stanford.edu"],
        search_depth="medium",
        query_style="exploratory_detailed",
        keywords=["course", "tutorial", "learn", "education", "university", "degree", "certification", "training", "class", "lesson", "study"],
        priority=6,
    ),
    "job_scout": SearchProfile(
        key="job_scout",
        name="Job Scout",
        expertise="jobs_career",
        description="Finds job listings, salary information, career advice, company reviews, and employment opportunities from job boards.",
        preferred_sources=["linkedin.com", "indeed.com", "glassdoor.com", "monster.com", "ziprecruiter.com"],
        search_depth="quick",
        query_style="specific_targeted",
        keywords=["job", "career", "hiring", "salary", "position", "employment", "recruitment", "resume", "interview", "work", "freelance"],
        priority=8,
    ),
    "science_explorer": SearchProfile(
        key="science_explorer",
        name="Science Explorer",
        expertise="science_research",
        description="Finds scientific research papers, discoveries, experimental results, and academic studies from leading science journals and repositories.",
        preferred_sources=["nature.com", "science.org", "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "sciencedaily.com"],
        search_depth="thorough",
        query_style="exploratory_detailed",
        keywords=["science", "research", "study", "experiment", "discovery", "physics", "chemistry", "biology", "astronomy", "scientist"],
        priority=5,
    ),
    "environment_watch": SearchProfile(
        key="environment_watch",
        name="Environment Watch",
        expertise="environment_sustainability",
        description="Tracks climate data, environmental news, sustainability practices, and conservation efforts from authoritative environmental sources.",
        preferred_sources=["epa.gov", "unep.org", "climate.gov", "nasa.gov", "noaa.gov"],
        search_depth="medium",
        query_style="factual_direct",
        keywords=["climate", "environment", "sustainability", "carbon", "pollution", "renewable", "ecosystem", "green", "recycle", "conservation"],
        priority=4,
    ),
    "sports_analyst": SearchProfile(
        key="sports_analyst",
        name="Sports Analyst",
        expertise="sports_athletics",
        description="Finds sports scores, match results, player statistics, team standings, and sports news from major sports networks.",
        preferred_sources=["espn.com", "sports.yahoo.com", "bbc.com/sport", "skysports.com", "bleacherreport.com"],
        search_depth="quick",
        query_style="factual_direct",
        keywords=["sports", "score", "game", "match", "player", "team", "nba", "nfl", "football", "cricket", "tennis", "fifa", "olympics"],
        priority=7,
    ),
    "auto_expert": SearchProfile(
        key="auto_expert",
        name="Auto Expert",
        expertise="automotive",
        description="Finds car reviews, vehicle comparisons, automotive news, pricing, and technical specs from automotive publications.",
        preferred_sources=["edmunds.com", "kbb.com", "caranddriver.com", "motortrend.com", "autotrader.com"],
        search_depth="medium",
        query_style="specific_targeted",
        keywords=["car", "vehicle", "automotive", "drive", "engine", "electric vehicle", "ev", "hybrid", "sedan", "suv", "mileage", "dealership"],
        priority=5,
    ),
    "real_estate_scout": SearchProfile(
        key="real_estate_scout",
        name="Real Estate Scout",
        expertise="real_estate",
        description="Finds property listings, housing prices, mortgage rates, rental information, and real estate market trends.",
        preferred_sources=["zillow.com", "realtor.com", "redfin.com", "trulia.com", "housing.com"],
        search_depth="quick",
        query_style="specific_targeted",
        keywords=["house", "apartment", "property", "real estate", "rent", "mortgage", "home", "condo", "landlord", "tenant", "housing"],
        priority=6,
    ),
    "ai_watcher": SearchProfile(
        key="ai_watcher",
        name="AI Watcher",
        expertise="ai_machine_learning",
        description="Tracks AI and machine learning developments, new model releases, research papers, and industry trends from AI-focused sources.",
        preferred_sources=["arxiv.org", "openai.com", "deepmind.google", "huggingface.co", "paperswithcode.com"],
        search_depth="thorough",
        query_style="technical_precise",
        keywords=["ai", "artificial intelligence", "machine learning", "deep learning", "neural network", "llm", "gpt", "transformer", "model", "chatbot", "diffusion"],
        priority=8,
    ),
}


def get_profile(key: str) -> Optional[SearchProfile]:
    """Get a search profile by key."""
    return SEARCH_PROFILES.get(key)


def get_profiles_for_query(query: str) -> list[SearchProfile]:
    """Get matching profiles for a query based on keyword matching."""
    query_lower = query.lower()
    matched = []

    for profile in SEARCH_PROFILES.values():
        if profile.key == "generalist":
            continue
        for keyword in profile.keywords:
            if keyword in query_lower:
                matched.append(profile)
                break

    matched.sort(key=lambda p: p.priority, reverse=True)

    if not matched:
        matched.append(SEARCH_PROFILES["generalist"])

    return matched


def get_all_profile_keys() -> list[str]:
    """Get all available profile keys."""
    return list(SEARCH_PROFILES.keys())


class AgentProfiles:
    """Convenience wrapper for accessing search agent profiles."""

    def get_profile(self, key: str) -> Optional[dict]:
        """Get a profile as a dict by key. Returns None if not found."""
        profile = SEARCH_PROFILES.get(key)
        if profile is None:
            return None
        return {
            "key": profile.key,
            "name": profile.name,
            "expertise": profile.expertise,
            "description": profile.description,
            "preferred_sources": profile.preferred_sources,
            "search_depth": profile.search_depth,
            "query_style": profile.query_style,
            "keywords": profile.keywords,
            "priority": profile.priority,
        }

    def list_profiles(self) -> list[str]:
        """List all available profile keys."""
        return get_all_profile_keys()

    def get_profiles_for_query(self, query: str) -> list[dict]:
        """Get matching profiles for a query, returned as dicts."""
        profiles = get_profiles_for_query(query)
        return [self.get_profile(p.key) for p in profiles if self.get_profile(p.key) is not None]
