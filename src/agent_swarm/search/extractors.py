"""Content extraction utilities for search results."""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """Extracted and processed content from a web page."""
    title: str
    url: str
    text: str
    word_count: int
    language: str = "en"
    quality_score: float = 0.5


class ContentExtractor:
    """Utility class for extracting and processing web content."""

    NOISE_PATTERNS = [
        r"cookie\s+policy",
        r"accept\s+cookies",
        r"subscribe\s+to\s+our",
        r"sign\s+up\s+for",
        r"advertisement",
        r"ad\s+choices",
        r"privacy\s+policy",
        r"terms\s+of\s+service",
        r"click\s+here\s+to",
        r"enable\s+javascript",
        r"please\s+disable\s+ad\s*blocker",
    ]

    def __init__(self, max_content_length: int = 5000):
        self.max_content_length = max_content_length
        self._noise_regex = re.compile("|".join(self.NOISE_PATTERNS), re.IGNORECASE)

    def clean_content(self, raw_text: str) -> str:
        """Clean extracted content by removing noise and normalizing."""
        if not raw_text:
            return ""
        text = re.sub(r"<[^>]+>", "", raw_text)
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            line = re.sub(r"\s+", " ", line).strip()
            if not line or len(line) < 10:
                continue
            if self._noise_regex.search(line):
                continue
            clean_lines.append(line)
        text = "\n".join(clean_lines)
        if len(text) > self.max_content_length:
            text = text[:self.max_content_length] + "..."
        return text

    def calculate_quality_score(self, text: str, query: str) -> float:
        """Calculate a quality score for extracted content."""
        if not text:
            return 0.0
        score = 0.5
        word_count = len(text.split())
        if word_count >= 100:
            score += 0.1
        if word_count >= 300:
            score += 0.1
        if word_count >= 500:
            score += 0.05
        if query:
            query_words = set(query.lower().split())
            text_words = set(text.lower().split())
            overlap = len(query_words & text_words)
            if overlap > 0:
                score += min(0.2, overlap * 0.05)
        noise_matches = len(self._noise_regex.findall(text))
        if noise_matches > 5:
            score -= 0.1
        return max(0.0, min(1.0, score))

    def extract_key_sentences(self, text: str, query: str, max_sentences: int = 5) -> list[str]:
        """Extract the most relevant sentences from content."""
        if not text or not query:
            return []
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        query_words = set(query.lower().split())
        scored = []
        for sentence in sentences:
            sent_words = set(sentence.lower().split())
            overlap = len(query_words & sent_words)
            scored.append((overlap, sentence))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:max_sentences]]
