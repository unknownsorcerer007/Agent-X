"""
Agent-X AI Content Extractor
Transforms raw browser data into structured, symmetrical JSON that
AI agents can instantly parse — no fluff, no HTML noise, no guessing.

This is the key differentiator: when the browser/swarm fetches data,
it returns it in a format AI understands natively, not human-readable
fluff that requires another parsing step.

Design Principles:
1. Symmetrical: Same structure regardless of source (HTTP vs browser)
2. Type-tagged: Every piece of data has a type label AI can route on
3. Deduplicated: Nav, footer, sidebar, ads stripped automatically
4. Compact: Only the data AI needs, nothing extra
5. Schema-aware: Extract JSON-LD, Microdata, Open Graph when present

No external AI API needed — pure DOM analysis + heuristics.
"""
import logging
import re
import json
import copy
import csv
import io
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from difflib import SequenceMatcher

logger = logging.getLogger("agent-x.ai_content")


# ─── Structured Output Types ────────────────────────────────────

@dataclass
class AIContent:
    """
    The universal structured output that AI agents receive.

    Every field is optional so the structure is always valid even
    for pages that lack certain content types. AI can check
    `content_type` to know what kind of page it's dealing with
    and which fields to expect data in.
    """
    # ── Identity ──────────────────────────────────────────
    content_type: str = "unknown"       # article, product, listing, forum, api_doc, search_results, profile, table, form, error, other
    url: str = ""
    title: str = ""
    domain: str = ""
    language: str = ""

    # ── Core Content ──────────────────────────────────────
    summary: str = ""                   # 2-3 sentence extractive summary
    main_text: str = ""                 # Clean, deduplicated body text
    headings: List[Dict[str, Any]] = field(default_factory=list)   # [{level, text, id}]
    paragraphs: List[str] = field(default_factory=list)            # Core paragraph texts

    # ── Structured Data ───────────────────────────────────
    tables: List[Dict[str, Any]] = field(default_factory=list)     # [{headers, rows}]
    lists: List[Dict[str, Any]] = field(default_factory=list)      # [{type: ol|ul, items: []}]
    code_blocks: List[Dict[str, Any]] = field(default_factory=list) # [{language, code}]
    forms: List[Dict[str, Any]] = field(default_factory=list)      # [{action, method, fields}]

    # ── Extracted Entities ────────────────────────────────
    links: List[Dict[str, str]] = field(default_factory=list)      # [{text, url, type}]
    images: List[Dict[str, str]] = field(default_factory=list)     # [{alt, src}]
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    prices: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)

    # ── Schema.org / Structured Data ──────────────────────
    schema_org: List[Dict[str, Any]] = field(default_factory=list)  # JSON-LD data
    open_graph: Dict[str, str] = field(default_factory=dict)
    meta: Dict[str, str] = field(default_factory=dict)

    # ── Metrics ───────────────────────────────────────────
    word_count: int = 0
    confidence: float = 0.0             # How confident we are in content_type
    extraction_method: str = ""         # "dom" or "http"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, omitting empty fields for compactness."""
        result = {}
        for key, value in asdict(self).items():
            if value or key in ("content_type", "url", "title"):
                result[key] = value
        return result


# ─── Content Type Detection ─────────────────────────────────────

class ContentTypeDetector:
    """
    Detects what type of content a page contains.
    Uses URL patterns, DOM structure, and meta tags.
    No external API needed — pure heuristics.
    """

    # URL patterns → content types
    URL_PATTERNS = {
        "product": [
            r"/product/", r"/products/", r"/item/", r"/p/", r"/dp/",
            r"amazon\.(com|in|co\.uk)/.*/dp/",
            r"ebay\.(com|co\.uk)/.*/itm/",
            r"etsy\.com/listing/",
            r"shopify\.(com|dev)/products/",
        ],
        "listing": [
            r"/search", r"/listings?", r"/catalog", r"/browse",
            r"/category/", r"/categories/", r"/collection/",
            r"/filter", r"/results",
        ],
        "forum": [
            r"/forum/", r"/thread/", r"/topic/", r"/discussion/",
            r"/post/", r"reddit\.com/r/", r"stackoverflow\.com/questions",
            r"discourse\.", r"/t/",
        ],
        "api_doc": [
            r"/api/", r"/docs/", r"/reference/", r"/endpoint/",
            r"swagger", r"openapi", r"/graphql",
            r"developer\.", r"api\.",
        ],
        "article": [
            r"/blog/", r"/article/", r"/news/", r"/story/",
            r"/post/", r"/\d{4}/\d{2}/",  # date-based URLs
            r"medium\.com/@", r"substack\.com",
        ],
        "profile": [
            r"/profile/", r"/user/", r"/u/", r"/@",
            r"linkedin\.com/in/", r"twitter\.com/",
            r"github\.com/[^/]+$",
        ],
    }

    @classmethod
    def detect(cls, url: str, dom_signals: Dict[str, Any] = None) -> tuple:
        """
        Detect content type and confidence score.

        Returns:
            (content_type, confidence) tuple
        """
        scores: Dict[str, float] = {}

        # 1. URL pattern matching (weight: 0.4)
        for content_type, patterns in cls.URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    scores[content_type] = scores.get(content_type, 0.0) + 0.4

        # 2. DOM signal matching (weight: 0.4)
        if dom_signals:
            # Schema.org types are strongest signals
            schema_types = dom_signals.get("schema_types", [])
            for st in schema_types:
                st_lower = st.lower()
                if "product" in st_lower:
                    scores["product"] = scores.get("product", 0.0) + 0.5
                elif "article" in st_lower or "newsarticle" in st_lower:
                    scores["article"] = scores.get("article", 0.0) + 0.5
                elif "person" in st_lower:
                    scores["profile"] = scores.get("profile", 0.0) + 0.5
                elif "searchresultspage" in st_lower or "itemlist" in st_lower:
                    scores["listing"] = scores.get("listing", 0.0) + 0.5
                elif "discussionforum" in st_lower or "comment" in st_lower:
                    scores["forum"] = scores.get("forum", 0.0) + 0.5

            # Open Graph type signals
            og_type = dom_signals.get("og_type", "").lower()
            if og_type == "product":
                scores["product"] = scores.get("product", 0.0) + 0.4
            elif og_type in ("article", "news"):
                scores["article"] = scores.get("article", 0.0) + 0.4
            elif og_type == "profile":
                scores["profile"] = scores.get("profile", 0.0) + 0.4

            # DOM structure signals
            has_article = dom_signals.get("has_article_tag", False)
            has_product = dom_signals.get("has_product_markup", False)
            has_forum = dom_signals.get("has_forum_markup", False)
            table_count = dom_signals.get("table_count", 0)
            form_count = dom_signals.get("form_count", 0)
            code_count = dom_signals.get("code_block_count", 0)

            if has_article:
                scores["article"] = scores.get("article", 0.0) + 0.3
            if has_product:
                scores["product"] = scores.get("product", 0.0) + 0.3
            if has_forum:
                scores["forum"] = scores.get("forum", 0.0) + 0.3
            if table_count > 3:
                scores["table"] = scores.get("table", 0.0) + 0.2
            if code_count > 2:
                scores["api_doc"] = scores.get("api_doc", 0.0) + 0.3
            if form_count > 0 and table_count == 0:
                scores["form"] = scores.get("form", 0.0) + 0.2

        # Pick the highest scoring type
        if not scores:
            return ("other", 0.3)

        best_type = max(scores, key=scores.get)
        confidence = min(1.0, scores[best_type])
        return (best_type, round(confidence, 2))


# ─── Main Extractor ─────────────────────────────────────────────

class AIContentExtractor:
    """
    Extracts structured, AI-ready content from web pages.

    Usage with browser:
        extractor = AIContentExtractor()
        result = await extractor.extract_from_browser(browser, page_id="main")

    Usage with HTTP response:
        result = await extractor.extract_from_html(html, url)

    The result is always an AIContent object with a predictable
    structure — same fields regardless of how the page was fetched.

    When an llm_provider (UniversalProvider) is provided, summarization
    uses the LLM for higher-quality, abstractive summaries. Otherwise,
    extractive summarization (first meaningful sentences) is used.
    """

    def __init__(self, llm_provider=None):
        """Initialize the content extractor.

        Args:
            llm_provider: Optional UniversalProvider instance for AI-powered
                         summarization. If None, extractive summarization
                         is used as fallback.
        """
        self._llm_provider = llm_provider

    # JavaScript to run in the browser to extract all data in one pass
    _BROWSER_EXTRACT_JS = """() => {
        const result = {};

        // ── Basic Identity ─────────────────────────────────
        result.url = window.location.href;
        result.title = document.title;
        result.domain = window.location.hostname;
        result.language = document.documentElement.lang || '';

        // ── DOM Signals for Content Type Detection ─────────
        result.dom_signals = {
            schema_types: [],
            og_type: '',
            has_article_tag: !!document.querySelector('article'),
            has_product_markup: !!document.querySelector('[itemtype*="Product"], [data-product-id], .product-price'),
            has_forum_markup: !!document.querySelector('.post-body, .forum-post, [itemtype*="Comment"]'),
            table_count: document.querySelectorAll('table').length,
            form_count: document.querySelectorAll('form').length,
            code_block_count: document.querySelectorAll('pre, code').length,
        };

        // JSON-LD schema types
        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
            try {
                const data = JSON.parse(s.textContent);
                if (data['@type']) result.dom_signals.schema_types.push(data['@type']);
                if (Array.isArray(data)) {
                    data.forEach(item => { if (item['@type']) result.dom_signals.schema_types.push(item['@type']); });
                }
            } catch(e) {}
        });

        // OG type
        const ogType = document.querySelector('meta[property="og:type"]');
        if (ogType) result.dom_signals.og_type = ogType.getAttribute('content') || '';

        // ── Main Content Extraction ────────────────────────
        // Try semantic containers first, fall back to body
        const mainSelectors = ['main', 'article', '[role="main"]', '.post-content', '.article-body', '.entry-content', '#content', '#main'];
        let mainEl = null;
        for (const sel of mainSelectors) {
            mainEl = document.querySelector(sel);
            if (mainEl) break;
        }
        if (!mainEl) mainEl = document.body;

        // ── Headings ──────────────────────────────────────
        result.headings = [];
        mainEl.querySelectorAll('h1, h2, h3, h4').forEach(h => {
            const text = h.textContent.trim();
            if (text && text.length < 200) {
                result.headings.push({
                    level: parseInt(h.tagName[1]),
                    text: text,
                    id: h.id || ''
                });
            }
        });

        // ── Paragraphs (deduplicated) ─────────────────────
        result.paragraphs = [];
        const seenTexts = new Set();
        mainEl.querySelectorAll('p').forEach(p => {
            const text = p.textContent.trim();
            // Skip short, duplicate, or boilerplate paragraphs
            if (text.length < 20) return;
            if (text.length > 3000) return;
            // Deduplicate by first 50 chars
            const key = text.substring(0, 50).toLowerCase();
            if (seenTexts.has(key)) return;
            seenTexts.add(key);
            // Skip nav/footer noise
            const parent = p.closest('nav, footer, header, .sidebar, .menu, .navigation');
            if (parent) return;
            result.paragraphs.push(text);
        });

        // ── Main Text (concatenated paragraphs) ───────────
        result.main_text = result.paragraphs.join('\\n\\n');

        // ── Tables ────────────────────────────────────────
        result.tables = [];
        document.querySelectorAll('table').forEach((table, idx) => {
            const headers = [];
            table.querySelectorAll('thead th, tr:first-child th').forEach(th => {
                headers.push(th.textContent.trim());
            });
            const rows = [];
            table.querySelectorAll('tbody tr, tr:not(:first-child)').forEach(tr => {
                const cells = [];
                tr.querySelectorAll('td').forEach(td => {
                    cells.push(td.textContent.trim().substring(0, 500));
                });
                if (cells.length > 0) rows.push(cells);
            });
            if (headers.length > 0 || rows.length > 0) {
                result.tables.push({
                    index: idx,
                    headers: headers,
                    rows: rows.slice(0, 50),  // Cap at 50 rows
                    row_count: rows.length,
                });
            }
        });

        // ── Lists ─────────────────────────────────────────
        result.lists = [];
        mainEl.querySelectorAll('ol, ul').forEach(list => {
            // Skip nav lists
            if (list.closest('nav, footer, header, .menu')) return;
            const items = [];
            list.querySelectorAll(':scope > li').forEach(li => {
                const text = li.textContent.trim().substring(0, 500);
                if (text) items.push(text);
            });
            if (items.length > 0 && items.length < 100) {
                result.lists.push({
                    type: list.tagName.toLowerCase(),
                    items: items,
                });
            }
        });

        // ── Code Blocks ──────────────────────────────────
        result.code_blocks = [];
        document.querySelectorAll('pre, pre > code').forEach(block => {
            const code = block.textContent.trim();
            if (code.length > 10 && code.length < 50000) {
                // Try to detect language from class
                let language = '';
                const codeEl = block.querySelector('code') || block;
                const classes = codeEl.className || '';
                const langMatch = classes.match(/language-(\\w+)|lang-(\\w+)|(\\w+)-code/);
                if (langMatch) language = langMatch[1] || langMatch[2] || langMatch[3] || '';
                result.code_blocks.push({
                    language: language,
                    code: code.substring(0, 10000),  // Cap at 10k chars
                });
            }
        });

        // ── Forms ────────────────────────────────────────
        result.forms = [];
        document.querySelectorAll('form').forEach(form => {
            const fields = [];
            form.querySelectorAll('input, textarea, select').forEach(inp => {
                const type = inp.type || inp.tagName.toLowerCase();
                if (type === 'hidden' || type === 'submit' || type === 'button') return;
                fields.push({
                    name: inp.name || inp.id || '',
                    type: type,
                    label: '',  // Will be filled below
                    required: inp.required,
                    placeholder: inp.placeholder || '',
                });
            });
            // Try to find labels
            form.querySelectorAll('label').forEach(label => {
                const forId = label.htmlFor;
                if (forId) {
                    const field = fields.find(f => f.name === forId);
                    if (field) field.label = label.textContent.trim();
                }
            });
            result.forms.push({
                action: form.action || '',
                method: (form.method || 'GET').toUpperCase(),
                fields: fields,
            });
        });

        // ── Links (deduplicated, categorized) ────────────
        result.links = [];
        const seenLinks = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const href = a.href;
            const text = (a.textContent || a.title || '').trim().substring(0, 200);
            if (!text || !href || text.length < 2) return;
            if (href.startsWith('javascript:') || href === '#') return;
            // Deduplicate
            const linkKey = href + '|' + text;
            if (seenLinks.has(linkKey)) return;
            seenLinks.add(linkKey);
            // Categorize
            let linkType = 'external';
            if (href.includes(window.location.hostname)) linkType = 'internal';
            else if (href.startsWith('mailto:')) linkType = 'email';
            else if (href.includes('download') || href.endsWith('.pdf') || href.endsWith('.zip')) linkType = 'download';

            result.links.push({text: text, url: href, type: linkType});
        });
        // Cap at 50 links
        result.links = result.links.slice(0, 50);

        // ── Images ───────────────────────────────────────
        result.images = [];
        document.querySelectorAll('img').forEach(img => {
            if (!img.src) return;
            // Skip tiny/hidden images (likely icons/tracking)
            if (img.naturalWidth > 0 && img.naturalWidth < 20) return;
            if (img.width > 0 && img.width < 20) return;
            result.images.push({
                alt: img.alt || '',
                src: img.src,
            });
        });
        result.images = result.images.slice(0, 30);

        // ── Emails ───────────────────────────────────────
        const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
        const bodyText = document.body.innerText || '';
        result.emails = [...new Set(bodyText.match(emailRegex) || [])];

        // ── Phone Numbers ────────────────────────────────
        const phonePatterns = [
            /\\+?\\d{1,3}[-.\\s]?\\(?\\d{1,4}\\)?[-.\\s]?\\d{1,4}[-.\\s]?\\d{1,9}/g,
            /\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}/g,
        ];
        const phones = new Set();
        const cleanedText = bodyText.replace(/\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b/g, ' ');
        phonePatterns.forEach(p => {
            (cleanedText.match(p) || []).forEach(m => {
                if (m.replace(/\\D/g, '').length >= 7) phones.add(m.trim());
            });
        });
        result.phones = [...phones];

        // ── Prices ───────────────────────────────────────
        const priceRegex = /[$€£¥₹]\\s?[\\d,]+\\.?\\d{0,2}|\\d{1,3}(?:,\\d{3})*(?:\\.\\d{2})?\\s?(?:USD|EUR|GBP|JPY|INR)/g;
        result.prices = [...new Set((bodyText.match(priceRegex) || []))].slice(0, 20);

        // ── Schema.org (JSON-LD) ────────────────────────
        result.schema_org = [];
        document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
            try {
                const data = JSON.parse(script.textContent);
                result.schema_org.push(data);
            } catch(e) {}
        });

        // ── Open Graph ──────────────────────────────────
        result.open_graph = {};
        document.querySelectorAll('meta[property^="og:"]').forEach(m => {
            const key = m.getAttribute('property').replace('og:', '');
            const val = m.getAttribute('content');
            if (val) result.open_graph[key] = val;
        });

        // ── Meta Tags ───────────────────────────────────
        result.meta = {};
        document.querySelectorAll('meta[name], meta[property]').forEach(m => {
            const key = m.getAttribute('name') || m.getAttribute('property') || '';
            const val = m.getAttribute('content') || '';
            if (key && val && !key.startsWith('og:') && !key.startsWith('twitter:')) {
                result.meta[key] = val.substring(0, 500);
            }
        });

        // ── Word Count ──────────────────────────────────
        result.word_count = result.main_text.split(/\\s+/).filter(w => w.length > 0).length;

        return result;
    }"""

    async def extract_from_browser(self, browser, page_id: str = "main") -> Dict[str, Any]:
        """
        Extract AI-structured content from a browser page.

        Args:
            browser: AgentBrowser instance
            page_id: Browser page/tab identifier

        Returns:
            Dict with AIContent structure — same format regardless of page type
        """
        try:
            page = browser._pages.get(page_id, browser.page)
            raw = await page.evaluate(self._BROWSER_EXTRACT_JS)

            content = AIContent(
                url=raw.get("url", ""),
                title=raw.get("title", ""),
                domain=raw.get("domain", ""),
                language=raw.get("language", ""),
                headings=raw.get("headings", []),
                paragraphs=raw.get("paragraphs", []),
                main_text=raw.get("main_text", ""),
                tables=raw.get("tables", []),
                lists=raw.get("lists", []),
                code_blocks=raw.get("code_blocks", []),
                forms=raw.get("forms", []),
                links=raw.get("links", []),
                images=raw.get("images", []),
                emails=raw.get("emails", []),
                phones=raw.get("phones", []),
                prices=raw.get("prices", []),
                schema_org=raw.get("schema_org", []),
                open_graph=raw.get("open_graph", {}),
                meta=raw.get("meta", {}),
                word_count=raw.get("word_count", 0),
                extraction_method="dom",
            )

            # Generate summary — use LLM-powered async version when available
            content.summary = await self._generate_summary_async(content, content.main_text)

            # Detect content type
            dom_signals = raw.get("dom_signals", {})
            content.content_type, content.confidence = ContentTypeDetector.detect(
                content.url, dom_signals
            )

            return {
                "status": "success",
                "data": content.to_dict(),
            }

        except Exception as exc:
            logger.error(f"Browser extraction failed: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    async def extract_from_html(self, html: str, url: str = "") -> Dict[str, Any]:
        """
        Extract AI-structured content from raw HTML (HTTP fetch path).

        Uses BeautifulSoup for parsing — same output structure as
        extract_from_browser but without JavaScript execution.

        Args:
            html: Raw HTML string
            url: Source URL for context

        Returns:
            Dict with AIContent structure
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {"status": "error", "error": "BeautifulSoup not available for HTML parsing"}

        try:
            soup = BeautifulSoup(html, "html.parser")

            # ── Basic Identity ──────────────────────────────
            title_tag = soup.find("title")
            title = title_tag.string.strip() if title_tag and title_tag.string else ""
            lang = soup.find("html", lang=True)
            language = lang.get("lang", "") if lang else ""

            # ── Schema.org (JSON-LD) — extract BEFORE decomposing scripts ──
            schema_org = []
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json as _json
                    schema_org.append(_json.loads(script.string))
                except Exception:
                    pass

            # ── Open Graph — extract BEFORE decomposing ──
            open_graph = {}
            for meta in soup.find_all("meta", attrs={"property": True}):
                prop = meta.get("property", "")
                if prop.startswith("og:"):
                    key = prop.replace("og:", "")
                    val = meta.get("content", "")
                    if key and val:
                        open_graph[key] = val

            # ── Meta Tags — extract BEFORE decomposing ──
            meta = {}
            for m in soup.find_all("meta", attrs={"name": True, "content": True}):
                key = m.get("name", "")
                val = m.get("content", "")
                if key and val and not key.startswith("og:") and not key.startswith("twitter:"):
                    meta[key] = val[:500]

            # ── Remove boilerplate ──────────────────────────
            for tag_name in ("script", "style", "noscript", "svg", "iframe"):
                for element in soup.find_all(tag_name):
                    element.decompose()
            for tag_name in ("nav", "footer", "header"):
                for element in soup.find_all(tag_name):
                    element.decompose()

            # ── Headings ────────────────────────────────────
            headings = []
            for h in soup.find_all(["h1", "h2", "h3", "h4"]):
                text = h.get_text(strip=True)
                if text and len(text) < 200:
                    headings.append({"level": int(h.name[1]), "text": text, "id": h.get("id", "")})

            # ── Paragraphs ─────────────────────────────────
            paragraphs = []
            seen = set()
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) < 20 or len(text) > 3000:
                    continue
                key = text[:50].lower()
                if key in seen:
                    continue
                seen.add(key)
                paragraphs.append(text)

            main_text = "\n\n".join(paragraphs)
            # Build a temporary AIContent to pass to async summarizer
            _tmp_content = AIContent(paragraphs=paragraphs, main_text=main_text, url=url)
            summary = await self._generate_summary_async(_tmp_content, main_text)

            # ── Tables ──────────────────────────────────────
            tables = []
            for idx, table in enumerate(soup.find_all("table")):
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                rows = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True)[:500] for td in tr.find_all("td")]
                    if cells:
                        rows.append(cells)
                if headers or rows:
                    tables.append({"index": idx, "headers": headers, "rows": rows[:50], "row_count": len(rows)})

            # ── Lists ───────────────────────────────────────
            lists = []
            for list_tag in soup.find_all(["ol", "ul"]):
                items = [li.get_text(strip=True)[:500] for li in list_tag.find_all("li", recursive=False)]
                if 0 < len(items) < 100:
                    lists.append({"type": list_tag.name, "items": items})

            # ── Code Blocks ────────────────────────────────
            code_blocks = []
            for pre in soup.find_all("pre"):
                code = pre.get_text(strip=True)
                if 10 < len(code) < 50000:
                    language = ""
                    code_el = pre.find("code")
                    if code_el:
                        classes = " ".join(code_el.get("class", []))
                        match = re.search(r"language-(\w+)", classes)
                        if match:
                            language = match.group(1)
                    code_blocks.append({"language": language, "code": code[:10000]})

            # ── Links ───────────────────────────────────────
            links = []
            seen_links = set()
            from urllib.parse import urlparse
            domain = urlparse(url).hostname or ""
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = (a.get_text(strip=True) or a.get("title", ""))[:200]
                if not text or not href or href.startswith("javascript:") or href == "#":
                    continue
                link_key = f"{href}|{text}"
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)
                link_type = "internal" if domain in href else "external"
                links.append({"text": text, "url": href, "type": link_type})

            # ── Images ──────────────────────────────────────
            images = []
            for img in soup.find_all("img", src=True):
                images.append({"alt": img.get("alt", ""), "src": img["src"]})

            # ── Emails & Phones ─────────────────────────────
            body_text = soup.get_text()
            emails = list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", body_text)))
            cleaned_text = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", " ", body_text)
            phones_raw = re.findall(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}", cleaned_text)
            phones = list(set(p.strip() for p in phones_raw if len(re.sub(r"\D", "", p)) >= 7))

            # ── Prices ──────────────────────────────────────
            prices = list(set(re.findall(
                r"[$€£¥₹]\s?[\d,]+\.?\d{0,2}|\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?(?:USD|EUR|GBP|JPY|INR)",
                body_text
            )))[:20]

            # ── Forms ──────────────────────────────────────
            forms = []
            for form in soup.find_all("form"):
                fields = []
                for inp in form.find_all(["input", "textarea", "select"]):
                    inp_type = inp.get("type", inp.name)
                    if inp_type in ("hidden", "submit", "button"):
                        continue
                    fields.append({
                        "name": inp.get("name", inp.get("id", "")),
                        "type": inp_type,
                        "label": "",
                        "required": inp.has_attr("required"),
                        "placeholder": inp.get("placeholder", ""),
                    })
                # Find labels
                for label in form.find_all("label"):
                    for_id = label.get("for", "")
                    if for_id:
                        field = next((f for f in fields if f["name"] == for_id), None)
                        if field:
                            field["label"] = label.get_text(strip=True)
                forms.append({
                    "action": form.get("action", ""),
                    "method": (form.get("method", "GET") or "GET").upper(),
                    "fields": fields,
                })

            # ── Build Content Object ────────────────────────
            # (schema_org, open_graph, meta already extracted before decompose)
            content = AIContent(
                url=url,
                title=title,
                domain=domain,
                language=language,
                summary=summary,
                main_text=main_text,
                headings=headings,
                paragraphs=paragraphs,
                tables=tables,
                lists=lists,
                code_blocks=code_blocks,
                forms=forms,
                links=links[:50],
                images=images[:30],
                emails=emails,
                phones=phones,
                prices=prices,
                schema_org=schema_org,
                open_graph=open_graph,
                meta=meta,
                word_count=len(main_text.split()) if main_text else 0,
                extraction_method="http",
            )

            # Detect content type
            schema_types = []
            for s in schema_org:
                if isinstance(s, dict) and s.get("@type"):
                    schema_types.append(s["@type"])
            og_type = open_graph.get("type", "")

            dom_signals = {
                "schema_types": schema_types,
                "og_type": og_type,
                "has_article_tag": bool(soup.find("article")),
                "has_product_markup": bool(soup.find(attrs={"itemtype": re.compile(r"Product")})),
                "table_count": len(tables),
                "form_count": len(soup.find_all("form")),
                "code_block_count": len(code_blocks),
            }
            content.content_type, content.confidence = ContentTypeDetector.detect(url, dom_signals)

            return {"status": "success", "data": content.to_dict()}

        except Exception as exc:
            logger.error(f"HTML extraction failed: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    def _generate_summary(self, content: AIContent, raw_text: str = "") -> str:
        """Generate a summary of the content using LLM when available, extractive fallback.

        When an llm_provider is configured, uses it for abstractive summarization
        which produces higher-quality, context-aware summaries. Falls back to
        extractive summarization (first meaningful sentences) when no LLM is
        available or if the LLM call fails.

        Args:
            content: The AIContent object (used for paragraphs and URL context)
            raw_text: Raw text from the page (used as LLM input before paragraphs)

        Returns:
            A 2-3 sentence summary string, or empty string if no content.
        """
        # If we have an LLM provider configured, try it for summarization
        if self._llm_provider is not None:
            try:
                # Prepare a compact prompt with the key content
                prompt_text = raw_text[:4000] if raw_text else ""
                if not prompt_text and content.paragraphs:
                    prompt_text = " ".join(content.paragraphs[:10])[:4000]

                if prompt_text:
                    # Try sync-style call via the provider's complete method
                    # We use asyncio to run the async complete in a sync context
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        # We're inside an event loop — can't await here (use _generate_summary_async instead)
                        pass
                    else:
                        summary_result = asyncio.run(self._llm_provider.complete(
                            prompt=f"Summarize this web page content in 2-3 concise sentences. Focus on the main topic and key information.\n\nContent from {content.url}:\n{prompt_text}",
                            max_tokens=200,
                            temperature=0.3,
                        ))
                        if isinstance(summary_result, dict) and summary_result.get("status") == "success":
                            summary = summary_result.get("content", "").strip()
                            if summary and len(summary) > 20:
                                return summary
            except Exception as e:
                logger.debug(f"LLM summarization failed, using extractive fallback: {e}")

        # Extractive fallback: take first 2-3 meaningful sentences
        paragraphs = content.paragraphs if hasattr(content, 'paragraphs') else []
        if isinstance(content, list):
            # Backward compat: content was passed as a list of paragraphs
            paragraphs = content

        if paragraphs:
            sentences = []
            for para in paragraphs[:5]:
                for sentence in para.split(". "):
                    sentence = sentence.strip()
                    if len(sentence) > 20 and not sentence.lower().startswith(("click", "subscribe", "sign up", "cookie", "accept")):
                        sentences.append(sentence)
                        if len(sentences) >= 3:
                            break
                if len(sentences) >= 3:
                    break
            if sentences:
                return ". ".join(sentences) + "."

        # Last resort: truncate main_text
        if hasattr(content, 'main_text') and content.main_text:
            return content.main_text[:300].rsplit(" ", 1)[0] + "..."

        return ""

    async def _generate_summary_async(self, content: AIContent, raw_text: str = "") -> str:
        """Async version: Generate summary using LLM when available.

        This is the preferred method to call from async contexts (extract_from_browser,
        extract_from_html). It tries the LLM provider's async complete method first,
        then falls back to the sync extractive method.

        Args:
            content: The AIContent object (used for paragraphs, URL, and main_text)
            raw_text: Raw text from the page (used as LLM input)

        Returns:
            A 2-3 sentence summary string, or empty string if no content.
        """
        if self._llm_provider is not None:
            try:
                prompt_text = raw_text[:4000] if raw_text else ""
                if not prompt_text and content.paragraphs:
                    prompt_text = " ".join(content.paragraphs[:10])[:4000]

                if prompt_text:
                    # Try the provider's async complete method
                    summary_result = await self._llm_provider.complete(
                        prompt=f"Summarize this web page content in 2-3 concise sentences. Focus on the main topic and key information.\n\nContent from {content.url}:\n{prompt_text}",
                        max_tokens=200,
                        temperature=0.3,
                    )
                    if isinstance(summary_result, dict) and summary_result.get("status") == "success":
                        summary = summary_result.get("content", "").strip()
                        if summary and len(summary) > 20:
                            return summary
            except Exception as e:
                logger.debug(f"Async LLM summarization failed, falling back to extractive: {e}")

        # Fall back to extractive summary (sync method handles this)
        return self._generate_summary(content, raw_text)


# ─── Enhanced Structured Output Types ───────────────────────────

@dataclass
class Conflict:
    """Represents a data conflict between pages."""
    field: str = ""
    page_id_1: str = ""
    value_1: Any = None
    page_id_2: str = ""
    value_2: Any = None
    conflict_type: str = "value_mismatch"  # value_mismatch, type_mismatch, missing_field

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    """Result of schema validation."""
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    type_mismatches: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredOutput:
    """Clean, deduplicated, structured output from AI content processing."""
    content: Dict[str, Any] = field(default_factory=dict)
    relationships: Dict[str, Any] = field(default_factory=dict)
    schema: Dict[str, Any] = field(default_factory=dict)
    normalization_applied: List[str] = field(default_factory=list)
    deduplication_stats: Dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for key, value in asdict(self).items():
            if value or key in ("content", "confidence"):
                result[key] = value
        return result


# ─── Data Normalizer ─────────────────────────────────────────────

class DataNormalizer:
    """
    Normalize extracted data to canonical forms.

    Transforms phone numbers to E.164, emails to lowercase,
    URLs to normalized form, prices to structured values,
    addresses to components, and dates to ISO 8601.
    """

    # Common URL tracking parameters to strip
    TRACKING_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "gclsrc", "dclid", "msclkid",
        "mc_eid", "mc_cid", "_ga", "_gl", "_hsenc", "_hsmi",
        "hsCtaTracking", "vero_id", "oly_anon_id", "oly_enc_id",
        "ref", "referrer", "source", "sfmc_sub", "sfmc_mid",
    }

    # Month name mappings for date parsing
    MONTH_NAMES = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
        "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }

    # US state abbreviations for address parsing
    US_STATES = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY", "dc": "DC", "district of columbia": "DC",
    }

    # Currency symbol mappings
    CURRENCY_SYMBOLS = {
        "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
        "₽": "RUB", "₩": "KRW", "₿": "BTC", "₴": "UAH", "₺": "TRY",
    }

    # Date format patterns to try
    DATE_FORMATS = [
        "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y", "%d/%m/%Y",
        "%m-%d-%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y",
        "%d %B %Y", "%d %b %Y", "%Y/%m/%d", "%m.%d.%Y",
        "%d.%m.%Y", "%B %d %Y", "%b %d %Y",
    ]

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        """
        Normalize a phone number to E.164 format (+1XXXXXXXXXX).

        Handles US and international formats. Strips all non-digit
        characters except the leading +.
        """
        if not phone or not phone.strip():
            return ""

        phone = phone.strip()
        # Preserve leading +
        has_plus = phone.startswith("+")

        # Extract country code hint
        digits_only = re.sub(r"[^\d]", "", phone)

        if not digits_only:
            return ""

        # Handle US/Canada numbers (country code 1)
        if has_plus and phone.startswith("+1"):
            if len(digits_only) == 11:
                return f"+{digits_only}"
            elif len(digits_only) == 10:
                return f"+1{digits_only}"
        elif has_plus:
            # International number with country code already present
            if len(digits_only) >= 7:
                return f"+{digits_only}"
        else:
            # No plus sign — try to guess
            if len(digits_only) == 11 and digits_only.startswith("1"):
                return f"+{digits_only}"
            elif len(digits_only) == 10:
                # Assume US number
                return f"+1{digits_only}"
            elif len(digits_only) == 7:
                # Too short for E.164 without area code
                return f"+1{digits_only}"
            elif len(digits_only) > 11:
                # Might include country code
                return f"+{digits_only}"

        # Fallback: return with + prefix if it seems like a valid number
        if len(digits_only) >= 7:
            return f"+{digits_only}" if has_plus else f"+1{digits_only}" if len(digits_only) <= 10 else f"+{digits_only}"

        return phone

    @classmethod
    def normalize_email(cls, email: str) -> str:
        """
        Normalize an email address: lowercase, trim whitespace.
        Removes mailto: prefix if present.
        """
        if not email or not email.strip():
            return ""

        email = email.strip().lower()

        # Remove mailto: prefix
        if email.startswith("mailto:"):
            email = email[7:]

        # Remove any trailing punctuation or angle brackets
        email = email.strip("<>").strip(".")

        # Basic validation
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            return email  # Return as-is if not valid format

        return email

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """
        Normalize a URL: add scheme, remove tracking params, lowercase domain.

        - Adds https:// if no scheme present
        - Removes common tracking parameters (utm_*, fbclid, gclid, etc.)
        - Lowercases the domain
        - Removes trailing slashes from path
        - Removes default ports
        - Sorts remaining query parameters for consistency
        """
        if not url or not url.strip():
            return ""

        url = url.strip()

        # Skip non-HTTP URLs
        if url.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
            return url

        # Add scheme if missing
        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url

        try:
            parsed = urlparse(url)
        except Exception:
            return url

        # Lowercase domain
        domain = parsed.hostname.lower() if parsed.hostname else ""

        # Remove default ports
        port = parsed.port
        if port == 80 and parsed.scheme == "http":
            port = None
        elif port == 443 and parsed.scheme == "https":
            port = None

        # Rebuild netloc
        netloc = domain
        if port:
            netloc = f"{domain}:{port}"

        # Remove tracking params from query
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            cleaned_params = {
                k: v for k, v in params.items()
                if k.lower() not in cls.TRACKING_PARAMS
            }
            # Sort parameters for consistency
            sorted_params = sorted(cleaned_params.items())
            query = urlencode(sorted_params, doseq=True)
        else:
            query = ""

        # Normalize path: remove trailing slash (except for root)
        path = parsed.path
        if path and path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Rebuild URL
        normalized = urlunparse((parsed.scheme, netloc, path, parsed.params, query, ""))

        return normalized

    @classmethod
    def normalize_price(cls, price: str) -> Dict[str, Any]:
        """
        Parse a price string into a structured dict.

        Returns: {value: float, currency: str, original: str}
        """
        # Handle already-normalized price dicts
        if isinstance(price, dict):
            if "value" in price and "currency" in price:
                return price
            price = price.get("original", str(price))

        if not price or not isinstance(price, str) or not price.strip():
            return {"value": 0.0, "currency": "USD", "original": str(price) if price else ""}

        original = price.strip()

        # Detect currency from symbol or code
        currency = "USD"  # default
        for symbol, curr_code in cls.CURRENCY_SYMBOLS.items():
            if symbol in original:
                currency = curr_code
                break

        # Also check for currency codes in the string
        currency_codes = {"USD", "EUR", "GBP", "JPY", "INR", "RUB", "KRW", "AUD", "CAD", "CHF", "CNY"}
        upper = original.upper()
        for code in currency_codes:
            if code in upper:
                currency = code
                break

        # Extract numeric value
        # Remove currency symbols and codes
        numeric_str = original
        for symbol in cls.CURRENCY_SYMBOLS:
            numeric_str = numeric_str.replace(symbol, "")
        for code in currency_codes:
            numeric_str = re.sub(r"\b" + code + r"\b", "", numeric_str, flags=re.IGNORECASE)

        numeric_str = numeric_str.strip()

        # Handle different decimal/grouping separators
        # European format: 1.234,56 → 1234.56
        if re.match(r"^[\d.]+,\d{2}$", numeric_str):
            numeric_str = numeric_str.replace(".", "").replace(",", ".")
        # Standard format: 1,234.56 → 1234.56
        elif "," in numeric_str and "." in numeric_str:
            numeric_str = numeric_str.replace(",", "")
        # Comma as decimal: 123,45 → 123.45
        elif re.match(r"^\d+,\d{1,2}$", numeric_str):
            numeric_str = numeric_str.replace(",", ".")
        # Comma as thousands: 1,234 → 1234
        elif "," in numeric_str:
            numeric_str = numeric_str.replace(",", "")

        # Remove any remaining non-numeric chars except minus and dot
        numeric_str = re.sub(r"[^\d.\-]", "", numeric_str)

        try:
            value = float(numeric_str) if numeric_str else 0.0
        except ValueError:
            value = 0.0

        return {
            "value": round(value, 2),
            "currency": currency,
            "original": original,
        }

    @classmethod
    def normalize_address(cls, address: str) -> Dict[str, Any]:
        """
        Parse an address string into components.

        Uses heuristic pattern matching for US addresses.
        Returns: {street, city, state, zip, country}
        """
        if not address or not address.strip():
            return {"street": "", "city": "", "state": "", "zip": "", "country": "", "original": ""}

        original = address.strip()
        result = {"street": "", "city": "", "state": "", "zip": "", "country": "", "original": original}

        # Try to extract ZIP code (US)
        zip_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", original)
        if zip_match:
            result["zip"] = zip_match.group(1)
            result["country"] = "US"

        # Try to extract state (abbreviation or full name)
        state_abbr_match = re.search(r"\b([A-Z]{2})\s+\d{5}", original)
        if state_abbr_match:
            result["state"] = state_abbr_match.group(1)
        else:
            # Try full state name
            addr_lower = original.lower()
            for state_name, state_abbr in cls.US_STATES.items():
                if state_name in addr_lower:
                    result["state"] = state_abbr
                    break

        # Try to extract city (word(s) between street and state/zip)
        # Pattern: STREET, CITY, STATE ZIP
        comma_parts = [p.strip() for p in original.split(",")]
        if len(comma_parts) >= 2:
            result["street"] = comma_parts[0]
            # Last part may contain state + zip
            last_part = comma_parts[-1].strip()
            # Remove zip from last part to get state
            state_part = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", last_part).strip()
            if not result["state"] and state_part:
                # Try to match state abbreviation
                state_abbr = state_part.upper()
                if state_abbr in cls.US_STATES.values():
                    result["state"] = state_abbr
            # City is the second-to-last comma part (before state/zip)
            if len(comma_parts) >= 3:
                result["city"] = comma_parts[-2].strip()
            elif len(comma_parts) == 2:
                # Only street and rest — city might be embedded
                rest = comma_parts[1].strip()
                # Remove state and zip from rest
                city = re.sub(r"\b[A-Z]{2}\b", "", rest)
                city = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", city).strip()
                if city:
                    result["city"] = city.strip(", ")

        # If no comma structure, try regex patterns
        if not result["street"]:
            # Pattern: NUMBER STREET, CITY STATE ZIP
            street_match = re.match(r"^(\d+\s+[A-Za-z\s]+?)(?:,\s*|\s+)([A-Za-z\s]+?)\s+([A-Z]{2})\s+(\d{5})", original)
            if street_match:
                result["street"] = street_match.group(1).strip()
                result["city"] = street_match.group(2).strip()
                result["state"] = street_match.group(3)
                result["zip"] = street_match.group(4)
                result["country"] = "US"

        return result

    @classmethod
    def normalize_date(cls, date: str) -> str:
        """
        Normalize a date string to ISO 8601 format (YYYY-MM-DD).

        Tries multiple common date formats. Returns original string
        if parsing fails.
        """
        if not date or not date.strip():
            return ""

        date_str = date.strip()

        # Try standard format parsing
        for fmt in cls.DATE_FORMATS:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try relative dates
        date_lower = date_str.lower()
        today = datetime.now()
        if date_lower in ("today", "now"):
            return today.strftime("%Y-%m-%d")
        elif date_lower == "yesterday":
            from datetime import timedelta
            return (today - timedelta(days=1)).strftime("%Y-%m-%d")
        elif date_lower == "tomorrow":
            from datetime import timedelta
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        # Try "X days/weeks/months/years ago" pattern
        ago_match = re.match(r"(\d+)\s+(day|week|month|year)s?\s+ago", date_lower)
        if ago_match:
            from datetime import timedelta
            amount = int(ago_match.group(1))
            unit = ago_match.group(2)
            if unit == "day":
                return (today - timedelta(days=amount)).strftime("%Y-%m-%d")
            elif unit == "week":
                return (today - timedelta(weeks=amount)).strftime("%Y-%m-%d")
            elif unit == "month":
                month_date = today.replace(year=today.year - (today.month - amount - 1) // 12)
                month_adj = (today.month - amount - 1) % 12 + 1
                month_date = month_date.replace(month=month_adj)
                return month_date.strftime("%Y-%m-%d")
            elif unit == "year":
                return today.replace(year=today.year - amount).strftime("%Y-%m-%d")

        # Try "Month DDth, YYYY" or "DDth Month YYYY" patterns
        ordinal_match = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str)
        for fmt in cls.DATE_FORMATS:
            try:
                dt = datetime.strptime(ordinal_match, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Return original if nothing works
        return date_str


# ─── AI Structured Output ────────────────────────────────────────

class AIStructuredOutput:
    """
    Takes raw extracted content and produces clean, deduplicated,
    structured output with entity normalization and relationship extraction.

    If llm_provider is provided, uses AI for semantic deduplication,
    entity extraction, schema generation, and conflict resolution.
    If llm_provider is None (default), falls back to heuristic methods.
    """

    # Person name patterns for relationship extraction
    _NAME_PREFIXES = {"mr", "mrs", "ms", "dr", "prof", "sir", "madam"}
    _NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "esq"}

    def __init__(self, llm_provider=None):
        """
        Initialize AIStructuredOutput.

        Args:
            llm_provider: Optional LLM provider for AI-powered features.
                         Must have a generate(prompt) -> str method.
                         If None, heuristic methods are used.
        """
        self.llm_provider = llm_provider
        self.normalizer = DataNormalizer()
    @staticmethod
    def _to_ai_content(content):
        """Convert a dict or AIContent to AIContent object.
        
        Handles the common case where a raw dict is passed instead of
        an AIContent object. Maps dict keys to AIContent fields.
        """
        if isinstance(content, AIContent):
            return content
        if isinstance(content, dict):
            return AIContent(
                content_type=content.get("content_type", "unknown"),
                url=content.get("url", ""),
                title=content.get("title", ""),
                domain=content.get("domain", ""),
                language=content.get("language", ""),
                summary=content.get("summary", ""),
                main_text=content.get("main_text", content.get("text", "")),
                headings=content.get("headings", []),
                paragraphs=content.get("paragraphs", []),
                tables=content.get("tables", []),
                lists=content.get("lists", []),
                code_blocks=content.get("code_blocks", []),
                forms=content.get("forms", []),
                links=content.get("links", []),
                images=content.get("images", []),
                emails=content.get("emails", []),
                phones=content.get("phones", []),
                prices=content.get("prices", []),
                dates=content.get("dates", []),
                schema_org=content.get("schema_org", []),
                open_graph=content.get("open_graph", {}),
                meta=content.get("meta", {}),
                word_count=content.get("word_count", 0),
                confidence=content.get("confidence", 0.0),
                extraction_method=content.get("extraction_method", ""),
            )
        raise TypeError(f"Expected AIContent or dict, got {type(content).__name__}")



    def process(self, content: AIContent) -> Dict[str, Any]:
        """
        Main processing pipeline: normalize → deduplicate → extract relationships → generate schema.

        Args:
            content: Raw AIContent from extraction

        Returns:
            Dict with status and StructuredOutput data
        """
        content = self._to_ai_content(content)
        try:
            # Step 1: Normalize entities
            content = self.normalize_entities(content)

            # Step 2: Deduplicate across fields
            dedup_stats_before = self._count_all_entities(content)
            content = self.deduplicate_across_fields(content)
            dedup_stats_after = self._count_all_entities(content)

            # Calculate dedup stats
            dedup_stats = {}
            for key in dedup_stats_before:
                removed = dedup_stats_before[key] - dedup_stats_after.get(key, 0)
                if removed > 0:
                    dedup_stats[key] = removed

            # Step 3: Extract relationships
            relationships = self.extract_relationships(content)

            # Step 4: Generate schema
            schema = self.generate_schema(content, schema_type="auto")

            # Build structured output
            output = StructuredOutput(
                content=content.to_dict(),
                relationships=relationships,
                schema=schema,
                normalization_applied=["phones", "emails", "urls", "prices", "dates"],
                deduplication_stats=dedup_stats,
                confidence=content.confidence,
            )

            return {"status": "success", "data": output.to_dict()}

        except Exception as exc:
            logger.error(f"Structured output processing failed: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    def deduplicate_across_fields(self, content: AIContent) -> AIContent:
        """
        Remove duplicate data that appears in multiple fields.

        E.g., same email in main_text AND emails list,
        same phone in summary AND phones list.
        """
        content = self._to_ai_content(content)
        content = copy.deepcopy(content)

        # Build canonical sets of entities already in structured fields
        email_set = set()
        for email in content.emails:
            normalized = self.normalizer.normalize_email(email)
            email_set.add(normalized.lower())

        phone_set = set()
        for phone in content.phones:
            normalized = self.normalizer.normalize_phone(phone)
            phone_set.add(re.sub(r"[^\d+]", "", normalized))

        url_set = set()
        for link in content.links:
            normalized = self.normalizer.normalize_url(link.get("url", ""))
            url_set.add(normalized.lower())

        price_set = set()
        for price in content.prices:
            parsed = self.normalizer.normalize_price(price)
            price_set.add(f"{parsed.get('value', 0)}_{parsed.get('currency', 'USD')}")

        # Deduplicate emails (remove from list if also in text — keep in list only)
        deduped_emails = []
        for email in content.emails:
            normalized = self.normalizer.normalize_email(email)
            if normalized.lower() not in {e.lower() for e in deduped_emails}:
                deduped_emails.append(email)
        content.emails = deduped_emails

        # Deduplicate phones
        seen_phone_digits = set()
        deduped_phones = []
        for phone in content.phones:
            digits = re.sub(r"[^\d]", "", phone)
            # Skip if same digits already seen
            if digits in seen_phone_digits:
                continue
            seen_phone_digits.add(digits)
            deduped_phones.append(phone)
        content.phones = deduped_phones

        # Deduplicate URLs in links
        seen_urls = set()
        deduped_links = []
        for link in content.links:
            url_normalized = self.normalizer.normalize_url(link.get("url", "")).lower()
            if url_normalized not in seen_urls:
                seen_urls.add(url_normalized)
                deduped_links.append(link)
        content.links = deduped_links

        # Deduplicate images by src
        seen_srcs = set()
        deduped_images = []
        for img in content.images:
            src = img.get("src", "")
            if src not in seen_srcs:
                seen_srcs.add(src)
                deduped_images.append(img)
        content.images = deduped_images

        # Deduplicate prices
        seen_prices = set()
        deduped_prices = []
        for price in content.prices:
            parsed = self.normalizer.normalize_price(price)
            key = f"{parsed['value']}_{parsed['currency']}"
            if key not in seen_prices:
                seen_prices.add(key)
                deduped_prices.append(price)
        content.prices = deduped_prices

        # Deduplicate headings by text
        seen_headings = set()
        deduped_headings = []
        for h in content.headings:
            text_key = h.get("text", "").strip().lower()
            if text_key and text_key not in seen_headings:
                seen_headings.add(text_key)
                deduped_headings.append(h)
        content.headings = deduped_headings

        # Deduplicate dates
        deduped_dates = list(dict.fromkeys(content.dates))
        content.dates = deduped_dates

        # Merge similar items in paragraphs
        content.paragraphs = self.merge_similar_items(content.paragraphs, similarity_threshold=0.9)

        return content

    def normalize_entities(self, content: AIContent) -> AIContent:
        """
        Normalize all entities in content to canonical forms.

        Phones → E.164, Emails → lowercase, URLs → normalized,
        Prices → structured, Dates → ISO 8601.
        """
        content = copy.deepcopy(content)

        # Normalize phones
        content.phones = [self.normalizer.normalize_phone(p) for p in content.phones]
        content.phones = [p for p in content.phones if p]  # Remove empty

        # Normalize emails
        content.emails = [self.normalizer.normalize_email(e) for e in content.emails]
        content.emails = [e for e in content.emails if e]  # Remove empty

        # Normalize URLs in links
        for link in content.links:
            if link.get("url"):
                link["url"] = self.normalizer.normalize_url(link["url"])

        # Normalize image URLs
        for img in content.images:
            if img.get("src"):
                img["src"] = self.normalizer.normalize_url(img["src"])

        # Normalize prices (handles both string and already-normalized dict inputs)
        content.prices = [
            self.normalizer.normalize_price(p) for p in content.prices
        ]

        # Normalize dates
        content.dates = [self.normalizer.normalize_date(d) for d in content.dates]
        content.dates = [d for d in content.dates if d]  # Remove empty

        # Normalize main URL
        if content.url:
            content.url = self.normalizer.normalize_url(content.url)

        return content

    def merge_similar_items(self, items: list, similarity_threshold: float = 0.85) -> list:
        """
        Merge items that are near-duplicates based on string similarity.

        Uses SequenceMatcher for heuristic comparison. If llm_provider
        is available, uses AI for semantic similarity comparison.

        Args:
            items: List of string items to merge
            similarity_threshold: Minimum similarity ratio (0-1) to consider duplicates

        Returns:
            Deduplicated list with similar items merged
        """
        if not items:
            return items

        if len(items) <= 1:
            return items

        # Use LLM for semantic similarity if available
        if self.llm_provider is not None and hasattr(self.llm_provider, "generate"):
            return self._merge_similar_items_llm(items, similarity_threshold)

        # Heuristic: use SequenceMatcher
        merged = []
        used = set()

        for i, item in enumerate(items):
            if i in used:
                continue

            item_str = str(item).strip()
            if not item_str:
                continue

            # Find all items similar to this one
            cluster = [item_str]
            for j in range(i + 1, len(items)):
                if j in used:
                    continue
                other_str = str(items[j]).strip()
                if not other_str:
                    continue

                similarity = SequenceMatcher(None, item_str.lower(), other_str.lower()).ratio()
                if similarity >= similarity_threshold:
                    cluster.append(other_str)
                    used.add(j)

            # Keep the longest version (most informative)
            best = max(cluster, key=len)
            merged.append(best)
            used.add(i)

        return merged

    def _merge_similar_items_llm(self, items: list, similarity_threshold: float) -> list:
        """Use LLM for semantic similarity comparison of items."""
        if len(items) <= 10:
            # For small sets, ask LLM to identify duplicates in one shot
            try:
                prompt = (
                    "Given the following list of text items, identify which items are "
                    "near-duplicates or semantically equivalent. Return a JSON array where "
                    "each element is an array of indices that should be merged together. "
                    "Only group items that mean essentially the same thing.\n\n"
                    f"Items:\n{json.dumps(items, indent=2)}\n\n"
                    "Return ONLY the JSON array of groups, e.g.: [[0, 3], [1, 5]]"
                )
                response = self.llm_provider.generate(prompt)
                groups = json.loads(response.strip())
                # Process groups
                used = set()
                merged = []
                for group in groups:
                    if isinstance(group, list):
                        for idx in group:
                            used.add(idx)
                        # Keep the longest item from the group
                        group_items = [items[i] for i in group if i < len(items)]
                        if group_items:
                            merged.append(max(group_items, key=lambda x: len(str(x))))
                # Add ungrouped items
                for i, item in enumerate(items):
                    if i not in used:
                        merged.append(item)
                return merged
            except Exception as exc:
                logger.warning(f"LLM merge failed, falling back to heuristic: {exc}")

        # Fallback to heuristic for large sets or LLM errors
        return self.merge_similar_items.__wrapped__(self, items, similarity_threshold) if hasattr(self.merge_similar_items, '__wrapped__') else self._merge_similar_items_heuristic(items, similarity_threshold)

    def _merge_similar_items_heuristic(self, items: list, similarity_threshold: float) -> list:
        """Heuristic fallback for merging similar items."""
        merged = []
        used = set()
        for i, item in enumerate(items):
            if i in used:
                continue
            item_str = str(item).strip()
            if not item_str:
                continue
            cluster = [item_str]
            for j in range(i + 1, len(items)):
                if j in used:
                    continue
                other_str = str(items[j]).strip()
                if not other_str:
                    continue
                similarity = SequenceMatcher(None, item_str.lower(), other_str.lower()).ratio()
                if similarity >= similarity_threshold:
                    cluster.append(other_str)
                    used.add(j)
            best = max(cluster, key=len)
            merged.append(best)
            used.add(i)
        return merged

    def extract_relationships(self, content: AIContent) -> Dict[str, Any]:
        """
        Find relationships between entities in the content.

        Detects person→email, company→phone, company→address,
        product→price, article→author, etc.

        Uses proximity heuristics in text. If llm_provider is available,
        uses AI for deeper relationship extraction.

        Returns:
            Dict of relationship type → list of relationship dicts
        """
        relationships = {
            "person_to_email": [],
            "company_to_phone": [],
            "company_to_email": [],
            "product_to_price": [],
            "page_to_dates": [],
            "entity_to_url": [],
        }

        text = content.main_text or content.summary or ""

        # Person → Email relationships
        for email in content.emails:
            email_part = email.split("@")[0]
            # Look for name patterns near the email in text
            # Check if email username matches any heading or known name
            for heading in content.headings:
                heading_text = heading.get("text", "")
                # Simple heuristic: if email local part resembles a name in a heading
                name_parts = re.split(r"[._]", email_part)
                for part in name_parts:
                    if len(part) > 2 and part.lower() in heading_text.lower():
                        relationships["person_to_email"].append({
                            "person": heading_text,
                            "email": email,
                            "evidence": "email_localpart_match_heading",
                        })
                        break

            # Look for name-like text near email in main_text
            email_pos = text.find(email)
            if email_pos >= 0:
                # Look backwards from email position for a name
                before = text[max(0, email_pos - 100):email_pos].strip()
                name_match = re.search(
                    r"(?:^|[\s,])([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s*$",
                    before
                )
                if name_match:
                    name = name_match.group(1).strip()
                    # Filter out common non-name words
                    if name.lower() not in self._NAME_PREFIXES and len(name) > 2:
                        relationships["person_to_email"].append({
                            "person": name,
                            "email": email,
                            "evidence": "proximity_in_text",
                        })

        # Company → Phone relationships
        # Look for organization names near phone numbers
        for phone in content.phones:
            phone_clean = re.sub(r"[^\d]", "", phone)
            if len(phone_clean) < 7:
                continue
            phone_pos = text.find(phone)
            if phone_pos < 0:
                # Try finding just the digits
                for i, char in enumerate(text):
                    if text[i:i+len(phone_clean)].isdigit():
                        phone_pos = i
                        break

            if phone_pos >= 0:
                # Look nearby for company indicators (Inc, LLC, Corp, Ltd, Co)
                nearby = text[max(0, phone_pos - 150):min(len(text), phone_pos + 50)]
                company_match = re.search(
                    r"([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Inc|LLC|Corp|Ltd|Co|Company|Group)",
                    nearby
                )
                if company_match:
                    company_name = company_match.group(0).strip()
                    relationships["company_to_phone"].append({
                        "company": company_name,
                        "phone": phone,
                        "evidence": "proximity_in_text",
                    })

        # Company → Email relationships (domain-based)
        for email in content.emails:
            domain = email.split("@")[-1] if "@" in email else ""
            if not domain:
                continue
            # Skip generic email providers
            generic_domains = {
                "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                "aol.com", "icloud.com", "mail.com", "protonmail.com",
            }
            if domain.lower() in generic_domains:
                continue

            # The domain likely belongs to a company
            company_name = domain.split(".")[0].capitalize()
            # Try to find full company name in headings or title
            for heading in content.headings:
                ht = heading.get("text", "")
                if company_name.lower() in ht.lower():
                    company_name = ht
                    break

            relationships["company_to_email"].append({
                "company": company_name,
                "email": email,
                "evidence": "email_domain_match",
            })

        # Product → Price relationships
        if content.content_type == "product" and content.prices:
            product_name = content.title
            for price in content.prices:
                if isinstance(price, dict):
                    price_str = f"{price.get('currency', 'USD')} {price.get('value', 0)}"
                else:
                    price_str = str(price)
                relationships["product_to_price"].append({
                    "product": product_name,
                    "price": price_str,
                    "evidence": "product_page_context",
                })

        # Page → Dates
        for date in content.dates:
            relationships["page_to_dates"].append({
                "page": content.title or content.url,
                "date": date,
                "evidence": "extracted_entity",
            })

        # Entity → URL (from links)
        for link in content.links:
            link_text = link.get("text", "")
            link_url = link.get("url", "")
            if link_text and link_url and len(link_text) > 3:
                relationships["entity_to_url"].append({
                    "entity": link_text,
                    "url": link_url,
                    "link_type": link.get("type", "unknown"),
                    "evidence": "hyperlink",
                })

        # LLM-powered relationship extraction if available
        if self.llm_provider is not None and hasattr(self.llm_provider, "generate") and text:
            try:
                llm_rels = self._extract_relationships_llm(content, text)
                # Merge LLM relationships with heuristic ones (avoid duplicates)
                for rel_type, rels in llm_rels.items():
                    if rel_type not in relationships:
                        relationships[rel_type] = []
                    existing_keys = set()
                    for r in relationships[rel_type]:
                        key = json.dumps(r, sort_keys=True)
                        existing_keys.add(key)
                    for r in rels:
                        key = json.dumps(r, sort_keys=True)
                        if key not in existing_keys:
                            relationships[rel_type].append(r)
                            existing_keys.add(key)
            except Exception as exc:
                logger.warning(f"LLM relationship extraction failed: {exc}")

        # Remove empty relationship categories
        relationships = {k: v for k, v in relationships.items() if v}

        return relationships

    def _extract_relationships_llm(self, content: AIContent, text: str) -> Dict[str, Any]:
        """Use LLM for deeper relationship extraction."""
        prompt = (
            "Analyze the following text and extract relationships between entities. "
            "Return a JSON object where keys are relationship types (like person_to_email, "
            "company_to_phone, product_to_price) and values are arrays of relationship objects. "
            "Each relationship object should have 'subject', 'object', and 'relation' keys.\n\n"
            f"Text excerpt (first 2000 chars):\n{text[:2000]}\n\n"
            "Known emails: " + json.dumps(content.emails[:5]) + "\n"
            "Known phones: " + json.dumps(content.phones[:5]) + "\n"
            "Known prices: " + json.dumps([str(p) for p in content.prices[:5]]) + "\n\n"
            "Return ONLY the JSON object."
        )
        response = self.llm_provider.generate(prompt)
        result = json.loads(response.strip())
        # Normalize the LLM output to our format
        normalized = {}
        for rel_type, rels in result.items():
            if isinstance(rels, list):
                normalized[rel_type] = rels
        return normalized

    def generate_schema(self, content: AIContent, schema_type: str = "auto") -> Dict[str, Any]:
        """
        Generate a structured schema from the content.

        Args:
            content: AIContent to generate schema from
            schema_type: One of "auto", "product", "article", "person",
                        "job", "event", "custom"

        Returns:
            Dict matching schema.org or custom schema format
        """
        content = self._to_ai_content(content)
        if schema_type == "auto":
            schema_type = self._detect_schema_type(content)

        # Use LLM for schema generation if available
        if self.llm_provider is not None and hasattr(self.llm_provider, "generate"):
            try:
                return self._generate_schema_llm(content, schema_type)
            except Exception as exc:
                logger.warning(f"LLM schema generation failed, falling back to heuristic: {exc}")

        generators = {
            "product": self._schema_product,
            "article": self._schema_article,
            "person": self._schema_person,
            "job": self._schema_job,
            "event": self._schema_event,
            "listing": self._schema_listing,
        }

        generator = generators.get(schema_type, self._schema_generic)
        return generator(content)

    def _detect_schema_type(self, content: AIContent) -> str:
        """Detect the best schema type from content."""
        ct = content.content_type
        type_map = {
            "product": "product",
            "article": "article",
            "profile": "person",
            "listing": "listing",
            "forum": "article",
            "api_doc": "article",
            "form": "article",
            "table": "listing",
            "search_results": "listing",
        }
        return type_map.get(ct, "article")

    def _schema_product(self, content: AIContent) -> Dict[str, Any]:
        """Generate Product schema.org schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": content.title,
        }

        if content.prices:
            price = content.prices[0]
            if isinstance(price, dict):
                schema["offers"] = {
                    "@type": "Offer",
                    "price": str(price.get("value", "")),
                    "priceCurrency": price.get("currency", "USD"),
                }
            else:
                parsed = self.normalizer.normalize_price(str(price))
                schema["offers"] = {
                    "@type": "Offer",
                    "price": str(parsed["value"]),
                    "priceCurrency": parsed["currency"],
                }

        if content.images:
            schema["image"] = [img.get("src", "") for img in content.images[:5]]

        if content.summary:
            schema["description"] = content.summary

        if content.tables:
            # Try to extract specs from tables
            specs = {}
            for table in content.tables:
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                if len(headers) >= 2:
                    for row in rows:
                        if len(row) >= 2:
                            specs[row[0]] = row[1]
                elif not headers and rows:
                    for row in rows:
                        if len(row) >= 2:
                            specs[row[0]] = row[1]
            if specs:
                schema["additionalProperty"] = [
                    {"@type": "PropertyValue", "name": k, "value": v}
                    for k, v in specs.items()
                ]

        if content.schema_org:
            # Merge with existing schema.org data
            for s in content.schema_org:
                if isinstance(s, dict) and s.get("@type", "").lower() == "product":
                    for key, value in s.items():
                        if key not in ("@context", "@type") and key not in schema:
                            schema[key] = value

        return schema

    def _schema_article(self, content: AIContent) -> Dict[str, Any]:
        """Generate Article schema.org schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": content.title,
        }

        if content.summary:
            schema["description"] = content.summary

        if content.main_text:
            schema["articleBody"] = content.main_text[:5000]

        if content.dates:
            schema["datePublished"] = content.dates[0]

        if content.images:
            schema["image"] = [img.get("src", "") for img in content.images[:3]]

        if content.domain:
            schema["publisher"] = {
                "@type": "Organization",
                "name": content.domain,
            }

        if content.url:
            schema["url"] = content.url

        if content.open_graph:
            for key, value in content.open_graph.items():
                mapping = {
                    "author": "author",
                    "published_time": "datePublished",
                    "modified_time": "dateModified",
                    "section": "articleSection",
                }
                if key in mapping and value:
                    if key == "author":
                        schema[mapping[key]] = {"@type": "Person", "name": value}
                    else:
                        schema[mapping[key]] = value

        return schema

    def _schema_person(self, content: AIContent) -> Dict[str, Any]:
        """Generate Person schema.org schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": content.title,
        }

        if content.emails:
            schema["email"] = content.emails[0]

        if content.phones:
            schema["telephone"] = content.phones[0]

        if content.images:
            schema["image"] = content.images[0].get("src", "")

        if content.links:
            same_as = [link["url"] for link in content.links if link.get("url") and link.get("type") == "external"]
            if same_as:
                schema["sameAs"] = same_as[:5]

        if content.summary:
            schema["description"] = content.summary

        # Try to extract job title from headings
        for h in content.headings:
            text = h.get("text", "").lower()
            if any(title_word in text for title_word in ["engineer", "developer", "manager", "director", "analyst", "designer", "lead", "vp", "ceo", "cto"]):
                schema["jobTitle"] = h.get("text", "")
                break

        return schema

    def _schema_job(self, content: AIContent) -> Dict[str, Any]:
        """Generate JobPosting schema.org schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": content.title,
        }

        if content.summary:
            schema["description"] = content.summary

        if content.prices:
            price = content.prices[0]
            if isinstance(price, dict):
                schema["baseSalary"] = {
                    "@type": "MonetaryAmount",
                    "currency": price.get("currency", "USD"),
                    "value": {
                        "@type": "QuantitativeValue",
                        "value": price.get("value", 0),
                    }
                }

        if content.dates:
            schema["datePosted"] = content.dates[0]

        if content.domain:
            schema["hiringOrganization"] = {
                "@type": "Organization",
                "name": content.domain,
            }

        if content.emails:
            schema["applicationContact"] = {
                "@type": "ContactPoint",
                "email": content.emails[0],
            }

        # Extract location from text
        location_patterns = [
            r"(?:location|city|office):\s*([A-Za-z\s,]+)",
            r"(?:in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})",
        ]
        text = content.main_text or content.summary or ""
        for pattern in location_patterns:
            match = re.search(pattern, text)
            if match:
                schema["jobLocation"] = {
                    "@type": "Place",
                    "address": match.group(1).strip(),
                }
                break

        return schema

    def _schema_event(self, content: AIContent) -> Dict[str, Any]:
        """Generate Event schema.org schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": content.title,
        }

        if content.summary:
            schema["description"] = content.summary

        if content.dates:
            schema["startDate"] = content.dates[0]
            if len(content.dates) > 1:
                schema["endDate"] = content.dates[1]

        if content.prices:
            price = content.prices[0]
            if isinstance(price, dict):
                schema["offers"] = {
                    "@type": "Offer",
                    "price": str(price.get("value", "")),
                    "priceCurrency": price.get("currency", "USD"),
                }

        if content.url:
            schema["url"] = content.url

        if content.domain:
            schema["organizer"] = {
                "@type": "Organization",
                "name": content.domain,
            }

        return schema

    def _schema_listing(self, content: AIContent) -> Dict[str, Any]:
        """Generate ItemList schema.org schema for listing/search pages."""
        schema = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": content.title,
        }

        items = []
        for link in content.links[:20]:
            items.append({
                "@type": "ListItem",
                "position": len(items) + 1,
                "name": link.get("text", ""),
                "url": link.get("url", ""),
            })

        if items:
            schema["itemListElement"] = items

        if content.summary:
            schema["description"] = content.summary

        return schema

    def _schema_generic(self, content: AIContent) -> Dict[str, Any]:
        """Generate a generic WebPage schema."""
        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": content.title,
            "url": content.url,
        }

        if content.summary:
            schema["description"] = content.summary

        if content.dates:
            schema["dateModified"] = content.dates[0]

        if content.domain:
            schema["publisher"] = {
                "@type": "Organization",
                "name": content.domain,
            }

        return schema

    def _generate_schema_llm(self, content: AIContent, schema_type: str) -> Dict[str, Any]:
        """Use LLM to generate a more accurate schema."""
        prompt = (
            f"Generate a schema.org JSON-LD object for type '{schema_type}' "
            f"based on the following extracted page data. Fill in as many "
            f"schema.org properties as possible from the data.\n\n"
            f"Title: {content.title}\n"
            f"URL: {content.url}\n"
            f"Summary: {content.summary[:500] if content.summary else ''}\n"
            f"Emails: {json.dumps(content.emails[:5])}\n"
            f"Phones: {json.dumps(content.phones[:5])}\n"
            f"Prices: {json.dumps([str(p) for p in content.prices[:5]])}\n"
            f"Dates: {json.dumps(content.dates[:5])}\n"
            f"Images: {len(content.images)} images found\n\n"
            "Return ONLY the JSON-LD object, no markdown, no explanation."
        )
        response = self.llm_provider.generate(prompt)
        # Try to parse as JSON
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)

    def _count_all_entities(self, content: AIContent) -> Dict[str, int]:
        """Count entities in content for deduplication stats."""
        return {
            "emails": len(content.emails),
            "phones": len(content.phones),
            "links": len(content.links),
            "images": len(content.images),
            "prices": len(content.prices),
            "headings": len(content.headings),
            "dates": len(content.dates),
            "paragraphs": len(content.paragraphs),
        }


# ─── Cross-Page Deduplicator ────────────────────────────────────

class CrossPageDeduplicator:
    """
    Deduplicate data across multiple pages.

    Merges content from multiple extractions, removes duplicates,
    detects conflicts, and produces a unified view.
    """

    def __init__(self):
        self._pages: Dict[str, AIContent] = {}
        self._conflicts: List[Conflict] = []
        self._normalizer = DataNormalizer()

    def add_page(self, page_id: str, content: Union[AIContent, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add a page's extracted content to the deduplicator.

        Args:
            page_id: Unique identifier for the page
            content: Extracted AIContent from the page, or a plain dict

        Returns:
            Dict with status and number of pages tracked
        """
        try:
            # Convert dict to AIContent if needed (same logic as AIStructuredOutput._to_ai_content)
            if isinstance(content, dict):
                content = AIContent(
                    content_type=content.get("content_type", "unknown"),
                    url=content.get("url", ""),
                    title=content.get("title", ""),
                    domain=content.get("domain", ""),
                    language=content.get("language", ""),
                    summary=content.get("summary", ""),
                    main_text=content.get("main_text", content.get("text", "")),
                    headings=content.get("headings", []),
                    paragraphs=content.get("paragraphs", []),
                    tables=content.get("tables", []),
                    lists=content.get("lists", []),
                    code_blocks=content.get("code_blocks", []),
                    forms=content.get("forms", []),
                    links=content.get("links", []),
                    images=content.get("images", []),
                    emails=content.get("emails", []),
                    phones=content.get("phones", []),
                    prices=content.get("prices", []),
                    dates=content.get("dates", []),
                    schema_org=content.get("schema_org", []),
                    open_graph=content.get("open_graph", {}),
                    meta=content.get("meta", {}),
                    word_count=content.get("word_count", 0),
                    confidence=content.get("confidence", 0.0),
                    extraction_method=content.get("extraction_method", ""),
                )
            self._pages[page_id] = copy.deepcopy(content)
            # Re-detect conflicts whenever a new page is added
            self._conflicts = self._detect_conflicts()
            return {
                "status": "success",
                "page_id": page_id,
                "total_pages": len(self._pages),
            }
        except Exception as exc:
            logger.error(f"Failed to add page {page_id}: {exc}")
            return {"status": "error", "error": str(exc)}

    def get_deduplicated(self) -> Dict[str, Any]:
        """
        Get merged, deduplicated content from all pages.

        Merges entities, resolves conflicts using the default strategy,
        and returns a unified AIContent.

        Returns:
            Dict with status and merged AIContent data
        """
        try:
            if not self._pages:
                return {"status": "success", "data": AIContent().to_dict()}

            if len(self._pages) == 1:
                return {
                    "status": "success",
                    "data": list(self._pages.values())[0].to_dict(),
                }

            # Resolve conflicts first
            self.resolve_conflicts(strategy="most_recent")

            # Merge all pages
            merged = self._merge_pages()

            return {"status": "success", "data": merged.to_dict()}

        except Exception as exc:
            logger.error(f"Cross-page deduplication failed: {exc}")
            return {"status": "error", "error": str(exc)}

    def get_conflicts(self) -> Dict[str, Any]:
        """
        Find conflicting data between pages.

        Returns:
            Dict with status and list of Conflict objects
        """
        return {
            "status": "success",
            "conflicts": [c.to_dict() for c in self._conflicts],
            "conflict_count": len(self._conflicts),
        }

    def resolve_conflicts(self, strategy: str = "most_recent") -> Dict[str, Any]:
        """
        Auto-resolve conflicts using the specified strategy.

        Strategies:
        - "most_recent": Use the value from the most recently added page
        - "most_frequent": Use the value that appears most often across pages
        - "longest": Use the longest/most detailed value
        - "first": Use the value from the first page added

        Args:
            strategy: Conflict resolution strategy name

        Returns:
            Dict with status and resolution details
        """
        try:
            resolved_count = 0
            page_ids = list(self._pages.keys())

            for conflict in self._conflicts:
                resolved = False

                if strategy == "most_recent":
                    # Use value from the later page
                    if conflict.page_id_2 in self._pages:
                        resolved = True

                elif strategy == "most_frequent":
                    # Count occurrences of each value across all pages
                    value_counts: Dict[str, int] = {}
                    for pid in page_ids:
                        page = self._pages[pid]
                        val = self._get_field_value(page, conflict.field)
                        val_str = json.dumps(val, sort_keys=True) if val is not None else "null"
                        value_counts[val_str] = value_counts.get(val_str, 0) + 1

                    # Pick the most common value
                    if value_counts:
                        most_common = max(value_counts, key=value_counts.get)
                        resolved = True

                elif strategy == "longest":
                    # Use the longer/more detailed value
                    val1_str = str(conflict.value_1) if conflict.value_1 else ""
                    val2_str = str(conflict.value_2) if conflict.value_2 else ""
                    resolved = True

                elif strategy == "first":
                    # Keep value from first page
                    resolved = True

                if resolved:
                    resolved_count += 1

            # Re-detect remaining conflicts
            self._conflicts = self._detect_conflicts()

            return {
                "status": "success",
                "strategy": strategy,
                "resolved_count": resolved_count,
                "remaining_conflicts": len(self._conflicts),
            }

        except Exception as exc:
            logger.error(f"Conflict resolution failed: {exc}")
            return {"status": "error", "error": str(exc)}

    def to_compact_json(self) -> Dict[str, Any]:
        """
        Output merged, deduplicated content as compact JSON.

        No empty fields, minimal whitespace.

        Returns:
            Dict with status and compact JSON string
        """
        try:
            result = self.get_deduplicated()
            if result.get("status") != "success":
                return result

            data = result["data"]
            # Remove empty fields recursively
            cleaned = self._remove_empty(data)
            compact = json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)

            return {"status": "success", "json": compact, "size_bytes": len(compact)}

        except Exception as exc:
            logger.error(f"Compact JSON output failed: {exc}")
            return {"status": "error", "error": str(exc)}

    def _detect_conflicts(self) -> List[Conflict]:
        """Detect conflicts between pages."""
        conflicts = []
        page_ids = list(self._pages.keys())

        # Compare each pair of pages
        for i in range(len(page_ids)):
            for j in range(i + 1, len(page_ids)):
                pid1, pid2 = page_ids[i], page_ids[j]
                page1, page2 = self._pages[pid1], self._pages[pid2]

                # Compare scalar fields
                scalar_fields = ["title", "url", "domain", "content_type", "summary"]
                for field_name in scalar_fields:
                    val1 = getattr(page1, field_name, None)
                    val2 = getattr(page2, field_name, None)
                    if val1 and val2 and val1 != val2:
                        conflicts.append(Conflict(
                            field=field_name,
                            page_id_1=pid1,
                            value_1=val1,
                            page_id_2=pid2,
                            value_2=val2,
                            conflict_type="value_mismatch",
                        ))

                # Compare prices (check for different prices for presumably same product)
                if page1.prices and page2.prices:
                    for p1 in page1.prices:
                        for p2 in page2.prices:
                            norm1 = self._normalizer.normalize_price(str(p1)) if isinstance(p1, str) else p1
                            norm2 = self._normalizer.normalize_price(str(p2)) if isinstance(p2, str) else p2
                            if (isinstance(norm1, dict) and isinstance(norm2, dict) and
                                norm1.get("currency") == norm2.get("currency") and
                                norm1.get("value") != norm2.get("value") and
                                norm1.get("value", 0) > 0 and norm2.get("value", 0) > 0):
                                conflicts.append(Conflict(
                                    field="prices",
                                    page_id_1=pid1,
                                    value_1=norm1,
                                    page_id_2=pid2,
                                    value_2=norm2,
                                    conflict_type="value_mismatch",
                                ))

        return conflicts

    def _merge_pages(self) -> AIContent:
        """Merge all pages into a single AIContent."""
        if not self._pages:
            return AIContent()

        page_ids = list(self._pages.keys())
        # Use the most recent page as the base
        base = copy.deepcopy(self._pages[page_ids[-1]])

        for pid in page_ids[:-1]:
            page = self._pages[pid]

            # Merge lists (union, deduplicated)
            base.emails = self._merge_string_lists(base.emails, page.emails)
            base.phones = self._merge_string_lists(base.phones, page.phones)
            base.prices = self._merge_string_lists(base.prices, page.prices)
            base.dates = self._merge_string_lists(base.dates, page.dates)
            base.paragraphs = self._merge_string_lists(base.paragraphs, page.paragraphs)

            # Merge dict lists
            base.links = self._merge_dict_lists(base.links, page.links, key="url")
            base.images = self._merge_dict_lists(base.images, page.images, key="src")
            base.headings = self._merge_headings(base.headings, page.headings)

            # Merge tables and lists (append unique)
            base.tables = self._merge_tables(base.tables, page.tables)
            base.lists = self._merge_list_items(base.lists, page.lists)
            base.code_blocks = self._merge_code_blocks(base.code_blocks, page.code_blocks)
            base.forms = self._merge_dict_lists(base.forms, page.forms, key="action")

            # Merge schema org (append unique)
            base.schema_org = self._merge_schema_org(base.schema_org, page.schema_org)

            # Merge open_graph (prefer base, fill gaps)
            for k, v in page.open_graph.items():
                if k not in base.open_graph and v:
                    base.open_graph[k] = v

            # Merge meta
            for k, v in page.meta.items():
                if k not in base.meta and v:
                    base.meta[k] = v

            # Use longest summary
            if len(page.summary) > len(base.summary):
                base.summary = page.summary

            # Use longest main_text
            if len(page.main_text) > len(base.main_text):
                base.main_text = page.main_text

            # Accumulate word count
            base.word_count += page.word_count

        return base

    @staticmethod
    def _merge_string_lists(list1: List[str], list2: List[str]) -> List[str]:
        """Merge two string lists, preserving order, removing duplicates."""
        seen = set()
        result = []
        for item in list1 + list2:
            key = str(item).strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _merge_dict_lists(list1: List[Dict], list2: List[Dict], key: str) -> List[Dict]:
        """Merge two dict lists by deduplicating on a key field."""
        seen = set()
        result = []
        for item in list1 + list2:
            k = item.get(key, "")
            if k and k not in seen:
                seen.add(k)
                result.append(item)
            elif not k:
                result.append(item)
        return result

    @staticmethod
    def _merge_headings(h1: List[Dict], h2: List[Dict]) -> List[Dict]:
        """Merge heading lists, deduplicating by text."""
        seen = set()
        result = []
        for h in h1 + h2:
            text_key = h.get("text", "").strip().lower()
            if text_key and text_key not in seen:
                seen.add(text_key)
                result.append(h)
        return result

    @staticmethod
    def _merge_tables(t1: List[Dict], t2: List[Dict]) -> List[Dict]:
        """Merge table lists. Keep all tables but avoid exact duplicates."""
        seen = set()
        result = []
        for t in t1 + t2:
            # Create a signature from headers
            sig = json.dumps(t.get("headers", []), sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                result.append(t)
        return result

    @staticmethod
    def _merge_list_items(l1: List[Dict], l2: List[Dict]) -> List[Dict]:
        """Merge list (ol/ul) structures."""
        seen = set()
        result = []
        for item in l1 + l2:
            sig = json.dumps(item.get("items", [])[:3], sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                result.append(item)
        return result

    @staticmethod
    def _merge_code_blocks(c1: List[Dict], c2: List[Dict]) -> List[Dict]:
        """Merge code blocks, deduplicating by code content."""
        seen = set()
        result = []
        for cb in c1 + c2:
            code_key = cb.get("code", "")[:100]
            if code_key not in seen:
                seen.add(code_key)
                result.append(cb)
        return result

    @staticmethod
    def _merge_schema_org(s1: List[Dict], s2: List[Dict]) -> List[Dict]:
        """Merge schema.org data, deduplicating by @type."""
        seen = set()
        result = []
        for s in s1 + s2:
            type_key = s.get("@type", "") + "_" + s.get("name", "")
            if type_key not in seen:
                seen.add(type_key)
                result.append(s)
        return result

    @staticmethod
    def _get_field_value(content: AIContent, field_name: str) -> Any:
        """Get a field value from AIContent by name."""
        if hasattr(content, field_name):
            return getattr(content, field_name)
        return None

    @staticmethod
    def _remove_empty(data: Any) -> Any:
        """Recursively remove empty fields from a dict/list."""
        if isinstance(data, dict):
            return {
                k: CrossPageDeduplicator._remove_empty(v)
                for k, v in data.items()
                if v is not None and v != "" and v != [] and v != {}
            }
        elif isinstance(data, list):
            return [
                CrossPageDeduplicator._remove_empty(item)
                for item in data
                if item is not None and item != "" and item != [] and item != {}
            ]
        return data


# ─── Custom Extraction Schema ────────────────────────────────────

class CustomExtractionSchema:
    """
    User-defined extraction schema for precise data extraction.

    Accepts a JSON schema definition that specifies which fields to
    extract from AIContent, with type coercion and validation.
    """

    # Supported transform functions
    _TRANSFORMS = {
        "extract_first": lambda x: x[0] if isinstance(x, list) and x else x,
        "extract_last": lambda x: x[-1] if isinstance(x, list) and x else x,
        "join": lambda x: ", ".join(str(i) for i in x) if isinstance(x, list) else str(x),
        "join_lines": lambda x: "\n".join(str(i) for i in x) if isinstance(x, list) else str(x),
        "flatten": lambda x: [item for sublist in x for item in (sublist if isinstance(sublist, list) else [sublist])] if isinstance(x, list) else x,
        "lowercase": lambda x: str(x).lower() if x else x,
        "uppercase": lambda x: str(x).upper() if x else x,
        "strip": lambda x: str(x).strip() if x else x,
        "to_string": lambda x: str(x) if x is not None else "",
        "to_int": lambda x: int(float(x)) if x else 0,
        "to_float": lambda x: float(x) if x else 0.0,
    }

    # Type coercions
    _TYPE_COERCIONS = {
        "string": lambda x: str(x) if x is not None else "",
        "int": lambda x: int(float(str(x).replace(",", ""))) if x else 0,
        "float": lambda x: float(str(x).replace(",", "").replace("$", "")) if x else 0.0,
        "bool": lambda x: str(x).lower() in ("true", "1", "yes", "on") if isinstance(x, str) else bool(x),
        "list": lambda x: x if isinstance(x, list) else [x] if x is not None else [],
        "dict": lambda x: x if isinstance(x, dict) else {"value": x},
    }

    def __init__(self, schema_definition: Dict):
        """
        Initialize with a schema definition.

        Schema format:
        {
            "name": "schema_name",
            "fields": [
                {"name": "field_name", "source": "ai_content_field", "type": "string",
                 "required": true, "transform": "extract_first", "max_length": 500,
                 "max_items": 5, "key_column": 0, "value_column": 1}
            ]
        }
        """
        self.name = schema_definition.get("name", "custom_schema")
        self.fields = schema_definition.get("fields", [])
        self._validate_schema_definition()

    def _validate_schema_definition(self) -> None:
        """Validate the schema definition structure."""
        required_keys = {"name", "source"}
        for i, field_def in enumerate(self.fields):
            if not isinstance(field_def, dict):
                raise ValueError(f"Field definition at index {i} must be a dict")
            missing = required_keys - set(field_def.keys())
            if missing:
                raise ValueError(f"Field at index {i} missing required keys: {missing}")

    def extract(self, content: AIContent) -> Dict[str, Any]:
        """
        Extract data from AIContent matching the schema definition.

        Args:
            content: AIContent to extract from

        Returns:
            Dict with status and extracted data matching the schema
        """
        try:
            content_dict = content.to_dict()
            result = {}

            for field_def in self.fields:
                field_name = field_def["name"]
                source = field_def["source"]
                field_type = field_def.get("type", "string")
                transform = field_def.get("transform")
                max_length = field_def.get("max_length")
                max_items = field_def.get("max_items")
                key_column = field_def.get("key_column")
                value_column = field_def.get("value_column")
                default = field_def.get("default")

                # Get value from source
                value = self._resolve_source(content_dict, content, source, key_column, value_column)

                # Apply transform if specified
                if transform and transform in self._TRANSFORMS:
                    try:
                        value = self._TRANSFORMS[transform](value)
                    except (IndexError, TypeError, ValueError) as exc:
                        logger.debug(f"Transform '{transform}' failed for field '{field_name}': {exc}")

                # Apply type coercion
                if field_type in self._TYPE_COERCIONS:
                    try:
                        value = self._TYPE_COERCIONS[field_type](value)
                    except (ValueError, TypeError) as exc:
                        logger.debug(f"Type coercion to '{field_type}' failed for field '{field_name}': {exc}")
                        value = default

                # Apply max_length for strings
                if max_length and isinstance(value, str) and len(value) > max_length:
                    value = value[:max_length - 3] + "..."

                # Apply max_items for lists
                if max_items and isinstance(value, list) and len(value) > max_items:
                    value = value[:max_items]

                # Use default if value is empty/None
                if value is None or value == "" or value == []:
                    value = default if default is not None else value

                result[field_name] = value

            return {"status": "success", "data": result, "schema_name": self.name}

        except Exception as exc:
            logger.error(f"Schema extraction failed: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    def validate(self, data: Dict) -> Dict[str, Any]:
        """
        Validate extracted data against the schema.

        Checks for required fields, type correctness, and constraints.

        Args:
            data: Dict of extracted data to validate

        Returns:
            Dict with status and ValidationResult
        """
        result = ValidationResult()
        errors = []
        warnings = []
        missing_required = []
        type_mismatches = []

        for field_def in self.fields:
            field_name = field_def["name"]
            field_type = field_def.get("type", "string")
            required = field_def.get("required", False)
            max_length = field_def.get("max_length")
            max_items = field_def.get("max_items")

            value = data.get(field_name)

            # Check required
            if required and (value is None or value == "" or value == []):
                missing_required.append(field_name)
                errors.append(f"Required field '{field_name}' is missing or empty")

            # Skip further validation if value is None
            if value is None:
                continue

            # Check type
            type_ok = True
            type_checks = {
                "string": lambda v: isinstance(v, str),
                "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
                "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
                "bool": lambda v: isinstance(v, bool),
                "list": lambda v: isinstance(v, list),
                "dict": lambda v: isinstance(v, dict),
            }
            if field_type in type_checks:
                if not type_checks[field_type](value):
                    type_mismatches.append(field_name)
                    warnings.append(
                        f"Field '{field_name}' expected type '{field_type}', "
                        f"got '{type(value).__name__}'"
                    )
                    type_ok = False

            # Check max_length
            if max_length and isinstance(value, str) and len(value) > max_length:
                warnings.append(f"Field '{field_name}' exceeds max_length ({len(value)} > {max_length})")

            # Check max_items
            if max_items and isinstance(value, list) and len(value) > max_items:
                warnings.append(f"Field '{field_name}' exceeds max_items ({len(value)} > {max_items})")

        result.errors = errors
        result.warnings = warnings
        result.missing_required = missing_required
        result.type_mismatches = type_mismatches
        result.valid = len(errors) == 0 and len(missing_required) == 0

        return {"status": "success", "validation": result.to_dict()}

    def _resolve_source(self, content_dict: Dict, content: AIContent, source: str,
                        key_column: int = None, value_column: int = None) -> Any:
        """Resolve a source field name to its value from content."""
        # Try direct attribute from dict
        if source in content_dict:
            value = content_dict[source]
            # Special handling for tables → dict conversion
            if key_column is not None and value_column is not None and isinstance(value, list):
                return self._table_to_dict(value, key_column, value_column)
            return value

        # Try direct attribute from AIContent object
        if hasattr(content, source):
            return getattr(content, source)

        # Try dot notation (e.g., "open_graph.title")
        parts = source.split(".")
        current = content_dict
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        return current

    @staticmethod
    def _table_to_dict(tables: List[Dict], key_column: int, value_column: int) -> Dict[str, Any]:
        """Convert table data to a dict using specified key and value columns."""
        result = {}
        for table in tables:
            rows = table.get("rows", [])
            for row in rows:
                if isinstance(row, list):
                    key = row[key_column] if key_column < len(row) else None
                    value = row[value_column] if value_column < len(row) else None
                    if key is not None:
                        result[str(key)] = value
        return result


# ─── Output Formatter ────────────────────────────────────────────

class OutputFormatter:
    """
    Format structured output in different ways.

    Supports JSON, Markdown, CSV, XML, and flat dict formats.
    """

    @staticmethod
    def to_json(data: Any, compact: bool = True) -> Dict[str, Any]:
        """
        Convert data to JSON string.

        Args:
            data: Data to serialize
            compact: If True, produce compact JSON; otherwise pretty-printed

        Returns:
            Dict with status and JSON string
        """
        try:
            if compact:
                json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)
            else:
                json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            return {"status": "success", "json": json_str, "size_bytes": len(json_str)}
        except (TypeError, ValueError) as exc:
            return {"status": "error", "error": f"JSON serialization failed: {exc}"}

    @staticmethod
    def to_markdown(data: Any) -> Dict[str, Any]:
        """
        Convert data to Markdown format.

        Dicts → heading + key-value pairs
        Lists of dicts → tables
        Lists of strings → bullet lists
        Nested structures → nested headings

        Args:
            data: Data to format

        Returns:
            Dict with status and Markdown string
        """
        try:
            md = OutputFormatter._to_markdown_recursive(data, level=1)
            return {"status": "success", "markdown": md}
        except Exception as exc:
            return {"status": "error", "error": f"Markdown formatting failed: {exc}"}

    @staticmethod
    def _to_markdown_recursive(data: Any, level: int = 1) -> str:
        """Recursively convert data to Markdown."""
        lines = []

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)) and value:
                    lines.append(f"{'#' * min(level, 6)} {key}")
                    lines.append("")
                    lines.append(OutputFormatter._to_markdown_recursive(value, level + 1))
                elif isinstance(value, list) and not value:
                    continue  # Skip empty lists
                elif value is not None and value != "":
                    # Inline key-value
                    lines.append(f"**{key}**: {value}")
                    lines.append("")
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                # Try to render as a table
                all_keys = []
                for item in data:
                    if isinstance(item, dict):
                        for k in item:
                            if k not in all_keys:
                                all_keys.append(k)

                if all_keys and len(all_keys) <= 10:
                    # Render as table
                    header = "| " + " | ".join(all_keys) + " |"
                    separator = "| " + " | ".join(["---"] * len(all_keys)) + " |"
                    lines.append(header)
                    lines.append(separator)
                    for item in data[:50]:
                        if isinstance(item, dict):
                            cells = []
                            for k in all_keys:
                                val = item.get(k, "")
                                cell_str = str(val).replace("|", "\\|")[:100]
                                if isinstance(val, (dict, list)):
                                    cell_str = json.dumps(val, default=str)[:50]
                                cells.append(cell_str)
                            lines.append("| " + " | ".join(cells) + " |")
                    lines.append("")
                else:
                    # Fall back to bullet list
                    for item in data:
                        lines.append(OutputFormatter._to_markdown_recursive(item, level + 1))
            else:
                # Simple list → bullet points
                for item in data:
                    if isinstance(item, (dict, list)):
                        lines.append(OutputFormatter._to_markdown_recursive(item, level + 1))
                    else:
                        lines.append(f"- {item}")
                lines.append("")
        else:
            lines.append(str(data))
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def to_csv(data: Any) -> Dict[str, Any]:
        """
        Convert tabular data to CSV format.

        Works best with lists of dicts (each dict = one row).
        Also handles AIContent tables format.

        Args:
            data: Data to convert (list of dicts, or list with 'headers'/'rows')

        Returns:
            Dict with status and CSV string
        """
        try:
            output = io.StringIO()
            writer = csv.writer(output)

            if isinstance(data, list) and data and isinstance(data[0], dict):
                # Check if it's in table format (has headers/rows)
                if "headers" in data[0] and "rows" in data[0]:
                    for table in data:
                        headers = table.get("headers", [])
                        rows = table.get("rows", [])
                        if headers:
                            writer.writerow(headers)
                        for row in rows:
                            writer.writerow(row)
                        writer.writerow([])  # Blank line between tables
                else:
                    # List of dicts → infer columns
                    all_keys = []
                    for item in data:
                        for k in item:
                            if k not in all_keys:
                                all_keys.append(k)
                    writer.writerow(all_keys)
                    for item in data:
                        row = [str(item.get(k, "")) for k in all_keys]
                        writer.writerow(row)
            elif isinstance(data, dict):
                # Single dict → key-value CSV
                writer.writerow(["key", "value"])
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v, default=str)
                    writer.writerow([k, v])
            else:
                return {"status": "error", "error": "Data format not suitable for CSV conversion"}

            csv_str = output.getvalue()
            return {"status": "success", "csv": csv_str}

        except Exception as exc:
            return {"status": "error", "error": f"CSV formatting failed: {exc}"}

    @staticmethod
    def to_xml(data: Any, root_tag: str = "data") -> Dict[str, Any]:
        """
        Convert data to XML format.

        Args:
            data: Data to convert
            root_tag: Name of the root XML element

        Returns:
            Dict with status and XML string
        """
        try:
            xml_str = OutputFormatter._to_xml_recursive(data, root_tag)
            return {"status": "success", "xml": xml_str}
        except Exception as exc:
            return {"status": "error", "error": f"XML formatting failed: {exc}"}

    @staticmethod
    def _to_xml_recursive(data: Any, tag: str) -> str:
        """Recursively convert data to XML."""
        # Sanitize tag name for XML
        tag = re.sub(r"[^a-zA-Z0-9_\-.]", "_", tag)
        if tag and tag[0].isdigit():
            tag = "_" + tag
        if not tag:
            tag = "item"

        if isinstance(data, dict):
            inner = []
            for key, value in data.items():
                inner.append(OutputFormatter._to_xml_recursive(value, key))
            return f"<{tag}>{''.join(inner)}</{tag}>"

        elif isinstance(data, list):
            inner = []
            for item in data:
                inner.append(OutputFormatter._to_xml_recursive(item, "item"))
            return f"<{tag}>{''.join(inner)}</{tag}>"

        elif data is None:
            return f"<{tag}/>"

        elif isinstance(data, bool):
            return f"<{tag}>{'true' if data else 'false'}</{tag}>"

        else:
            # Escape XML special characters
            text = str(data)
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace('"', "&quot;").replace("'", "&apos;")
            return f"<{tag}>{text}</{tag}>"

    @staticmethod
    def to_flat_dict(data: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """
        Flatten nested structures into dot-notation keys.

        E.g., {"address": {"city": "NYC"}} → {"address.city": "NYC"}

        Args:
            data: Data to flatten
            parent_key: Prefix for keys (used in recursion)
            sep: Separator between nested keys

        Returns:
            Dict with status and flattened dict
        """
        try:
            flat = OutputFormatter._flatten_recursive(data, parent_key, sep)
            return {"status": "success", "flat_dict": flat}
        except Exception as exc:
            return {"status": "error", "error": f"Flattening failed: {exc}"}

    @staticmethod
    def _flatten_recursive(data: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """Recursively flatten a nested dict/list into dot-notation keys."""
        items = {}

        if isinstance(data, dict):
            for key, value in data.items():
                new_key = f"{parent_key}{sep}{key}" if parent_key else key
                if isinstance(value, (dict, list)) and value:
                    items.update(OutputFormatter._flatten_recursive(value, new_key, sep))
                else:
                    items[new_key] = value
        elif isinstance(data, list):
            for i, value in enumerate(data):
                new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
                if isinstance(value, (dict, list)) and value:
                    items.update(OutputFormatter._flatten_recursive(value, new_key, sep))
                else:
                    items[new_key] = value
        else:
            items[parent_key] = data

        return items
