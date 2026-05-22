"""
Agent-OS Auto-Heal Engine
Self-healing selectors that automatically recover when the DOM changes.

How it works:
  1. When a selector SUCCEEDES → fingerprint the element (text, attributes, position, DOM path)
  2. When a selector FAILS → attempt multi-strategy recovery:
     a. Same text content match
     b. Same aria-label / placeholder / title / alt
     c. Similar attribute fingerprint (class, role, data-*)
     d. Same structural position (nth-child path)
     e. Visual position proximity (nearby coordinates)
     f. Role-based fallback (button, input, link, etc.)
  3. Recovered selector gets cached → future calls skip the failure phase
  4. Full healing history and statistics for observability

Integration:
  - Auto-heal wraps browser.click(), browser.fill_form(), browser.wait_for_element()
  - Works transparently — agents don't need to change their code
  - Healing report available via "heal-stats" command
"""
import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger("agent-os.auto_heal")


# ─── Fingerprint JS ─────────────────────────────────────────

_FINGERPRINT_ELEMENT_JS = """
((selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;

    // Text content (trimmed, first 200 chars)
    const text = (el.innerText || el.textContent || '').trim().substring(0, 200);

    // Tag
    const tag = el.tagName.toLowerCase();

    // Attributes fingerprint
    const attrs = {};
    for (const a of el.attributes) {
        if (['style', 'class'].includes(a.name)) continue;
        attrs[a.name] = a.value.substring(0, 200);
    }

    // Class list
    const classes = Array.from(el.classList).sort();

    // Role
    const role = el.getAttribute('role') || '';

    // Data attributes
    const dataAttrs = {};
    for (const a of el.attributes) {
        if (a.name.startsWith('data-')) {
            dataAttrs[a.name] = a.value.substring(0, 200);
        }
    }

    // Aria attributes
    const ariaLabel = el.getAttribute('aria-label') || '';
    const ariaRole = el.getAttribute('aria-role') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const title = el.getAttribute('title') || '';
    const alt = el.getAttribute('alt') || '';
    const name = el.getAttribute('name') || '';
    const type = el.getAttribute('type') || '';
    const href = el.getAttribute('href') || '';
    const id = el.id || '';

    // DOM structural path
    const path = [];
    let cur = el;
    while (cur && cur !== document.body) {
        const parent = cur.parentElement;
        if (!parent) break;
        const siblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
        const idx = siblings.indexOf(cur) + 1;
        path.unshift(cur.tagName.toLowerCase() + (siblings.length > 1 ? ':nth-of-type(' + idx + ')' : ''));
        cur = parent;
    }

    // Position
    const rect = el.getBoundingClientRect();

    // Parent context
    const parentTag = el.parentElement ? el.parentElement.tagName.toLowerCase() : '';
    const parentClasses = el.parentElement ? Array.from(el.parentElement.classList).sort() : [];

    // Sibling context
    const prevSibling = el.previousElementSibling;
    const nextSibling = el.nextElementSibling;
    const prevTag = prevSibling ? prevSibling.tagName.toLowerCase() + (prevSibling.id ? '#' + prevSibling.id : '') : '';
    const nextTag = nextSibling ? nextSibling.tagName.toLowerCase() + (nextSibling.id ? '#' + nextSibling.id : '') : '';

    return {
        text: text,
        tag: tag,
        id: id,
        name: name,
        classes: classes,
        role: role,
        attrs: attrs,
        dataAttrs: dataAttrs,
        ariaLabel: ariaLabel,
        ariaRole: ariaRole,
        placeholder: placeholder,
        title: title,
        alt: alt,
        type: type,
        href: href,
        path: path.join(' > '),
        pathParts: path,
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
        parentTag: parentTag,
        parentClasses: parentClasses,
        prevTag: prevTag,
        nextTag: nextTag,
    };
});
"""

_FIND_BY_TEXT_JS = """
((text, tag) => {
    const results = [];
    const seen = new Set();
    const query = tag ? tag : '*';
    const els = document.querySelectorAll(query);

    for (const el of els) {
        const elText = (el.innerText || el.textContent || '').trim();
        if (!elText) continue;
        if (elText.toLowerCase() !== text.toLowerCase() &&
            !elText.toLowerCase().includes(text.toLowerCase())) continue;

        const sel = _makeSelector(el);
        if (seen.has(sel)) continue;
        seen.add(sel);
        results.push(sel);
        if (results.length >= 5) break;
    }
    return results;

    function _makeSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        let p = [], c = el;
        while (c && c !== document.body) {
            let s = c.tagName.toLowerCase();
            if (c.id) { p.unshift('#' + CSS.escape(c.id)); break; }
            if (c.className && typeof c.className === 'string') {
                const cls = c.className.trim().split(/\\s+/)[0];
                if (cls) s += '.' + CSS.escape(cls);
            }
            const par = c.parentElement;
            if (par) {
                const sibs = Array.from(par.children).filter(x => x.tagName === c.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(c) + 1) + ')';
            }
            p.unshift(s);
            c = par;
        }
        return p.join(' > ');
    }
});
"""

_FIND_BY_ATTRS_JS = """
((tag, attrs, dataAttrs, classes) => {
    const results = [];
    const seen = new Set();
    const query = tag ? tag : '*';
    const els = document.querySelectorAll(query);

    for (const el of els) {
        let score = 0;
        let checks = 0;

        // Check standard attrs
        for (const [k, v] of Object.entries(attrs || {})) {
            checks++;
            if (el.getAttribute(k) === v) score++;
        }

        // Check data attrs
        for (const [k, v] of Object.entries(dataAttrs || {})) {
            checks++;
            if (el.getAttribute(k) === v) score++;
        }

        // Check classes
        if (classes && classes.length > 0) {
            checks++;
            const elClasses = Array.from(el.classList);
            const overlap = classes.filter(c => elClasses.includes(c)).length;
            score += overlap / Math.max(classes.length, 1);
        }

        if (checks === 0) continue;
        const ratio = score / checks;
        if (ratio < 0.5) continue;

        const sel = _makeSelector(el);
        if (seen.has(sel)) continue;
        seen.add(sel);
        results.push({ selector: sel, score: ratio });
    }

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, 5);

    function _makeSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        let p = [], c = el;
        while (c && c !== document.body) {
            let s = c.tagName.toLowerCase();
            if (c.id) { p.unshift('#' + CSS.escape(c.id)); break; }
            if (c.className && typeof c.className === 'string') {
                const cls = c.className.trim().split(/\\s+/)[0];
                if (cls) s += '.' + CSS.escape(cls);
            }
            const par = c.parentElement;
            if (par) {
                const sibs = Array.from(par.children).filter(x => x.tagName === c.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(c) + 1) + ')';
            }
            p.unshift(s);
            c = par;
        }
        return p.join(' > ');
    }
});
"""

_FIND_BY_PATH_JS = """
((pathParts, tag) => {
    // Try to find element with same structural path
    if (!pathParts || pathParts.length === 0) return [];

    const results = [];
    const seen = new Set();

    // Build candidates from the last tag in the path
    const lastTag = pathParts[pathParts.length - 1].split(':')[0];
    const els = document.querySelectorAll(tag || lastTag);

    for (const el of els) {
        const elPath = [];
        let cur = el;
        while (cur && cur !== document.body) {
            const parent = cur.parentElement;
            if (!parent) break;
            const siblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
            const idx = siblings.indexOf(cur) + 1;
            elPath.unshift(cur.tagName.toLowerCase() + (siblings.length > 1 ? ':nth-of-type(' + idx + ')' : ''));
            cur = parent;
        }

        // Compare paths (match from the end)
        let matchLen = 0;
        const minLen = Math.min(elPath.length, pathParts.length);
        for (let i = 1; i <= minLen; i++) {
            if (elPath[elPath.length - i] === pathParts[pathParts.length - i]) {
                matchLen++;
            } else {
                break;
            }
        }

        if (matchLen >= 2) {
            const sel = _makeSelector(el);
            if (!seen.has(sel)) {
                seen.add(sel);
                results.push({ selector: sel, matchDepth: matchLen, totalDepth: pathParts.length });
            }
        }
    }

    results.sort((a, b) => b.matchDepth - a.matchDepth);
    return results.slice(0, 5);

    function _makeSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        let p = [], c = el;
        while (c && c !== document.body) {
            let s = c.tagName.toLowerCase();
            if (c.id) { p.unshift('#' + CSS.escape(c.id)); break; }
            if (c.className && typeof c.className === 'string') {
                const cls = c.className.trim().split(/\\s+/)[0];
                if (cls) s += '.' + CSS.escape(cls);
            }
            const par = c.parentElement;
            if (par) {
                const sibs = Array.from(par.children).filter(x => x.tagName === c.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(c) + 1) + ')';
            }
            p.unshift(s);
            c = par;
        }
        return p.join(' > ');
    }
});
"""

_FIND_BY_ROLE_TEXT_JS = """
((role, text) => {
    const results = [];
    const seen = new Set();
    const textLower = (text || '').toLowerCase();

    // Search by role
    let els = [];
    if (role) {
        els = Array.from(document.querySelectorAll('[role="' + role + '"]'));
    }
    // Also search semantic elements for common roles
    if (role === 'button') els = els.concat(Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]')));
    if (role === 'link') els = els.concat(Array.from(document.querySelectorAll('a[href]')));
    if (role === 'textbox') els = els.concat(Array.from(document.querySelectorAll('input[type="text"], input:not([type]), textarea, [role="textbox"]')));
    if (role === 'checkbox') els = els.concat(Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')));

    for (const el of els) {
        const elText = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if (!textLower || elText.includes(textLower)) {
            const sel = _makeSelector(el);
            if (!seen.has(sel)) {
                seen.add(sel);
                results.push(sel);
                if (results.length >= 5) break;
            }
        }
    }
    return results;

    function _makeSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        let p = [], c = el;
        while (c && c !== document.body) {
            let s = c.tagName.toLowerCase();
            if (c.id) { p.unshift('#' + CSS.escape(c.id)); break; }
            if (c.className && typeof c.className === 'string') {
                const cls = c.className.trim().split(/\\s+/)[0];
                if (cls) s += '.' + CSS.escape(cls);
            }
            const par = c.parentElement;
            if (par) {
                const sibs = Array.from(par.children).filter(x => x.tagName === c.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(c) + 1) + ')';
            }
            p.unshift(s);
            c = par;
        }
        return p.join(' > ');
    }
});
"""

_FIND_BY_PROXIMITY_JS = """
((targetX, targetY, tag, maxDistance) => {
    const results = [];
    const query = tag || '*';
    const els = document.querySelectorAll(query);

    for (const el of els) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const cx = rect.x + rect.width / 2;
        const cy = rect.y + rect.height / 2;
        const dist = Math.sqrt((cx - targetX) ** 2 + (cy - targetY) ** 2);
        if (dist <= maxDistance) {
            results.push({ selector: _makeSelector(el), distance: Math.round(dist), tag: el.tagName.toLowerCase() });
        }
    }

    results.sort((a, b) => a.distance - b.distance);
    return results.slice(0, 5);

    function _makeSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        let p = [], c = el;
        while (c && c !== document.body) {
            let s = c.tagName.toLowerCase();
            if (c.id) { p.unshift('#' + CSS.escape(c.id)); break; }
            if (c.className && typeof c.className === 'string') {
                const cls = c.className.trim().split(/\\s+/)[0];
                if (cls) s += '.' + CSS.escape(cls);
            }
            const par = c.parentElement;
            if (par) {
                const sibs = Array.from(par.children).filter(x => x.tagName === c.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(c) + 1) + ')';
            }
            p.unshift(s);
            c = par;
        }
        return p.join(' > ');
    }
});
"""


class AutoHeal:
    """
    Self-healing selector engine.

    Wraps browser actions and automatically recovers when selectors break.

    Usage:
        heal = AutoHeal(browser)

        # Heal-wrapped click (auto-recovers if selector is stale)
        result = await heal.click("button.submit-btn")

        # Heal-wrapped fill
        result = await heal.fill("input[name=email]", "user@example.com")

        # Heal-wrapped wait
        result = await heal.wait(".results-loaded")

        # Manual heal (find new selector for a broken one)
        result = await heal.heal_selector("button.submit-btn")

        # Stats
        stats = heal.get_stats()
    """

    FINGERPRINT_DIR = os.path.expanduser("~/.agent-os/heal")

    def __init__(self, browser, smart_wait=None):
        self.browser = browser
        self.smart_wait = smart_wait
        self._fingerprint_cache: Dict[str, Dict] = {}  # selector -> fingerprint
        self._healed_cache: Dict[str, str] = {}  # old_selector -> new_selector
        self._stats = {
            "total_operations": 0,
            "heal_attempts": 0,
            "heal_successes": 0,
            "heal_failures": 0,
            "by_strategy": {},
            "history": [],
        }
        self._load_fingerprints()

    # ─── Public API: Heal-Wrapped Actions ───────────────────

    async def click(self, selector: str, page_id: str = "main", timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Click with auto-heal. If the selector fails, attempts recovery.
        """
        self._stats["total_operations"] += 1
        return await self._heal_action("click", selector, {}, page_id, timeout_ms)

    async def fill(self, selector: str, value: str, page_id: str = "main", timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Fill form field with auto-heal.
        """
        self._stats["total_operations"] += 1
        return await self._heal_action("fill", selector, {"value": value}, page_id, timeout_ms)

    async def wait(self, selector: str, page_id: str = "main", timeout_ms: int = 10000) -> Dict[str, Any]:
        """
        Wait for element with auto-heal.
        """
        self._stats["total_operations"] += 1
        return await self._heal_action("wait", selector, {}, page_id, timeout_ms)

    async def hover(self, selector: str, page_id: str = "main", timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Hover with auto-heal.
        """
        self._stats["total_operations"] += 1
        return await self._heal_action("hover", selector, {}, page_id, timeout_ms)

    async def double_click(self, selector: str, page_id: str = "main", timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Double-click with auto-heal.
        """
        self._stats["total_operations"] += 1
        return await self._heal_action("double_click", selector, {}, page_id, timeout_ms)

    async def heal_selector(self, broken_selector: str, page_id: str = "main") -> Dict[str, Any]:
        """
        Manually attempt to heal a broken selector.
        Returns the new working selector, or error if unrecoverable.
        """
        self._stats["heal_attempts"] += 1

        # Check if we have a cached fingerprint
        fingerprint = self._fingerprint_cache.get(broken_selector)
        if not fingerprint:
            # Try to find one from saved fingerprints
            fingerprint = self._find_fingerprint(broken_selector)

        if not fingerprint:
            return {
                "status": "error",
                "error": f"No fingerprint found for selector: {broken_selector}",
                "suggestion": "The element must have been successfully selected at least once to build a fingerprint.",
            }

        healed = await self._attempt_heal(broken_selector, fingerprint, page_id)
        if healed:
            self._stats["heal_successes"] += 1
            self._healed_cache[broken_selector] = healed
            self._save_fingerprints()
            self._record_history(broken_selector, healed, "manual")
            return {
                "status": "success",
                "original_selector": broken_selector,
                "healed_selector": healed,
                "method": "manual_heal",
            }

        self._stats["heal_failures"] += 1
        return {
            "status": "error",
            "error": f"Could not heal selector: {broken_selector}",
            "fingerprint": {
                "tag": fingerprint.get("tag"),
                "text": fingerprint.get("text", "")[:100],
                "id": fingerprint.get("id"),
                "classes": fingerprint.get("classes"),
            },
        }

    # ─── Fingerprint Management ────────────────────────────

    async def fingerprint(self, selector: str, page_id: str = "main") -> Dict[str, Any]:
        """
        Capture a fingerprint of an element. Call this after a successful selector match
        to enable auto-healing later.
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        fp = await page.evaluate(_FINGERPRINT_ELEMENT_JS, selector)
        if not fp:
            return {"status": "error", "error": f"Element not found: {selector}"}

        fp["captured_at"] = time.time()
        fp["selector"] = selector
        self._fingerprint_cache[selector] = fp
        self._save_fingerprints()

        return {
            "status": "success",
            "selector": selector,
            "fingerprint": {
                "tag": fp["tag"],
                "text": fp["text"][:100],
                "id": fp["id"],
                "classes": fp["classes"],
                "dataAttrs": list(fp.get("dataAttrs", {}).keys()),
                "ariaLabel": fp["ariaLabel"],
            },
        }

    async def fingerprint_page(self, page_id: str = "main") -> Dict[str, Any]:
        """
        Auto-fingerprint all interactive elements on the current page.
        Useful for building a healing library for a site.
        """
        page = self.browser._pages.get(page_id, self.browser.page)

        # Find all interactive elements
        selectors = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const interactives = document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [onclick], [tabindex]');
            for (const el of interactives) {
                let sel;
                if (el.id) sel = '#' + CSS.escape(el.id);
                else if (el.name) sel = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                else continue;
                if (!seen.has(sel)) {
                    seen.add(sel);
                    results.push(sel);
                }
            }
            return results;
        }""")

        captured = 0
        for sel in selectors:
            fp = await page.evaluate(_FINGERPRINT_ELEMENT_JS, sel)
            if fp:
                fp["captured_at"] = time.time()
                fp["selector"] = sel
                self._fingerprint_cache[sel] = fp
                captured += 1

        self._save_fingerprints()

        return {
            "status": "success",
            "fingerprints_captured": captured,
            "total_fingerprints": len(self._fingerprint_cache),
        }

    # ─── Stats & History ────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get healing statistics."""
        return {
            "status": "success",
            "stats": {
                "total_operations": self._stats["total_operations"],
                "heal_attempts": self._stats["heal_attempts"],
                "heal_successes": self._stats["heal_successes"],
                "heal_failures": self._stats["heal_failures"],
                "success_rate": round(
                    self._stats["heal_successes"] / max(1, self._stats["heal_attempts"]) * 100, 1
                ),
                "by_strategy": self._stats["by_strategy"],
                "cached_heals": len(self._healed_cache),
                "fingerprints_stored": len(self._fingerprint_cache),
            },
            "recent_heals": self._stats["history"][-20:],
        }

    def get_healed_cache(self) -> Dict[str, str]:
        """Get all cached healed selectors."""
        return dict(self._healed_cache)

    def clear_cache(self):
        """Clear all cached data."""
        self._fingerprint_cache.clear()
        self._healed_cache.clear()
        self._save_fingerprints()

    # ─── Internal: Heal Action Pipeline ─────────────────────

    async def _heal_action(
        self,
        action: str,
        selector: str,
        params: Dict,
        page_id: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        """Execute action with auto-heal on failure."""

        # Check if already healed
        working_selector = self._healed_cache.get(selector, selector)

        # Try the action directly
        result = await self._do_action(action, working_selector, params, page_id)

        if result.get("status") == "success":
            # Fingerprint for future healing (fire and forget)
            asyncio.create_task(self._auto_fingerprint(working_selector, page_id))
            result["healed"] = working_selector != selector
            if result["healed"]:
                result["original_selector"] = selector
            return result

        # Action failed — attempt healing
        self._stats["heal_attempts"] += 1
        logger.info(f"Selector failed, attempting heal: {selector}")

        # Get or build fingerprint
        fingerprint = self._fingerprint_cache.get(selector) or self._fingerprint_cache.get(working_selector)
        if not fingerprint:
            fingerprint = self._find_fingerprint(selector)

        if not fingerprint:
            # No fingerprint — try text-based and role-based recovery
            healed = await self._heuristic_heal(selector, page_id)
            if healed:
                self._healed_cache[selector] = healed
                self._stats["heal_successes"] += 1
                self._record_history(selector, healed, "heuristic")
                retry = await self._do_action(action, healed, params, page_id)
                retry["healed"] = True
                retry["original_selector"] = selector
                retry["healed_selector"] = healed
                return retry

            self._stats["heal_failures"] += 1
            return result  # Return original error

        # Attempt multi-strategy heal
        healed = await self._attempt_heal(selector, fingerprint, page_id)

        if healed:
            self._healed_cache[selector] = healed
            self._fingerprint_cache[healed] = fingerprint  # Store under new selector too
            self._stats["heal_successes"] += 1
            self._save_fingerprints()
            self._record_history(selector, healed, "fingerprint")

            # Retry the action with healed selector
            retry = await self._do_action(action, healed, params, page_id)
            if retry.get("status") == "success":
                retry["healed"] = True
                retry["original_selector"] = selector
                retry["healed_selector"] = healed
                return retry

        self._stats["heal_failures"] += 1
        self._record_history(selector, None, "failed")
        return {
            "status": "error",
            "error": f"Selector '{selector}' failed and auto-heal could not recover it.",
            "original_error": result.get("error"),
        }

    async def _do_action(self, action: str, selector: str, params: Dict, page_id: str) -> Dict:
        """Execute a browser action."""
        try:
            if action == "click":
                return await self.browser.click(selector, page_id=page_id)
            elif action == "fill":
                return await self.browser.fill_form({selector: params["value"]}, page_id=page_id)
            elif action == "wait":
                return await self.browser.wait_for_element(selector, page_id=page_id)
            elif action == "hover":
                return await self.browser.hover(selector, page_id=page_id)
            elif action == "double_click":
                return await self.browser.double_click(selector, page_id=page_id)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Internal: Healing Strategies ───────────────────────

    async def _attempt_heal(self, original_selector: str, fingerprint: Dict, page_id: str) -> Optional[str]:
        """
        Try multiple strategies to find the element again.
        Returns a working selector or None.
        """
        page = self.browser._pages.get(page_id, self.browser.page)
        strategies = []

        # Strategy 1: Same text content
        text = fingerprint.get("text", "").strip()
        if text and len(text) > 1 and len(text) < 200:
            strategies.append(("text_content", self._heal_by_text, (page, text, fingerprint.get("tag"))))

        # Strategy 2: Aria-label / placeholder / title
        for attr_name in ["ariaLabel", "placeholder", "title", "alt", "name"]:
            attr_val = fingerprint.get(attr_name, "")
            if attr_val:
                strategies.append((f"attr_{attr_name}", self._heal_by_attr, (page, fingerprint.get("tag"), attr_name, attr_val)))

        # Strategy 3: Attribute fingerprint
        data_attrs = fingerprint.get("dataAttrs", {})
        all_attrs = fingerprint.get("attrs", {})
        if data_attrs or all_attrs:
            strategies.append(("attr_fingerprint", self._heal_by_attr_fingerprint, (page, fingerprint)))

        # Strategy 4: Structural path
        path_parts = fingerprint.get("pathParts", [])
        if path_parts:
            strategies.append(("structural_path", self._heal_by_path, (page, path_parts, fingerprint.get("tag"))))

        # Strategy 5: Visual proximity
        rect = fingerprint.get("rect", {})
        if rect and rect.get("w", 0) > 0:
            strategies.append(("visual_proximity", self._heal_by_proximity, (page, rect, fingerprint.get("tag"))))

        # Strategy 6: Role + text
        role = fingerprint.get("role", "")
        if role:
            strategies.append(("role_text", self._heal_by_role_text, (page, role, text)))

        # Strategy 7: Same tag + classes
        classes = fingerprint.get("classes", [])
        tag = fingerprint.get("tag", "")
        if classes and tag:
            strategies.append(("tag_class", self._heal_by_tag_class, (page, tag, classes)))

        # Execute strategies in priority order
        for strategy_name, strategy_fn, args in strategies:
            try:
                candidate = await strategy_fn(*args)
                if candidate:
                    # Verify the candidate actually exists and is visible
                    exists = await page.evaluate(
                        "((s) => { const e = document.querySelector(s); return e && e.offsetParent !== null; })",
                        candidate,
                    )
                    if exists:
                        self._stats["by_strategy"][strategy_name] = self._stats["by_strategy"].get(strategy_name, 0) + 1
                        logger.info(f"Auto-heal succeeded via '{strategy_name}': {original_selector} → {candidate}")
                        return candidate
            except Exception as e:
                logger.debug(f"Heal strategy '{strategy_name}' failed: {e}")
                continue

        return None

    async def _heal_by_text(self, page, text: str, tag: str = None) -> Optional[str]:
        """Find element by matching visible text."""
        results = await page.evaluate(_FIND_BY_TEXT_JS, text[:200], tag)
        return results[0] if results else None

    async def _heal_by_attr(self, page, tag: str, attr_name: str, attr_value: str) -> Optional[str]:
        """Find element by matching a specific attribute."""
        # Map fingerprint names to DOM attribute names
        attr_map = {
            "ariaLabel": "aria-label",
            "placeholder": "placeholder",
            "title": "title",
            "alt": "alt",
            "name": "name",
        }
        dom_attr = attr_map.get(attr_name, attr_name)

        # Use page.evaluate with arguments to avoid JS injection from attribute values
        js = """(([tag, domAttr, attrValue]) => {
            const query = tag || '*';
            const els = document.querySelectorAll(query);
            for (const el of els) {
                if (el.getAttribute(domAttr) === attrValue) {
                    if (el.id) return '#' + CSS.escape(el.id);
                    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                    return null;
                }
            }
            return null;
        })"""
        return await page.evaluate(js, [tag or "*", dom_attr, attr_value])

    async def _heal_by_attr_fingerprint(self, page, fingerprint: Dict) -> Optional[str]:
        """Find element by matching attribute fingerprint similarity."""
        tag = fingerprint.get("tag", "*")
        attrs = {k: v for k, v in fingerprint.get("attrs", {}).items() if k not in ("id", "class")}
        data_attrs = fingerprint.get("dataAttrs", {})
        classes = fingerprint.get("classes", [])

        results = await page.evaluate(_FIND_BY_ATTRS_JS, tag, attrs, data_attrs, classes)
        if results:
            return results[0].get("selector")
        return None

    async def _heal_by_path(self, page, path_parts: List[str], tag: str = None) -> Optional[str]:
        """Find element by matching structural DOM path."""
        results = await page.evaluate(_FIND_BY_PATH_JS, path_parts, tag)
        if results:
            best = max(results, key=lambda r: r["matchDepth"])
            if best["matchDepth"] >= 2:
                return best["selector"]
        return None

    async def _heal_by_proximity(self, page, rect: Dict, tag: str = None) -> Optional[str]:
        """Find element by visual proximity to original position."""
        target_x = rect["x"] + rect["w"] / 2
        target_y = rect["y"] + rect["h"] / 2
        max_distance = max(200, max(rect["w"], rect["h"]) * 2)

        results = await page.evaluate(_FIND_BY_PROXIMITY_JS, target_x, target_y, tag, max_distance)
        if results:
            return results[0].get("selector")
        return None

    async def _heal_by_role_text(self, page, role: str, text: str) -> Optional[str]:
        """Find element by ARIA role and text content."""
        results = await page.evaluate(_FIND_BY_ROLE_TEXT_JS, role, text[:100])
        return results[0] if results else None

    async def _heal_by_tag_class(self, page, tag: str, classes: List[str]) -> Optional[str]:
        """Find element by tag and overlapping classes."""
        class_selector = "." + ".".join(classes[:3])  # Use first 3 classes max
        js = f"""(() => {{
            try {{
                const els = document.querySelectorAll('{tag}{class_selector}');
                if (els.length > 0) {{
                    const el = els[0];
                    if (el.id) return '#' + CSS.escape(el.id);
                    return '{tag}{class_selector}';
                }}
            }} catch(e) {{}}
            return null;
        }})()"""
        return await page.evaluate(js)

    async def _heuristic_heal(self, selector: str, page_id: str) -> Optional[str]:
        """
        Last-resort healing without fingerprint.
        Parses the broken selector and tries to find similar elements.
        """
        page = self.browser._pages.get(page_id, self.browser.page)

        # Extract info from the selector itself
        tag = ""
        cls = ""
        elem_id = ""
        _name = ""

        # Parse common selector patterns
        if selector.startswith("#"):
            elem_id = selector[1:]
        elif "." in selector:
            parts = selector.split(".")
            tag = parts[0] if parts[0] else "div"
            cls = parts[1] if len(parts) > 1 else ""
        elif "[" in selector and "]" in selector:
            # attribute selector like input[name="email"] or input[name*="email"]
            import re
            m = re.match(r'^([\w-]+)\[([\w-]+)([=*^$~|]?=)"([^"]+)"\]$', selector)
            if m:
                tag, attr_name, operator, attr_value = m.groups()
                # Try finding by attribute
                js = f"""(() => {{
                    const el = document.querySelector('{tag}[{attr_name}*="{attr_value}"]');
                    if (el) {{
                        if (el.id) return '#' + CSS.escape(el.id);
                        return '{tag}[{attr_name}="' + el.getAttribute('{attr_name}') + '"]';
                    }}
                    return null;
                }})()"""
                result = await page.evaluate(js)
                if result:
                    return result

        # Try partial class match
        if cls:
            js = f"""(() => {{
                const els = document.querySelectorAll('[class*="{cls}"]');
                if (els.length > 0) {{
                    const el = els[0];
                    if (el.id) return '#' + CSS.escape(el.id);
                    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                }}
                return null;
            }})()"""
            result = await page.evaluate(js)
            if result:
                return result

        # Try partial ID match
        if elem_id:
            js = f"""(() => {{
                const els = document.querySelectorAll('[id*="{elem_id}"]');
                if (els.length > 0) {{
                    return '#' + CSS.escape(els[0].id);
                }}
                return null;
            }})()"""
            result = await page.evaluate(js)
            if result:
                return result

        return None

    # ─── Internal: Fingerprint Storage ──────────────────────

    async def _auto_fingerprint(self, selector: str, page_id: str):
        """Auto-capture fingerprint after successful action (background)."""
        if selector in self._fingerprint_cache:
            return  # Already captured
        try:
            page = self.browser._pages.get(page_id, self.browser.page)
            fp = await page.evaluate(_FINGERPRINT_ELEMENT_JS, selector)
            if fp:
                fp["captured_at"] = time.time()
                fp["selector"] = selector
                self._fingerprint_cache[selector] = fp
                # Periodically save (not on every action)
                if len(self._fingerprint_cache) % 10 == 0:
                    self._save_fingerprints()
        except Exception:
            pass

    def _find_fingerprint(self, selector: str) -> Optional[Dict]:
        """Find a fingerprint by selector or partial match."""
        if selector in self._fingerprint_cache:
            return self._fingerprint_cache[selector]

        # Try partial match
        for key, fp in self._fingerprint_cache.items():
            # Match by ID in selector
            if selector.startswith("#") and fp.get("id") == selector[1:]:
                return fp
            # Match by class
            if "." in selector:
                cls = selector.split(".")[1] if selector.startswith(".") else selector.split(".")[-1]
                if cls in fp.get("classes", []):
                    return fp

        return None

    def _load_fingerprints(self):
        """Load fingerprints from disk."""
        fp_file = Path(self.FINGERPRINT_DIR) / "fingerprints.json"
        if fp_file.exists():
            try:
                with open(fp_file, "r") as f:
                    data = json.load(f)
                self._fingerprint_cache = data.get("fingerprints", {})
                self._healed_cache = data.get("healed", {})
                self._stats["by_strategy"] = data.get("stats", {}).get("by_strategy", {})
                logger.info(f"Loaded {len(self._fingerprint_cache)} fingerprints from disk")
            except Exception as e:
                logger.warning(f"Failed to load fingerprints: {e}")

    def _save_fingerprints(self):
        """Save fingerprints to disk."""
        fp_dir = Path(self.FINGERPRINT_DIR)
        fp_dir.mkdir(parents=True, exist_ok=True)
        fp_file = fp_dir / "fingerprints.json"
        try:
            with open(fp_file, "w") as f:
                json.dump({
                    "fingerprints": self._fingerprint_cache,
                    "healed": self._healed_cache,
                    "stats": {"by_strategy": self._stats["by_strategy"]},
                    "saved_at": time.time(),
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save fingerprints: {e}")

    def _record_history(self, original: str, healed: Optional[str], method: str):
        """Record healing event in history."""
        self._stats["history"].append({
            "timestamp": time.time(),
            "original": original,
            "healed": healed,
            "method": method,
            "success": healed is not None,
        })
        # Keep last 500 events
        if len(self._stats["history"]) > 500:
            self._stats["history"] = self._stats["history"][-500:]
