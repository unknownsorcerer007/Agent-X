"""
Agent-OS Smart Element Finder
Finds elements by visible text, accessibility labels, placeholder, title, alt text.
No CSS selector needed — works like a human looking at the page.
"""
import asyncio
import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger("agent-os.smart_finder")


class SmartElementFinder:
    """
    Find elements by natural language description or visible text.
    Supports fuzzy matching, accessibility labels, and ranked results.
    """

    # Search strategies in priority order
    SEARCH_STRATEGIES = [
        "exact_text",           # Exact visible text match
        "aria_label",           # aria-label attribute
        "placeholder",          # input placeholder
        "title_attr",           # title attribute
        "alt_text",             # img alt text
        "link_text",            # anchor text
        "button_text",          # button text
        "label_text",           # label[for] text
        "fuzzy_text",           # Fuzzy match on visible text
        "partial_text",         # Partial/substring match
        "text_nearby",          # Text near the element
    ]

    def __init__(self, browser):
        self.browser = browser

    async def find(
        self,
        description: str,
        tag: str = None,
        timeout: int = 5000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Find an element by natural description.

        Args:
            description: What to find — e.g. "Sign In", "email", "Submit button"
            tag: Optional tag filter — e.g. "button", "input", "a"
            timeout: Max wait time in ms
            page_id: Which tab to search

        Returns:
            Dict with selector, element info, and confidence score
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        desc_lower = description.lower().strip()
        start_time = time.time()

        # Build JS search function
        js_search = self._build_search_js(desc_lower, tag)
        elapsed_ms = int((time.time() - start_time) * 1000)
        remaining_timeout = max(0, timeout - elapsed_ms)

        # Try immediate search first
        results = await page.evaluate(js_search)

        if results and len(results) > 0:
            best = self._rank_results(results, desc_lower)
            return {
                "status": "success",
                "found": True,
                "selector": best["selector"],
                "tag": best["tag"],
                "text": best["text"],
                "match_type": best["match_type"],
                "confidence": best["confidence"],
                "total_matches": len(results),
                "all_results": [
                    {
                        "selector": r["selector"],
                        "text": r["text"][:100],
                        "match_type": r["match_type"],
                        "confidence": r["confidence"],
                    }
                    for r in results[:10]
                ],
            }

        # If not found immediately, wait and retry
        if remaining_timeout > 0:
            retry_interval = min(500, remaining_timeout // 5)
            elapsed = 0
            while elapsed < remaining_timeout:
                await asyncio.sleep(retry_interval / 1000)
                elapsed += retry_interval
                results = await page.evaluate(js_search)
                if results:
                    best = self._rank_results(results, desc_lower)
                    return {
                        "status": "success",
                        "found": True,
                        "selector": best["selector"],
                        "tag": best["tag"],
                        "text": best["text"],
                        "match_type": best["match_type"],
                        "confidence": best["confidence"],
                        "total_matches": len(results),
                        "waited_ms": elapsed + elapsed_ms,
                    }

        return {
            "status": "error",
            "found": False,
            "error": f"Element not found: '{description}'",
            "suggestion": "Try a different description or check if the element is visible",
        }

    async def find_all(
        self,
        description: str,
        tag: str = None,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Find ALL matching elements, ranked by relevance."""
        page = self.browser._pages.get(page_id, self.browser.page)
        desc_lower = description.lower().strip()
        js_search = self._build_search_js(desc_lower, tag)
        results = await page.evaluate(js_search)

        if not results:
            return {"status": "success", "found": False, "elements": [], "count": 0}

        ranked = sorted(results, key=lambda r: r["confidence"], reverse=True)

        return {
            "status": "success",
            "found": True,
            "elements": [
                {
                    "selector": r["selector"],
                    "tag": r["tag"],
                    "text": r["text"][:200],
                    "match_type": r["match_type"],
                    "confidence": round(r["confidence"], 2),
                }
                for r in ranked[:20]
            ],
            "count": len(ranked),
        }

    async def click_text(
        self,
        text: str,
        tag: str = None,
        timeout: int = 5000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Find and click an element by its visible text."""
        result = await self.find(text, tag=tag, timeout=timeout, page_id=page_id)
        if not result.get("found"):
            return result

        selector = result["selector"]
        click_result = await self.browser.click(selector, page_id=page_id)
        click_result["finder"] = {
            "text": result["text"],
            "match_type": result["match_type"],
            "confidence": result["confidence"],
        }
        return click_result

    async def fill_text(
        self,
        label: str,
        value: str,
        timeout: int = 5000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Find an input by its label/placeholder and fill it."""
        result = await self.find(label, tag="input", timeout=timeout, page_id=page_id)
        if not result.get("found"):
            # Try broader search without tag filter
            result = await self.find(label, timeout=timeout, page_id=page_id)
            if not result.get("found"):
                return result

        selector = result["selector"]
        fill_result = await self.browser.fill_form({selector: value}, page_id=page_id)
        fill_result["finder"] = {
            "label": result["text"],
            "match_type": result["match_type"],
            "confidence": result["confidence"],
        }
        return fill_result

    def _build_search_js(self, description: str, tag_filter: str = None) -> str:
        """Build the JavaScript search function."""
        # Escape description for safe JS injection
        import json as _json
        safe_desc = _json.dumps(description)
        safe_tag = _json.dumps(tag_filter.lower()) if tag_filter else "null"

        tag_clause = ""
        if tag_filter:
            tag_clause = f"el.tagName.toLowerCase() === {safe_tag} &&"

        return f"""() => {{
            const desc = {safe_desc};
            const results = [];
            const seen = new Set();

            function makeSelector(el) {{
                if (el.id) return '#' + CSS.escape(el.id);
                if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';

                // Build path-based selector
                let path = [];
                let current = el;
                while (current && current !== document.body) {{
                    let seg = current.tagName.toLowerCase();
                    if (current.id) {{
                        path.unshift('#' + CSS.escape(current.id));
                        break;
                    }}
                    if (current.className && typeof current.className === 'string') {{
                        const cls = current.className.trim().split(/\\s+/)[0];
                        if (cls) seg += '.' + CSS.escape(cls);
                    }}
                    const parent = current.parentElement;
                    if (parent) {{
                        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
                        if (siblings.length > 1) {{
                            seg += ':nth-of-type(' + (siblings.indexOf(current) + 1) + ')';
                        }}
                    }}
                    path.unshift(seg);
                    current = parent;
                }}
                return path.join(' > ');
            }}

            function addResult(el, matchType, confidence) {{
                const sel = makeSelector(el);
                if (seen.has(sel)) return;
                seen.add(sel);

                const text = (el.innerText || el.textContent || '').trim().substring(0, 300);
                results.push({{
                    selector: sel,
                    tag: el.tagName.toLowerCase(),
                    text: text,
                    match_type: matchType,
                    confidence: confidence,
                }});
            }}

            function similarity(a, b) {{
                if (a === b) return 1.0;
                if (!a || !b) return 0;
                a = a.toLowerCase().trim();
                b = b.toLowerCase().trim();
                if (a === b) return 1.0;
                if (a.includes(b)) return 0.8;
                if (b.includes(a)) return 0.7;
                // Simple word overlap
                const wordsA = new Set(a.split(/\\s+/));
                const wordsB = new Set(b.split(/\\s+/));
                let overlap = 0;
                for (const w of wordsB) {{ if (wordsA.has(w)) overlap++; }}
                if (overlap > 0) return 0.3 + (overlap / Math.max(wordsA.size, wordsB.size)) * 0.4;
                return 0;
            }}

            const allElements = document.querySelectorAll('a, button, input, textarea, select, [aria-label], [role="button"], [placeholder], [title], [alt], [for], [onclick], [tabindex], label, h1, h2, h3, h4, img, [data-testid]');
            for (const el of allElements) {{
                if ({tag_clause} false) continue;
                // Skip truly hidden elements but allow elements with offsetParent === null
                // that are inside scrollable containers (lazy loaded content)
                const style = window.getComputedStyle(el);
                const isHidden = style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
                if (isHidden && el.style.position !== 'fixed') continue;

                const tag = el.tagName.toLowerCase();

                // 1. Exact visible text
                const visibleText = (el.innerText || '').trim();
                if (visibleText.toLowerCase() === desc) {{
                    addResult(el, 'exact_text', 1.0);
                    continue;
                }}

                // 2. Aria label
                const ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel && ariaLabel.toLowerCase().includes(desc)) {{
                    addResult(el, 'aria_label', 0.95);
                    continue;
                }}

                // 3. Placeholder
                const placeholder = el.getAttribute('placeholder');
                if (placeholder && placeholder.toLowerCase().includes(desc)) {{
                    addResult(el, 'placeholder', 0.9);
                    continue;
                }}

                // 4. Title
                const title = el.getAttribute('title');
                if (title && title.toLowerCase().includes(desc)) {{
                    addResult(el, 'title_attr', 0.85);
                    continue;
                }}

                // 5. Alt text (images)
                const alt = el.getAttribute('alt');
                if (alt && alt.toLowerCase().includes(desc)) {{
                    addResult(el, 'alt_text', 0.85);
                    continue;
                }}

                // 6. Link text
                if (tag === 'a') {{
                    const linkText = (el.innerText || '').trim();
                    if (linkText.toLowerCase().includes(desc)) {{
                        addResult(el, 'link_text', 0.8);
                        continue;
                    }}
                }}

                // 7. Button text
                if (tag === 'button' || (tag === 'input' && ['submit', 'button'].includes(el.type))) {{
                    const btnText = (el.innerText || el.value || '').trim();
                    if (btnText.toLowerCase().includes(desc)) {{
                        addResult(el, 'button_text', 0.85);
                        continue;
                    }}
                }}

                // 8. Label text (for inputs)
                if (tag === 'label' && el.htmlFor) {{
                    const labelText = (el.innerText || '').trim();
                    if (labelText.toLowerCase().includes(desc)) {{
                        const target = document.getElementById(el.htmlFor);
                        if (target) addResult(target, 'label_text', 0.9);
                        continue;
                    }}
                }}

                // 9. Fuzzy match
                if (visibleText.length > 0 && visibleText.length < 500) {{
                    const sim = similarity(visibleText, desc);
                    if (sim > 0.5) {{
                        addResult(el, 'fuzzy_text', sim * 0.7);
                    }}
                }}

                // 10. Partial text
                if (visibleText.toLowerCase().includes(desc) && visibleText.length < 500) {{
                    addResult(el, 'partial_text', 0.6);
                }}
            }}

            // 11. Check for text nodes near clickable elements
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walker.nextNode()) {{
                if (node.textContent.toLowerCase().includes(desc)) {{
                    const parent = node.parentElement;
                    if (parent) {{
                        const clickable = parent.closest('a, button, [role="button"], input, [onclick], [tabindex]');
                        if (clickable && !seen.has(makeSelector(clickable))) {{
                            addResult(clickable, 'text_nearby', 0.5);
                        }}
                    }}
                }}
            }}

            return results;
        }}"""

    def _rank_results(self, results: List[Dict], description: str) -> Dict:
        """Rank results by confidence and return the best match."""
        if not results:
            return None

        # Sort by confidence descending
        ranked = sorted(results, key=lambda r: r.get("confidence", 0), reverse=True)
        return ranked[0]
