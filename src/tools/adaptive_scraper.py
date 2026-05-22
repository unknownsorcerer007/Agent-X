"""
Agent-OS Adaptive Element Scraper
Element fingerprinting + adaptive relocation for resilient scraping.

When a website changes its DOM structure, traditional CSS/XPath selectors break.
This module stores element fingerprints (tag, attributes, text, path, parent context)
in SQLite, and when a selector fails, uses similarity scoring to relocate the element
even if the page structure has changed.

Based on the adaptive scraping algorithm from Scrapling (BSD-3, Karim Shoair).
See THIRD_PARTY_LICENSES.md for attribution.
"""

import logging
import copy
import json
import time
from hashlib import sha256
from difflib import SequenceMatcher
from sqlite3 import connect as db_connect
from threading import RLock
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.adaptive-scraper")

# Default storage path
_DEFAULT_DB = str(Path.home() / ".agent-os" / "adaptive_elements.db")


# ═══════════════════════════════════════════════════════════════
# ELEMENT FINGERPRINT — Captures an element's unique identity
# ═══════════════════════════════════════════════════════════════

def element_to_fingerprint(element_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert element properties to a fingerprint dict for storage and comparison.

    Extracts: tag, attributes, text, DOM path, parent info, siblings, children.
    This fingerprint is the "identity" of an element that survives page changes.

    Args:
        element_data: Dict with keys: tag, attributes, text, parent, siblings, children, path

    Returns:
        Cleaned fingerprint dict suitable for similarity comparison.
    """
    result = {
        "tag": element_data.get("tag", ""),
        "attributes": {
            k: v.strip()
            for k, v in element_data.get("attributes", {}).items()
            if v and str(v).strip()
        },
        "text": (element_data.get("text") or "").strip() or None,
        "path": tuple(element_data.get("path", [])),
    }

    parent = element_data.get("parent")
    if parent:
        result["parent_name"] = parent.get("tag", "")
        result["parent_attribs"] = parent.get("attributes", {})
        result["parent_text"] = (parent.get("text") or "").strip() or None

    siblings = element_data.get("siblings", [])
    if siblings:
        result["siblings"] = tuple(siblings)

    children = element_data.get("children", [])
    if children:
        result["children"] = tuple(children)

    return result


def page_element_to_fingerprint(page, selector: str) -> Optional[Dict[str, Any]]:
    """Extract fingerprint from a live Playwright page element.

    Args:
        page: Playwright Page object
        selector: CSS/XPath selector for the element

    Returns:
        Fingerprint dict or None if element not found.
    """
    try:
        data = page.evaluate("""(selector) => {
            const el = document.querySelector(selector) ||
                       document.evaluate(selector, document, null,
                           XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (!el) return null;

            const parent = el.parentElement;
            const siblings = parent ? Array.from(parent.children)
                .filter(c => c !== el).map(c => c.tagName.toLowerCase()) : [];
            const children = Array.from(el.children)
                .map(c => c.tagName.toLowerCase());

            const attrs = {};
            for (const attr of el.attributes) {
                if (attr.value && attr.value.trim()) {
                    attrs[attr.name] = attr.value.trim();
                }
            }

            // Build element path (tag chain from root)
            const path = [];
            let node = el;
            while (node && node !== document.body) {
                path.unshift(node.tagName.toLowerCase());
                node = node.parentElement;
            }

            const parentData = parent ? {
                tag: parent.tagName.toLowerCase(),
                attributes: Object.fromEntries(
                    Array.from(parent.attributes)
                        .filter(a => a.value && a.value.trim())
                        .map(a => [a.name, a.value.trim()])
                ),
                text: parent.firstChild?.nodeType === 3 ?
                    parent.firstChild.textContent.trim() : null
            } : null;

            return {
                tag: el.tagName.toLowerCase(),
                attributes: attrs,
                text: el.childNodes.length === 1 && el.childNodes[0].nodeType === 3 ?
                    el.childNodes[0].textContent.trim() : null,
                path: path,
                parent: parentData,
                siblings: siblings,
                children: children
            };
        }""", selector)

        if data:
            return element_to_fingerprint(data)
        return None
    except Exception as e:
        logger.debug(f"Fingerprint extraction failed for '{selector}': {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# SIMILARITY SCORING — Compare two element fingerprints
# ═══════════════════════════════════════════════════════════════

def calculate_similarity(fp1: Dict[str, Any], fp2: Dict[str, Any]) -> float:
    """Calculate similarity score (0-100) between two element fingerprints.

    Scoring weights:
    - Tag name: 30% (same tag is a strong signal)
    - Attributes: 30% (class, id, name are highly identifying)
    - Text content: 20% (text changes more often but still useful)
    - DOM path: 10% (structural position)
    - Parent context: 10% (parent tag + attributes)

    Args:
        fp1: First fingerprint (stored/cached)
        fp2: Second fingerprint (current page element)

    Returns:
        Similarity score 0-100 (higher = more similar).
    """
    score = 0.0

    # 1. Tag name (30%)
    if fp1.get("tag") == fp2.get("tag"):
        score += 30.0

    # 2. Attributes (30%)
    attrs1 = fp1.get("attributes", {})
    attrs2 = fp2.get("attributes", {})
    if attrs1 and attrs2:
        # Compare key overlap
        keys1 = set(attrs1.keys())
        keys2 = set(attrs2.keys())
        if keys1 and keys2:
            key_overlap = len(keys1 & keys2) / max(len(keys1 | keys2), 1)
            # Compare values for shared keys
            shared_keys = keys1 & keys2
            if shared_keys:
                value_matches = sum(
                    1 for k in shared_keys
                    if attrs1.get(k) == attrs2.get(k)
                )
                value_score = value_matches / len(shared_keys)
            else:
                value_score = 0
            score += 30.0 * (key_overlap * 0.5 + value_score * 0.5)
        elif not keys1 and not keys2:
            score += 15.0  # Both have no attributes — neutral
    elif not attrs1 and not attrs2:
        score += 15.0

    # 3. Text content (20%)
    text1 = fp1.get("text") or ""
    text2 = fp2.get("text") or ""
    if text1 and text2:
        text_ratio = SequenceMatcher(None, text1, text2).ratio()
        score += 20.0 * text_ratio
    elif not text1 and not text2:
        score += 10.0  # Both have no text — neutral

    # 4. DOM path (10%)
    path1 = fp1.get("path", ())
    path2 = fp2.get("path", ())
    if path1 and path2:
        path_ratio = SequenceMatcher(None, path1, path2).ratio()
        score += 10.0 * path_ratio

    # 5. Parent context (10%)
    parent_name_match = fp1.get("parent_name") == fp2.get("parent_name")
    if parent_name_match:
        score += 5.0
    parent_attrs1 = fp1.get("parent_attribs", {})
    parent_attrs2 = fp2.get("parent_attribs", {})
    if parent_attrs1 and parent_attrs2:
        p_key_overlap = len(set(parent_attrs1) & set(parent_attrs2)) / max(len(set(parent_attrs1) | set(parent_attrs2)), 1)
        score += 5.0 * p_key_overlap
    elif not parent_attrs1 and not parent_attrs2:
        score += 2.5

    return round(score, 2)


# ═══════════════════════════════════════════════════════════════
# SQLITE STORAGE — Persistent element fingerprint storage
# ═══════════════════════════════════════════════════════════════

class AdaptiveStorage:
    """Thread-safe SQLite storage for element fingerprints.

    Stores element fingerprints keyed by (domain, identifier).
    When a selector fails, retrieves the stored fingerprint and
    uses similarity scoring to find the element even if the page
    structure has changed.
    """

    def __init__(self, storage_file: str = _DEFAULT_DB, url: Optional[str] = None):
        self.storage_file = storage_file
        self.url = (url or "").lower().strip() or None
        self.lock = RLock()

        # Ensure directory exists
        Path(storage_file).parent.mkdir(parents=True, exist_ok=True)

        self.connection = db_connect(storage_file, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.cursor = self.connection.cursor()
        self._setup_database()

    def _setup_database(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS element_fingerprints (
                id INTEGER PRIMARY KEY,
                domain TEXT NOT NULL,
                identifier TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE (domain, identifier)
            )
        """)
        self.connection.commit()

    def _get_domain(self) -> str:
        """Extract base domain from URL for storage key."""
        if not self.url:
            return "default"
        try:
            parsed = urlparse(self.url)
            hostname = parsed.hostname or "default"
            # Use registrable domain (e.g., example.com from sub.example.com)
            parts = hostname.split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return hostname
        except Exception:
            return "default"

    @staticmethod
    def _hash_identifier(identifier: str) -> str:
        """Create a deterministic hash for the identifier."""
        return sha256(identifier.lower().strip().encode("utf-8")).hexdigest()[:32]

    def save(self, fingerprint: Dict[str, Any], identifier: str) -> None:
        """Save an element fingerprint to storage.

        Args:
            fingerprint: Element fingerprint dict from element_to_fingerprint()
            identifier: Unique identifier for this element (e.g., CSS selector or custom name)
        """
        domain = self._get_domain()
        hashed_id = self._hash_identifier(identifier)
        fingerprint_json = json.dumps(fingerprint, default=str)

        with self.lock:
            self.cursor.execute(
                """INSERT OR REPLACE INTO element_fingerprints
                   (domain, identifier, fingerprint, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (domain, hashed_id, fingerprint_json, time.time()),
            )
            self.connection.commit()

        logger.debug(f"Saved fingerprint for '{identifier}' on {domain}")

    def retrieve(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored element fingerprint.

        Args:
            identifier: The identifier used when saving

        Returns:
            Fingerprint dict or None if not found.
        """
        domain = self._get_domain()
        hashed_id = self._hash_identifier(identifier)

        with self.lock:
            self.cursor.execute(
                "SELECT fingerprint FROM element_fingerprints WHERE domain = ? AND identifier = ?",
                (domain, hashed_id),
            )
            result = self.cursor.fetchone()

        if result:
            try:
                return json.loads(result[0])
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def delete(self, identifier: str) -> bool:
        """Delete a stored fingerprint."""
        domain = self._get_domain()
        hashed_id = self._hash_identifier(identifier)

        with self.lock:
            self.cursor.execute(
                "DELETE FROM element_fingerprints WHERE domain = ? AND identifier = ?",
                (domain, hashed_id),
            )
            self.connection.commit()
        return True

    def list_fingerprints(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored fingerprints for a domain."""
        domain = domain or self._get_domain()
        with self.lock:
            self.cursor.execute(
                "SELECT identifier, fingerprint, updated_at FROM element_fingerprints WHERE domain = ?",
                (domain,),
            )
            results = self.cursor.fetchall()

        return [
            {
                "identifier": row[0],
                "fingerprint": json.loads(row[1]),
                "updated_at": row[2],
            }
            for row in results
        ]

    def cleanup_expired(self, max_age_days: int = 30) -> int:
        """Remove fingerprints older than max_age_days."""
        cutoff = time.time() - (max_age_days * 86400)
        with self.lock:
            self.cursor.execute(
                "DELETE FROM element_fingerprints WHERE updated_at < ?", (cutoff,)
            )
            deleted = self.cursor.rowcount
            self.connection.commit()
        return deleted

    def close(self):
        """Close database connection."""
        with self.lock:
            try:
                self.connection.commit()
                self.cursor.close()
                self.connection.close()
            except Exception:
                pass

    def __del__(self):
        self.close()


# ═══════════════════════════════════════════════════════════════
# ADAPTIVE SCRAPER — Main integration class
# ═══════════════════════════════════════════════════════════════

class AdaptiveScraper:
    """Adaptive element finder that survives page structure changes.

    Workflow:
    1. Find element with normal selector → success → save fingerprint
    2. Find element with normal selector → FAIL → load saved fingerprint
    3. Scan all page elements → score each against saved fingerprint
    4. Return best match if above threshold

    This is the Agent-OS integration of the adaptive scraping algorithm.
    """

    def __init__(self, browser, storage_file: str = _DEFAULT_DB):
        self.browser = browser
        self.storage_file = storage_file
        self._storages: Dict[str, AdaptiveStorage] = {}

    def _get_storage(self, url: str) -> AdaptiveStorage:
        """Get or create storage for a URL."""
        domain = ""
        try:
            domain = urlparse(url).hostname or ""
        except Exception:
            pass

        if domain not in self._storages:
            self._storages[domain] = AdaptiveStorage(
                storage_file=self.storage_file, url=url
            )
        return self._storages[domain]

    async def find_element(
        self,
        selector: str,
        identifier: Optional[str] = None,
        page_id: str = "main",
        auto_save: bool = True,
        threshold: float = 40.0,
    ) -> Dict[str, Any]:
        """Find an element adaptively.

        1. Try normal selector first
        2. If fails, load stored fingerprint and relocate
        3. If found via relocation, optionally save new fingerprint

        Args:
            selector: CSS or XPath selector
            identifier: Custom name for this element (defaults to selector)
            page_id: Browser tab ID
            auto_save: Automatically save fingerprints for future relocation
            threshold: Minimum similarity score (0-100) to accept relocation

        Returns:
            Dict with status, element info, and method used.
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return {"status": "error", "error": "No active page"}

        identifier = identifier or selector
        url = page.url or ""
        storage = self._get_storage(url)

        # Step 1: Try normal selector
        try:
            element = await page.query_selector(selector)
            if element:
                # Success — save fingerprint for future use
                if auto_save:
                    try:
                        fp = page_element_to_fingerprint(page, selector)
                        if fp:
                            storage.save(fp, identifier)
                    except Exception as e:
                        logger.debug(f"Auto-save fingerprint failed: {e}")

                text = ""
                try:
                    text = await element.inner_text()
                except Exception:
                    pass

                return {
                    "status": "success",
                    "selector": selector,
                    "text": text[:500],
                    "method": "direct_selector",
                    "adaptive": False,
                }
        except Exception as e:
            logger.debug(f"Direct selector failed for '{selector}': {e}")

        # Step 2: Selector failed — try adaptive relocation
        stored_fp = storage.retrieve(identifier)
        if not stored_fp:
            return {
                "status": "error",
                "error": f"Element not found and no stored fingerprint for '{identifier}'",
                "method": "none",
                "adaptive": False,
            }

        # Step 3: Scan all page elements and score against stored fingerprint
        try:
            best_match = await page.evaluate("""(args) => {
                const stored = args.fp;
                const threshold = args.threshold;
                function getElementPath(el) {
                    const path = [];
                    let node = el;
                    while (node && node !== document.body) {
                        path.unshift(node.tagName.toLowerCase());
                        node = node.parentElement;
                    }
                    return path;
                }

                function cleanAttributes(el) {
                    const attrs = {};
                    for (const attr of el.attributes) {
                        if (attr.value && attr.value.trim()) {
                            attrs[attr.name] = attr.value.trim();
                        }
                    }
                    return attrs;
                }

                const allElements = document.querySelectorAll('*');
                let bestScore = 0;
                let bestElement = null;

                for (const el of allElements) {
                    if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' ||
                        el.tagName === 'NOSCRIPT') continue;

                    const parent = el.parentElement;
                    const siblings = parent ? Array.from(parent.children)
                        .filter(c => c !== el).map(c => c.tagName.toLowerCase()) : [];
                    const children = Array.from(el.children)
                        .map(c => c.tagName.toLowerCase());

                    const elData = {
                        tag: el.tagName.toLowerCase(),
                        attributes: cleanAttributes(el),
                        text: el.childNodes.length === 1 && el.childNodes[0].nodeType === 3 ?
                            el.childNodes[0].textContent.trim() : null,
                        path: getElementPath(el),
                        parent_name: parent ? parent.tagName.toLowerCase() : '',
                        parent_attribs: parent ? cleanAttributes(parent) : {},
                        parent_text: parent && parent.firstChild?.nodeType === 3 ?
                            parent.firstChild.textContent.trim() : null,
                        siblings: siblings,
                        children: children
                    };

                    // Calculate similarity (simplified for browser execution)
                    let score = 0;

                    // Tag match (30%)
                    if (elData.tag === stored.tag) score += 30;

                    // Attributes (30%)
                    const sAttrs = stored.attributes || {};
                    const eAttrs = elData.attributes;
                    const sKeys = Object.keys(sAttrs);
                    const eKeys = Object.keys(eAttrs);
                    const sharedKeys = sKeys.filter(k => eKeys.includes(k));
                    if (sKeys.length > 0 && eKeys.length > 0) {
                        const keyOverlap = sharedKeys.length / Math.max(new Set([...sKeys, ...eKeys]).size, 1);
                        const valueMatches = sharedKeys.filter(k => sAttrs[k] === eAttrs[k]).length;
                        const valueScore = sharedKeys.length > 0 ? valueMatches / sharedKeys.length : 0;
                        score += 30 * (keyOverlap * 0.5 + valueScore * 0.5);
                    }

                    // Text (20%)
                    if (elData.text && stored.text) {
                        const maxLen = Math.max(elData.text.length, stored.text.length);
                        if (maxLen > 0) {
                            let matches = 0;
                            const minLen = Math.min(elData.text.length, stored.text.length);
                            for (let i = 0; i < minLen; i++) {
                                if (elData.text[i] === stored.text[i]) matches++;
                            }
                            score += 20 * (matches / maxLen);
                        }
                    }

                    // Path (10%)
                    if (elData.path && stored.path) {
                        const maxPLen = Math.max(elData.path.length, stored.path.length);
                        if (maxPLen > 0) {
                            let pathMatches = 0;
                            const minPLen = Math.min(elData.path.length, stored.path.length);
                            for (let i = 0; i < minPLen; i++) {
                                if (elData.path[i] === stored.path[i]) pathMatches++;
                            }
                            score += 10 * (pathMatches / maxPLen);
                        }
                    }

                    // Parent (10%)
                    if (elData.parent_name === stored.parent_name) score += 5;

                    if (score > bestScore) {
                        bestScore = score;
                        bestElement = {
                            tag: el.tagName.toLowerCase(),
                            id: el.id || '',
                            className: el.className || '',
                            text: (el.textContent || '').trim().substring(0, 200),
                            score: Math.round(score * 100) / 100
                        };
                    }
                }

                if (bestElement && bestScore >= threshold) {
                    return bestElement;
                }
                return null;
            }""", {"fp": stored_fp, "threshold": threshold})

            if best_match:
                # Found via relocation — generate a selector for it
                relocated_selector = None
                if best_match.get("id"):
                    relocated_selector = f"#{best_match['id']}"
                elif best_match.get("className"):
                    classes = best_match["className"].split()[:3]
                    relocated_selector = "." + ".".join(classes)

                if relocated_selector:
                    element = await page.query_selector(relocated_selector)
                    if element:
                        text = ""
                        try:
                            text = await element.inner_text()
                        except Exception:
                            pass

                        # Update stored fingerprint with new location
                        if auto_save:
                            try:
                                new_fp = page_element_to_fingerprint(page, relocated_selector)
                                if new_fp:
                                    storage.save(new_fp, identifier)
                            except Exception:
                                pass

                        return {
                            "status": "success",
                            "selector": relocated_selector,
                            "text": text[:500],
                            "method": "adaptive_relocation",
                            "adaptive": True,
                            "similarity_score": best_match["score"],
                            "original_selector": selector,
                        }

            return {
                "status": "error",
                "error": f"No element found above {threshold}% similarity threshold",
                "method": "adaptive_relocation",
                "adaptive": True,
                "best_score": best_match["score"] if best_match else 0,
            }

        except Exception as e:
            logger.error(f"Adaptive relocation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "method": "adaptive_relocation",
                "adaptive": True,
            }

    async def save_element(
        self,
        selector: str,
        identifier: str,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Explicitly save an element's fingerprint for future adaptive relocation.

        Args:
            selector: CSS/XPath selector for the element
            identifier: Name to save under
            page_id: Browser tab ID

        Returns:
            Status dict.
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return {"status": "error", "error": "No active page"}

        url = page.url or ""
        storage = self._get_storage(url)

        fp = page_element_to_fingerprint(page, selector)
        if not fp:
            return {"status": "error", "error": f"Element not found: {selector}"}

        storage.save(fp, identifier)
        return {
            "status": "success",
            "identifier": identifier,
            "fingerprint": fp,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get adaptive scraper statistics."""
        total_fingerprints = 0
        domains = []
        for domain, storage in self._storages.items():
            fps = storage.list_fingerprints()
            total_fingerprints += len(fps)
            domains.append({"domain": domain, "fingerprints": len(fps)})

        return {
            "total_domains": len(self._storages),
            "total_fingerprints": total_fingerprints,
            "domains": domains,
            "storage_file": self.storage_file,
        }

    def cleanup(self, max_age_days: int = 30) -> Dict[str, Any]:
        """Clean up expired fingerprints."""
        total_deleted = 0
        for storage in self._storages.values():
            total_deleted += storage.cleanup_expired(max_age_days)
        return {"status": "success", "deleted": total_deleted}
