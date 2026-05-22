"""
Agent-OS Smart Wait Engine
Intelligent waiting that automatically detects when pages/elements are truly ready.

Strategies:
  - network_idle: Wait for all network requests to settle
  - dom_stable: Wait for DOM mutations to stop
  - element_ready: Wait for element visible, interactable, animations done
  - page_ready: Wait for fonts, images, frameworks to finish loading
  - js_condition: Wait for arbitrary JS expression to become truthy
  - composed: Combine multiple conditions with AND/OR logic

Handles SPAs, lazy-loaded content, infinite scroll, AJAX-heavy pages.
"""
import asyncio
import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger("agent-os.smart_wait")


# ─── JS Snippets (injected once, reused everywhere) ─────────

_INSTALL_NETWORK_TRACKER_JS = """
(() => {
    if (window.__agentos_nettracker) return;
    window.__agentos_nettracker = { pending: 0, completed: 0, lastActivity: Date.now() };

    // Use PerformanceObserver to track network activity WITHOUT overriding fetch/XHR
    // This avoids conflicts with stealth modules that also override fetch
    try {
        const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                window.__agentos_nettracker.completed++;
                window.__agentos_nettracker.lastActivity = Date.now();
            }
        });
        observer.observe({ type: 'resource', buffered: true });
    } catch(e) {
        // PerformanceObserver not available, fall back to simple tracking
        // Track via fetch wrapper that chains properly
        const origFetch = window.fetch;
        window.fetch = function() {
            window.__agentos_nettracker.pending++;
            window.__agentos_nettracker.lastActivity = Date.now();
            return origFetch.apply(this, arguments).finally(() => {
                window.__agentos_nettracker.pending--;
                window.__agentos_nettracker.completed++;
                window.__agentos_nettracker.lastActivity = Date.now();
            });
        };
    }
})();
"""

_CHECK_NETWORK_IDLE_JS = """
(() => {
    const t = window.__agentos_nettracker;
    if (!t) return { idle: true, pending: 0, completed: 0, lastActivity: 0 };
    const idleMs = Date.now() - t.lastActivity;
    return { idle: t.pending === 0, pending: t.pending, completed: t.completed, idleMs: idleMs };
})();
"""

_CHECK_DOM_STABLE_JS = """
((stabilityMs) => {
    if (!window.__agentos_domobserver) {
        window.__agentos_domobserver = { mutations: 0, lastMutation: Date.now() };
        const obs = new MutationObserver(() => {
            window.__agentos_domobserver.mutations++;
            window.__agentos_domobserver.lastMutation = Date.now();
        });
        obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
    }
    const d = window.__agentos_domobserver;
    const sinceLast = Date.now() - d.lastMutation;
    return { stable: sinceLast >= stabilityMs, sinceLastMs: sinceLast, totalMutations: d.mutations };
});
"""

_CHECK_ELEMENT_READY_JS = """
((selector) => {
    const el = document.querySelector(selector);
    if (!el) return { found: false, visible: false, interactable: false, animating: false, rect: null };

    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 &&
                    style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    style.opacity !== '0';

    // Check if element or ancestors are in a CSS animation/transition
    const animating = style.animationName !== 'none' ||
                      style.transitionProperty !== 'none' && style.transitionDuration !== '0s';

    // Check pointer-events
    const pointerOk = style.pointerEvents !== 'none';

    // Check if disabled
    const disabled = el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';

    // Check if obscured by overlay (sample center point)
    let obscured = false;
    if (visible) {
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const topEl = document.elementFromPoint(cx, cy);
        obscured = topEl !== el && !el.contains(topEl);
    }

    return {
        found: true,
        visible: visible,
        interactable: visible && pointerOk && !disabled && !obscured,
        animating: animating,
        disabled: disabled,
        obscured: obscured,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
});
"""

_CHECK_PAGE_READY_JS = """
(() => {
    // Document readiness
    const docReady = document.readyState === 'complete';

    // Pending images
    const images = Array.from(document.images);
    const imagesLoaded = images.every(img => img.complete);
    const pendingImages = images.filter(img => !img.complete).length;

    // Font readiness — consider loaded or no fonts as ready
    // 'loading' state is transient and should not block page_ready
    let fontsReady = true;
    if (document.fonts && document.fonts.status) {
        fontsReady = document.fonts.status === 'loaded' || document.fonts.size === 0;
    }

    // Framework-specific checks
    let frameworkReady = true;
    // SPA frameworks (generic detection)
    const rootEl = document.querySelector('#root, #app, [data-reactroot], [data-v-app], [ng-app]');
    if (rootEl) frameworkReady = true;
    // Angular
    const ngReady = typeof window.getAllAngularRootElements === 'undefined' ||
                    window.getAllAngularRootElements().length > 0;

    // Pending iframes (basic check)
    const iframes = Array.from(document.querySelectorAll('iframe'));
    const iframesDone = iframes.every(f => {
        try { return f.contentDocument && f.contentDocument.readyState === 'complete'; }
        catch(e) { return true; // cross-origin, assume done
        }
    });

    const ready = docReady && imagesLoaded && fontsReady && frameworkReady && ngReady && iframesDone;

    return {
        ready: ready,
        docReady: docReady,
        imagesLoaded: imagesLoaded,
        pendingImages: pendingImages,
        fontsReady: fontsReady,
        frameworkReady: frameworkReady,
        angularReady: ngReady,
        iframesDone: iframesDone,
    };
});
"""

_CHECK_JS_CONDITION_JS = """
((expr) => {
    try {
        // Whitelist: only allow safe property access and comparisons
        // Block: assignment, function calls (except allowed), eval, Function, etc.
        const FORBIDDEN = /\b(eval|Function|import|require|fetch|XMLHttp|__proto__|constructor)\b|[=!]/i;
        if (FORBIDDEN.test(expr)) {
            return { success: false, error: 'Expression contains forbidden patterns', truthy: false };
        }
        const result = new Function('return (' + expr + ')')();
        return { success: true, value: result, truthy: !!result };
    } catch(e) {
        return { success: false, error: e.message, truthy: false };
    }
});
"""


class SmartWait:
    """
    Intelligent waiting engine for Agent-OS.
    Handles SPAs, AJAX, lazy load, animations, infinite scroll.

    Usage:
        wait = SmartWait(browser)

        # Wait for network to go idle (no requests for N ms)
        await wait.network_idle(idle_ms=500)

        # Wait for DOM to stop changing
        await wait.dom_stable(stability_ms=300)

        # Wait for element to be truly ready (visible, clickable, not animating)
        await wait.element_ready("button.submit")

        # Wait for full page readiness
        await wait.page_ready()

        # Wait for custom JS condition
        await wait.js_condition("document.querySelector('.loaded') !== null")

        # Compose: wait for page ready AND element ready
        await wait.compose([
            {"strategy": "page_ready"},
            {"strategy": "element_ready", "selector": "#login-form"},
        ], mode="all")
    """

    # How often to poll each strategy (ms)
    DEFAULT_POLL_MS = 150

    def _adaptive_poll_interval(self, elapsed_ms: float) -> float:
        """Adaptive polling: fast initially, slower over time to reduce CDP overhead."""
        if elapsed_ms < 5000:
            return 0.15
        elif elapsed_ms < 15000:
            return 0.30
        else:
            return 0.50

    # Hard maximum wait time (ms) — never wait longer than this
    HARD_MAX_MS = 120_000

    def __init__(self, browser):
        self.browser = browser
        self._nettracker_installed: set = set()  # page_ids where tracker is installed
        self._domobserver_installed: set = set()

    # ─── Public API ─────────────────────────────────────────

    async def network_idle(
        self,
        idle_ms: int = 500,
        timeout_ms: int = 30_000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait until there are zero in-flight network requests for `idle_ms` milliseconds.
        Handles fetch(), XMLHttpRequest, and dynamically injected scripts.

        Args:
            idle_ms: How long (ms) the network must be completely quiet.
            timeout_ms: Maximum total wait time.
            page_id: Tab to monitor.
        """
        page = self._get_page(page_id)
        await self._ensure_nettracker(page, page_id)

        start = time.time()
        idle_start = None
        total_waited = 0

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                result = await page.evaluate(_CHECK_NETWORK_IDLE_JS)
                return self._timeout_result("network_idle", elapsed_ms, {
                    "idle_required_ms": idle_ms,
                    "last_check": result,
                })

            result = await page.evaluate(_CHECK_NETWORK_IDLE_JS)

            if result["idle"] and result["pending"] == 0:
                if idle_start is None:
                    idle_start = time.time()
                elif (time.time() - idle_start) * 1000 >= idle_ms:
                    total_waited = (time.time() - start) * 1000
                    return {
                        "status": "success",
                        "strategy": "network_idle",
                        "waited_ms": round(total_waited, 1),
                        "idle_achieved_ms": idle_ms,
                        "total_requests_completed": result["completed"],
                    }
            else:
                idle_start = None

            await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))

    async def dom_stable(
        self,
        stability_ms: int = 300,
        timeout_ms: int = 15_000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait until the DOM stops changing for `stability_ms` milliseconds.
        Detects: element additions/removals, attribute changes, subtree modifications.

        Great for SPAs that do rapid DOM updates after navigation.

        Args:
            stability_ms: How long (ms) the DOM must have zero mutations.
            timeout_ms: Maximum total wait time.
            page_id: Tab to monitor.
        """
        page = self._get_page(page_id)
        await self._ensure_domobserver(page, page_id)

        start = time.time()
        stable_since = None

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                return self._timeout_result("dom_stable", elapsed_ms, {
                    "stability_required_ms": stability_ms,
                })

            result = await page.evaluate(_CHECK_DOM_STABLE_JS, stability_ms)

            if result["stable"]:
                if stable_since is None:
                    stable_since = time.time()
                elif (time.time() - stable_since) * 1000 >= stability_ms:
                    total_waited = (time.time() - start) * 1000
                    return {
                        "status": "success",
                        "strategy": "dom_stable",
                        "waited_ms": round(total_waited, 1),
                        "stability_achieved_ms": stability_ms,
                        "total_mutations_observed": result["totalMutations"],
                    }
            else:
                stable_since = None

            await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))

    async def element_ready(
        self,
        selector: str,
        timeout_ms: int = 15_000,
        require_interactable: bool = True,
        wait_for_animation: bool = True,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait for an element to be TRULY ready for interaction.

        Checks:
          1. Element exists in DOM
          2. Element is visible (non-zero size, not display:none, not visibility:hidden)
          3. Element is interactable (not disabled, pointer-events enabled, not obscured)
          4. CSS animations/transitions have finished (optional)

        This replaces the naive `wait_for_selector` that only checks DOM presence.

        Args:
            selector: CSS selector for the target element.
            timeout_ms: Maximum wait time.
            require_interactable: If True, also checks element isn't disabled/obscured.
            wait_for_animation: If True, waits for CSS animations/transitions to finish.
            page_id: Tab to search.
        """
        page = self._get_page(page_id)
        start = time.time()
        last_state = None

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                return self._timeout_result("element_ready", elapsed_ms, {
                    "selector": selector,
                    "last_state": last_state,
                })

            state = await page.evaluate(_CHECK_ELEMENT_READY_JS, selector)
            last_state = state

            if not state["found"]:
                await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))
                continue

            if not state["visible"]:
                await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))
                continue

            if require_interactable and not state["interactable"]:
                await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))
                continue

            if wait_for_animation and state["animating"]:
                await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))
                continue

            total_waited = (time.time() - start) * 1000
            return {
                "status": "success",
                "strategy": "element_ready",
                "selector": selector,
                "waited_ms": round(total_waited, 1),
                "element": {
                    "visible": state["visible"],
                    "interactable": state["interactable"],
                    "animating": state["animating"],
                    "disabled": state.get("disabled", False),
                    "obscured": state.get("obscured", False),
                    "rect": state["rect"],
                },
            }

    async def page_ready(
        self,
        timeout_ms: int = 30_000,
        require_images: bool = True,
        require_fonts: bool = True,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait for the page to be fully loaded and settled.

        Checks:
          - document.readyState === 'complete'
          - All <img> elements finished loading
          - Web fonts loaded (document.fonts.ready)
          - SPA frameworks settled (app root mounted, framework initialized)
          - iframes loaded

        Args:
            timeout_ms: Maximum wait time.
            require_images: Wait for all images to load.
            require_fonts: Wait for web fonts.
            page_id: Tab to monitor.
        """
        page = self._get_page(page_id)
        start = time.time()
        last_state = None

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                return self._timeout_result("page_ready", elapsed_ms, {"last_state": last_state})

            state = await page.evaluate(_CHECK_PAGE_READY_JS)
            last_state = state

            ready = state["docReady"] and state["frameworkReady"] and state["angularReady"] and state["iframesDone"]
            if require_images:
                ready = ready and state["imagesLoaded"]
            if require_fonts:
                ready = ready and state["fontsReady"]

            if ready:
                total_waited = (time.time() - start) * 1000
                return {
                    "status": "success",
                    "strategy": "page_ready",
                    "waited_ms": round(total_waited, 1),
                    "state": state,
                }

            await asyncio.sleep(self._adaptive_poll_interval(elapsed_ms))

    async def js_condition(
        self,
        expression: str,
        timeout_ms: int = 10_000,
        poll_ms: int = None,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait for a JavaScript expression to become truthy.

        Examples:
            'document.querySelector(".loaded") !== null'
            'window.myApp && window.myApp.isReady'
            'document.querySelectorAll(".item").length >= 10'
            'document.title.includes("Dashboard")'

        Args:
            expression: JS expression to evaluate. Must return truthy/falsy.
            timeout_ms: Maximum wait time.
            poll_ms: Polling interval (default: 150ms).
            page_id: Tab to evaluate in.
        """
        page = self._get_page(page_id)
        start = time.time()
        poll = (poll_ms or self.DEFAULT_POLL_MS) / 1000
        last_result = None

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                return self._timeout_result("js_condition", elapsed_ms, {
                    "expression": expression,
                    "last_result": last_result,
                })

            result = await page.evaluate(_CHECK_JS_CONDITION_JS, expression)
            last_result = result

            if result["success"] and result["truthy"]:
                total_waited = (time.time() - start) * 1000
                return {
                    "status": "success",
                    "strategy": "js_condition",
                    "expression": expression,
                    "value": result.get("value"),
                    "waited_ms": round(total_waited, 1),
                }

            await asyncio.sleep(poll)

    async def compose(
        self,
        conditions: List[Dict[str, Any]],
        mode: str = "all",
        timeout_ms: int = 30_000,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Wait for multiple conditions combined with AND/OR logic.

        Each condition is a dict with:
            - strategy: "network_idle" | "dom_stable" | "element_ready" | "page_ready" | "js_condition"
            - Plus strategy-specific params (selector, expression, idle_ms, etc.)

        Args:
            conditions: List of condition dicts.
            mode: "all" (AND) — all conditions must pass.
                  "any" (OR) — at least one condition must pass.
            timeout_ms: Maximum total wait time for the entire composition.
            page_id: Tab to evaluate in.

        Examples:
            # Wait for page ready AND login button ready
            await wait.compose([
                {"strategy": "page_ready"},
                {"strategy": "element_ready", "selector": "#login-btn"},
            ])

            # Wait for either a success message OR an error message
            await wait.compose([
                {"strategy": "element_ready", "selector": ".success-msg", "require_interactable": False},
                {"strategy": "element_ready", "selector": ".error-msg", "require_interactable": False},
            ], mode="any")
        """
        start = time.time()

        if mode == "all":
            # Run all conditions, all must succeed
            results = {}
            for cond in conditions:
                elapsed_ms = (time.time() - start) * 1000
                remaining = max(100, timeout_ms - elapsed_ms)

                result = await self._run_condition(cond, remaining, page_id)
                results[cond.get("strategy", "unknown")] = result

                if result["status"] != "success":
                    total_waited = (time.time() - start) * 1000
                    return {
                        "status": "error",
                        "mode": "all",
                        "failed_condition": cond.get("strategy"),
                        "waited_ms": round(total_waited, 1),
                        "results": results,
                        "error": result.get("error", f"Condition '{cond.get('strategy')}' did not pass"),
                    }

            total_waited = (time.time() - start) * 1000
            return {
                "status": "success",
                "mode": "all",
                "waited_ms": round(total_waited, 1),
                "results": results,
            }

        elif mode == "any":
            # Run all conditions concurrently, first success wins
            elapsed_ms = (time.time() - start) * 1000
            remaining = max(100, timeout_ms - elapsed_ms)

            tasks = []
            for cond in conditions:
                tasks.append(asyncio.create_task(self._run_condition(cond, remaining, page_id)))

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=remaining / 1000)

            # Cancel pending
            for t in pending:
                t.cancel()

            # Check if any succeeded
            for t in done:
                try:
                    result = t.result()
                    if result["status"] == "success":
                        total_waited = (time.time() - start) * 1000
                        return {
                            "status": "success",
                            "mode": "any",
                            "waited_ms": round(total_waited, 1),
                            "winning_condition": result.get("strategy"),
                            "result": result,
                        }
                except Exception:
                    continue

            total_waited = (time.time() - start) * 1000
            return self._timeout_result("compose:any", total_waited, {"conditions": len(conditions)})

        else:
            return {"status": "error", "error": f"Unknown compose mode: {mode}. Use 'all' or 'any'."}

    # JS snippet for fast DOM node count check — lighter than full MutationObserver
    _FAST_DOM_COUNT_JS = """
    (() => {
        return document.querySelectorAll('*').length;
    })();
    """

    async def _fast_dom_stable_check(
        self,
        page,
        check_interval_ms: int = 500,
        max_checks: int = 4,
    ) -> bool:
        """Quick DOM stability check by comparing node counts.

        Polls the DOM node count at intervals. If the count stays the same
        for 2 consecutive checks, the DOM is likely stable enough to skip
        the full network_idle wait. This is much faster than waiting for
        full network idle (typically saves 1-5 seconds).

        Returns True if DOM appears stable, False if still changing.
        """
        last_count = None
        stable_count = 0

        for _ in range(max_checks):
            try:
                count = await page.evaluate(self._FAST_DOM_COUNT_JS)
            except Exception:
                return False

            if count == last_count:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
            last_count = count
            await asyncio.sleep(check_interval_ms / 1000)

        return False

    async def auto(
        self,
        selector: str = None,
        idle_ms: int = 500,
        dom_stable_ms: int = 300,
        timeout_ms: int = 30_000,
        require_interactable: bool = True,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """
        The "just works" wait — automatically combines the best strategies.

        If selector is provided:
            page_ready → network_idle → dom_stable → element_ready

        If selector is None:
            page_ready → network_idle → dom_stable

        This is the recommended wait for most use cases.

        Args:
            selector: Optional element to wait for.
            idle_ms: Network idle threshold.
            dom_stable_ms: DOM stability threshold.
            timeout_ms: Maximum total wait.
            require_interactable: If True, element must be clickable.
            page_id: Tab to wait in.
        """
        start = time.time()

        conditions = []

        # Phase 0: Fast DOM stability check
        # Before committing to expensive waits, do a quick poll to see if
        # the DOM is already stable. If it is, we can skip the longer
        # network_idle wait entirely, saving 1-5 seconds on most pages.
        page = self._get_page(page_id)
        dom_already_stable = await self._fast_dom_stable_check(page)

        # Phase 1: Page readiness
        elapsed = (time.time() - start) * 1000
        remaining = max(100, timeout_ms - elapsed)
        r1 = await self.page_ready(timeout_ms=min(remaining, 10_000), page_id=page_id)
        conditions.append({"strategy": "page_ready", "result": r1})

        # Phase 2: Network idle — skip if DOM was already stable
        if dom_already_stable:
            r2 = {
                "status": "success",
                "strategy": "network_idle",
                "waited_ms": 0,
                "skipped_reason": "dom_already_stable",
            }
            conditions.append({"strategy": "network_idle", "result": r2})
        else:
            elapsed = (time.time() - start) * 1000
            remaining = max(100, timeout_ms - elapsed)
            r2 = await self.network_idle(idle_ms=idle_ms, timeout_ms=min(remaining, 8_000), page_id=page_id)
            conditions.append({"strategy": "network_idle", "result": r2})

        # Phase 3: DOM stable
        elapsed = (time.time() - start) * 1000
        remaining = max(100, timeout_ms - elapsed)
        r3 = await self.dom_stable(stability_ms=dom_stable_ms, timeout_ms=min(remaining, 5_000), page_id=page_id)
        conditions.append({"strategy": "dom_stable", "result": r3})

        # Phase 4: Element ready (if selector provided)
        if selector:
            elapsed = (time.time() - start) * 1000
            remaining = max(100, timeout_ms - elapsed)
            r4 = await self.element_ready(
                selector,
                timeout_ms=remaining,
                require_interactable=require_interactable,
                page_id=page_id,
            )
            conditions.append({"strategy": "element_ready", "result": r4})
        else:
            r4 = {"status": "success", "skipped": True}

        total_waited = (time.time() - start) * 1000

        # Determine overall success
        all_ok = all(
            c["result"].get("status") == "success" or c["result"].get("skipped")
            for c in conditions
        )

        return {
            "status": "success" if all_ok else "error",
            "strategy": "auto",
            "waited_ms": round(total_waited, 1),
            "phases": conditions,
            "selector": selector,
            "error": None if all_ok else "One or more wait conditions timed out",
        }

    # ─── Internal Helpers ───────────────────────────────────

    def _get_page(self, page_id: str):
        return self.browser._pages.get(page_id, self.browser.page)

    async def _ensure_nettracker(self, page, page_id: str):
        if page_id not in self._nettracker_installed:
            await page.evaluate(_INSTALL_NETWORK_TRACKER_JS)
            self._nettracker_installed.add(page_id)

    async def _ensure_domobserver(self, page, page_id: str):
        if page_id not in self._domobserver_installed:
            await page.evaluate(_CHECK_DOM_STABLE_JS, 300)
            self._domobserver_installed.add(page_id)

    async def _run_condition(self, cond: Dict, timeout_ms: float, page_id: str) -> Dict:
        strategy = cond.get("strategy", "")
        t_ms = min(timeout_ms, cond.get("timeout_ms", timeout_ms))

        if strategy == "network_idle":
            return await self.network_idle(
                idle_ms=cond.get("idle_ms", 500),
                timeout_ms=t_ms,
                page_id=page_id,
            )
        elif strategy == "dom_stable":
            return await self.dom_stable(
                stability_ms=cond.get("stability_ms", 300),
                timeout_ms=t_ms,
                page_id=page_id,
            )
        elif strategy == "element_ready":
            return await self.element_ready(
                selector=cond.get("selector", ""),
                timeout_ms=t_ms,
                require_interactable=cond.get("require_interactable", True),
                wait_for_animation=cond.get("wait_for_animation", True),
                page_id=page_id,
            )
        elif strategy == "page_ready":
            return await self.page_ready(
                timeout_ms=t_ms,
                require_images=cond.get("require_images", True),
                require_fonts=cond.get("require_fonts", True),
                page_id=page_id,
            )
        elif strategy == "js_condition":
            return await self.js_condition(
                expression=cond.get("expression", "true"),
                timeout_ms=t_ms,
                poll_ms=cond.get("poll_ms"),
                page_id=page_id,
            )
        else:
            return {"status": "error", "error": f"Unknown strategy: {strategy}"}

    def _timeout_result(self, strategy: str, elapsed_ms: float, extra: Dict = None) -> Dict:
        result = {
            "status": "error",
            "strategy": strategy,
            "error": f"Wait timed out after {round(elapsed_ms, 1)}ms",
            "waited_ms": round(elapsed_ms, 1),
        }
        if extra:
            result.update(extra)
        return result

    def reset_trackers(self, page_id: str = None):
        """Reset installed tracker flags (call after navigation)."""
        if page_id:
            self._nettracker_installed.discard(page_id)
            self._domobserver_installed.discard(page_id)
        else:
            self._nettracker_installed.clear()
            self._domobserver_installed.clear()
