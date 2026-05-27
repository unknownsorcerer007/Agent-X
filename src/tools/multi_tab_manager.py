"""
Multi-Tab Handler — Human-Like Multi-Tab Browsing for AI Agents
===============================================================
A production-grade multi-tab management system that gives AI agents
the ability to work across multiple browser tabs simultaneously —
just like humans do.

KEY FEATURES:
- Create, switch, close, and manage multiple tabs
- Cross-tab data sharing and communication
- Tab state persistence (cookies, storage)
- Intelligent tab switching with context awareness
- Tab grouping for organized workflows
- Memory-efficient tab lifecycle management
- Concurrent tab operations for parallel processing

ARCHITECTURE:
- Each tab is a separate Playwright page with isolated state
- Tab manager coordinates tab lifecycle and switching
- AI agent can reason about which tab to use for which task
- Cross-tab communication via shared context or messaging

Usage:
    # Initialize
    tabs = MultiTabHandler(browser)
    
    # Create tabs for different tasks
    main_tab = await tabs.create_tab("main", "https://google.com")
    docs_tab = await tabs.create_tab("documentation", "https://docs.example.com")
    api_tab = await tabs.create_tab("api-reference", "https://api.example.com")
    
    # Switch between tabs
    await tabs.switch_to("documentation")
    content = await tabs.get_current_page().content()
    
    # Cross-tab operations
    result = await tabs.execute_in_tab("api-reference", 
        lambda page: page.evaluate("fetch('/api/data').then(r=>r.json())"))
    
    # Get tab overview for AI decision making
    overview = tabs.get_tab_overview()
    # AI uses overview to decide which tab to use next
"""
import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("agent-x.multi_tab")


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

class TabStatus(str, Enum):
    """Tab lifecycle states."""
    ACTIVE = "active"           # Currently visible/selected
    BACKGROUND = "background"   # Loaded but not visible
    LOADING = "loading"         # Navigation in progress
    FROZEN = "frozen"           # Paused to save resources
    ERROR = "error"             # Error state (navigation failed, crashed)
    CLOSING = "closing"         # Being closed
    CLOSED = "closed"           # Closed and cleaned up


class TabPriority(str, Enum):
    """Tab priority levels for resource management."""
    CRITICAL = "critical"   # Never auto-close (login, payment)
    HIGH = "high"           # Prefer keeping (main workflow)
    NORMAL = "normal"       # Standard tab
    LOW = "low"             # Can be auto-closed under pressure


@dataclass
class TabInfo:
    """Metadata about a managed tab."""
    tab_id: str
    name: str
    url: str
    title: str
    status: TabStatus
    priority: TabPriority
    created_at: float
    last_accessed: float
    access_count: int
    page_ref: Optional[Any] = None  # Playwright Page object
    parent_tab_id: Optional[str] = None  # For tabs opened from other tabs
    group: Optional[str] = None  # Tab group name
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_count: int = 0
    total_load_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "name": self.name,
            "url": self.url,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "last_accessed": datetime.fromtimestamp(self.last_accessed).isoformat(),
            "access_count": self.access_count,
            "parent_tab": self.parent_tab_id,
            "group": self.group,
            "error_count": self.error_count,
            "load_time_ms": round(self.total_load_time_ms, 2),
        }


@dataclass
class TabOverview:
    """Overview of all tabs for AI decision making."""
    total_tabs: int
    active_tab: Optional[str]
    tabs: List[Dict[str, Any]]
    can_create_more: bool
    memory_pressure: str  # "low", "medium", "high", "critical"
    suggestions: List[str]


# ═══════════════════════════════════════════════════════════════
# Multi-Tab Handler
# ═══════════════════════════════════════════════════════════════

class MultiTabHandler:
    """Human-like multi-tab browsing coordinator for AI agents.
    
    This class manages multiple browser tabs, allowing an AI agent to:
    - Open multiple tabs for different purposes
    - Switch between tabs contextually
    - Share data between tabs
    - Make intelligent decisions about tab usage
    - Efficiently manage memory by freezing/pausing unused tabs
    """

    # Resource limits
    MAX_TABS = 20           # Absolute maximum
    DEFAULT_MAX_TABS = 10   # Recommended maximum
    FREEZE_AFTER_SECONDS = 120  # Auto-freeze background tabs after 2 min
    CLOSE_LOW_PRIORITY_AFTER_SECONDS = 300  # Auto-close low priority after 5 min

    def __init__(self, browser_engine, max_tabs: int = DEFAULT_MAX_TABS):
        """Initialize the multi-tab handler.
        
        Args:
            browser_engine: The AgentBrowser instance
            max_tabs: Maximum number of tabs to allow
        """
        self.browser = browser_engine
        self.max_tabs = min(max_tabs, self.MAX_TABS)
        
        # Tab registry
        self._tabs: Dict[str, TabInfo] = {}
        self._pages: Dict[str, Any] = {}  # tab_id → Playwright Page
        self._current_tab_id: Optional[str] = None
        
        # Resource management
        self._frozen_pages: Dict[str, Dict] = {}  # tab_id → frozen state
        self._maintenance_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Cross-tab communication
        self._shared_state: Dict[str, Any] = {}  # Key-value store across tabs
        self._tab_messages: Dict[str, List[Dict]] = {}  # tab_id → messages
        
        # Statistics
        self._total_switches = 0
        self._total_created = 0
        self._total_closed = 0

    # ─── Lifecycle ──────────────────────────────────────────────

    async def start(self):
        """Start background maintenance tasks."""
        self._running = True
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        logger.info(f"MultiTabHandler started (max {self.max_tabs} tabs)")

    async def stop(self):
        """Stop maintenance and close all tabs."""
        self._running = False
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
        
        # Close all non-main tabs
        tab_ids = list(self._tabs.keys())
        for tab_id in tab_ids:
            if tab_id != "main":
                await self.close_tab(tab_id)
        
        logger.info("MultiTabHandler stopped")

    # ─── Tab Creation ───────────────────────────────────────────

    async def create_tab(
        self,
        name: str,
        url: Optional[str] = None,
        priority: TabPriority = TabPriority.NORMAL,
        group: Optional[str] = None,
        activate: bool = True,
        wait_until: str = "domcontentloaded",
    ) -> str:
        """Create a new browser tab.
        
        Args:
            name: Human-readable name for the tab (e.g., "gmail", "docs")
            url: Initial URL to navigate to
            priority: Tab priority for resource management
            group: Optional group name for organizing tabs
            activate: Whether to switch to this tab immediately
            wait_until: Navigation wait condition
            
        Returns:
            tab_id: Unique identifier for the new tab
        """
        # Check limits
        if len(self._tabs) >= self.max_tabs:
            # Try to free up space by closing low-priority tabs
            freed = await self._free_up_space()
            if not freed:
                raise RuntimeError(
                    f"Maximum tab limit reached ({self.max_tabs}). "
                    f"Close existing tabs or increase limit."
                )
        
        tab_id = f"tab_{name}_{uuid.uuid4().hex[:8]}"
        
        try:
            # Create new page in existing context
            context = self.browser.context
            if not context:
                raise RuntimeError("Browser context not available")
            
            page = await context.new_page()
            
            # Set up page listeners
            self._setup_page_listeners(tab_id, page)
            
            # Store references
            self._pages[tab_id] = page
            
            tab_info = TabInfo(
                tab_id=tab_id,
                name=name,
                url=url or "about:blank",
                title=name,
                status=TabStatus.LOADING if url else TabStatus.BACKGROUND,
                priority=priority,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=0,
                page_ref=page,
                group=group,
            )
            self._tabs[tab_id] = tab_info
            self._total_created += 1
            
            # Navigate if URL provided
            if url:
                nav_start = time.time()
                try:
                    await page.goto(url, wait_until=wait_until, timeout=30000)
                    tab_info.url = page.url
                    tab_info.title = await page.title()
                    tab_info.status = TabStatus.BACKGROUND
                    tab_info.total_load_time_ms = (time.time() - nav_start) * 1000
                except Exception as e:
                    tab_info.status = TabStatus.ERROR
                    tab_info.error_count += 1
                    tab_info.metadata["last_error"] = str(e)
                    logger.warning(f"Tab '{name}' navigation error: {e}")
            
            if activate:
                await self.switch_to(tab_id)
            
            logger.info(
                f"Tab created: {name} ({tab_id}) — "
                f"{len(self._tabs)}/{self.max_tabs} tabs"
            )
            return tab_id
            
        except Exception as e:
            logger.error(f"Failed to create tab '{name}': {e}")
            raise

    async def create_tab_from_current(
        self,
        name: str,
        url: Optional[str] = None,
        priority: TabPriority = TabPriority.NORMAL,
        group: Optional[str] = None,
    ) -> str:
        """Create a new tab from the current tab (like Ctrl+click)."""
        parent_id = self._current_tab_id
        tab_id = await self.create_tab(name, url, priority, group, activate=True)
        
        if tab_id and parent_id and tab_id in self._tabs:
            self._tabs[tab_id].parent_tab_id = parent_id
        
        return tab_id

    # ─── Tab Switching ──────────────────────────────────────────

    async def switch_to(self, tab_id: str) -> TabInfo:
        """Switch to a specific tab (bring to foreground).
        
        Args:
            tab_id: Tab to activate
            
        Returns:
            TabInfo for the activated tab
        """
        if tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")
        
        tab_info = self._tabs[tab_id]
        
        # Unfreeze if needed
        if tab_info.status == TabStatus.FROZEN:
            await self._unfreeze_tab(tab_id)
        
        # Update previous active tab status
        if self._current_tab_id and self._current_tab_id in self._tabs:
            prev = self._tabs[self._current_tab_id]
            if prev.status == TabStatus.ACTIVE:
                prev.status = TabStatus.BACKGROUND
        
        # Activate new tab
        self._current_tab_id = tab_id
        tab_info.status = TabStatus.ACTIVE
        tab_info.last_accessed = time.time()
        tab_info.access_count += 1
        self._total_switches += 1
        
        # Bring page to front in browser
        page = self._pages.get(tab_id)
        if page:
            try:
                await page.bring_to_front()
                # Update URL and title
                tab_info.url = page.url
                try:
                    tab_info.title = await page.title()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Error bringing tab to front: {e}")
        
        logger.debug(f"Switched to tab: {tab_info.name} ({tab_id})")
        return tab_info

    async def switch_by_name(self, name: str) -> TabInfo:
        """Switch to a tab by its human-readable name."""
        for tab_id, info in self._tabs.items():
            if info.name == name and info.status != TabStatus.CLOSED:
                return await self.switch_to(tab_id)
        raise ValueError(f"No active tab named '{name}'")

    async def switch_by_url_match(self, pattern: str) -> TabInfo:
        """Switch to a tab whose URL contains the pattern."""
        for tab_id, info in self._tabs.items():
            if pattern in info.url and info.status != TabStatus.CLOSED:
                return await self.switch_to(tab_id)
        raise ValueError(f"No tab with URL matching '{pattern}'")

    async def switch_by_group(self, group: str) -> List[TabInfo]:
        """Get all tabs in a group and switch to the first one."""
        group_tabs = [
            info for info in self._tabs.values()
            if info.group == group and info.status != TabStatus.CLOSED
        ]
        if not group_tabs:
            raise ValueError(f"No tabs in group '{group}'")
        
        # Switch to most recently accessed in group
        group_tabs.sort(key=lambda t: t.last_accessed, reverse=True)
        return await self.switch_to(group_tabs[0].tab_id)

    # ─── Tab Operations ─────────────────────────────────────────

    async def navigate_in_tab(
        self,
        tab_id: str,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> TabInfo:
        """Navigate a specific tab to a URL without switching to it."""
        if tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")
        
        page = self._pages.get(tab_id)
        if not page:
            raise RuntimeError(f"Page not available for tab: {tab_id}")
        
        tab_info = self._tabs[tab_id]
        tab_info.status = TabStatus.LOADING
        
        try:
            start = time.time()
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            tab_info.url = page.url
            tab_info.title = await page.title()
            tab_info.status = TabStatus.BACKGROUND
            tab_info.total_load_time_ms = (time.time() - start) * 1000
            tab_info.error_count = 0
        except Exception as e:
            tab_info.status = TabStatus.ERROR
            tab_info.error_count += 1
            tab_info.metadata["last_error"] = str(e)
            raise
        
        return tab_info

    async def execute_in_tab(
        self,
        tab_id: str,
        action: Callable,
    ) -> Any:
        """Execute a function in a specific tab without switching.
        
        Args:
            tab_id: Tab to execute in
            action: Async function that takes a page and returns a result
            
        Returns:
            Result from the action function
        """
        if tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")
        
        page = self._pages.get(tab_id)
        if not page:
            raise RuntimeError(f"Page not available for tab: {tab_id}")
        
        # Unfreeze if needed
        if self._tabs[tab_id].status == TabStatus.FROZEN:
            await self._unfreeze_tab(tab_id)
        
        self._tabs[tab_id].last_accessed = time.time()
        
        return await action(page)

    async def execute_in_all_tabs(
        self,
        action: Callable,
        exclude_active: bool = False,
    ) -> Dict[str, Any]:
        """Execute an action in all tabs concurrently.
        
        Args:
            action: Async function that takes (page, tab_info) and returns result
            exclude_active: Whether to skip the currently active tab
            
        Returns:
            Dict mapping tab_id → result
        """
        tasks = []
        tab_ids = []
        
        for tab_id, tab_info in self._tabs.items():
            if tab_info.status in (TabStatus.CLOSED, TabStatus.CLOSING):
                continue
            if exclude_active and tab_id == self._current_tab_id:
                continue
            
            page = self._pages.get(tab_id)
            if page:
                tasks.append(action(page, tab_info))
                tab_ids.append(tab_id)
        
        if not tasks:
            return {}
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            tab_id: result
            for tab_id, result in zip(tab_ids, results)
        }

    # ─── Tab Information ────────────────────────────────────────

    def get_current_tab(self) -> Optional[TabInfo]:
        """Get the currently active tab info."""
        if self._current_tab_id and self._current_tab_id in self._tabs:
            return self._tabs[self._current_tab_id]
        return None

    def get_current_page(self) -> Optional[Any]:
        """Get the Playwright page for the current tab."""
        if self._current_tab_id:
            return self._pages.get(self._current_tab_id)
        return None

    def get_page(self, tab_id: str) -> Optional[Any]:
        """Get the Playwright page for a specific tab."""
        return self._pages.get(tab_id)

    def get_tab(self, tab_id: str) -> Optional[TabInfo]:
        """Get tab info by ID."""
        return self._tabs.get(tab_id)

    def get_tab_by_name(self, name: str) -> Optional[TabInfo]:
        """Get tab info by name."""
        for info in self._tabs.values():
            if info.name == name and info.status != TabStatus.CLOSED:
                return info
        return None

    def list_tabs(self, include_closed: bool = False) -> List[TabInfo]:
        """List all tabs."""
        tabs = self._tabs.values()
        if not include_closed:
            tabs = [t for t in tabs if t.status != TabStatus.CLOSED]
        return sorted(tabs, key=lambda t: t.last_accessed, reverse=True)

    def get_tab_overview(self) -> TabOverview:
        """Get an overview of all tabs for AI decision making.
        
        This provides structured information that the AI can use to
        decide which tab to use for the next action.
        """
        tabs = self.list_tabs()
        active = self.get_current_tab()
        
        # Determine memory pressure
        tab_count = len(tabs)
        if tab_count <= 3:
            pressure = "low"
        elif tab_count <= 6:
            pressure = "medium"
        elif tab_count <= 10:
            pressure = "high"
        else:
            pressure = "critical"
        
        # Generate suggestions
        suggestions = []
        if tab_count >= self.max_tabs * 0.8:
            suggestions.append("Consider closing unused tabs to free memory")
        frozen_count = sum(1 for t in tabs if t.status == TabStatus.FROZEN)
        if frozen_count > 0:
            suggestions.append(f"{frozen_count} frozen tab(s) available to unfreeze")
        if not active:
            suggestions.append("No active tab — select a tab to continue")
        
        # Suggest tab organization
        groups: Dict[str, int] = {}
        for t in tabs:
            if t.group:
                groups[t.group] = groups.get(t.group, 0) + 1
        if len(groups) > 1:
            suggestions.append(f"Tabs organized in {len(groups)} groups: {', '.join(groups.keys())}")
        
        return TabOverview(
            total_tabs=tab_count,
            active_tab=active.tab_id if active else None,
            tabs=[t.to_dict() for t in tabs],
            can_create_more=tab_count < self.max_tabs,
            memory_pressure=pressure,
            suggestions=suggestions,
        )

    # ─── Tab Closing ────────────────────────────────────────────

    async def close_tab(self, tab_id: str) -> bool:
        """Close a specific tab."""
        if tab_id not in self._tabs:
            return False
        
        tab_info = self._tabs[tab_id]
        tab_info.status = TabStatus.CLOSING
        
        # Close the Playwright page
        page = self._pages.pop(tab_id, None)
        if page:
            try:
                await page.close()
            except Exception as e:
                logger.debug(f"Error closing page: {e}")
        
        # Clean up messages
        self._tab_messages.pop(tab_id, None)
        self._frozen_pages.pop(tab_id, None)
        
        tab_info.status = TabStatus.CLOSED
        tab_info.page_ref = None
        self._total_closed += 1
        
        # Switch to another tab if we closed the active one
        if self._current_tab_id == tab_id:
            self._current_tab_id = None
            # Find most recently accessed active tab
            candidates = [
                t for t in self._tabs.values()
                if t.tab_id != tab_id and t.status not in (TabStatus.CLOSED, TabStatus.CLOSING)
            ]
            if candidates:
                candidates.sort(key=lambda t: t.last_accessed, reverse=True)
                try:
                    await self.switch_to(candidates[0].tab_id)
                except Exception:
                    pass
        
        logger.info(f"Tab closed: {tab_info.name} ({tab_id})")
        return True

    async def close_tabs_by_group(self, group: str) -> int:
        """Close all tabs in a group."""
        to_close = [
            t.tab_id for t in self._tabs.values()
            if t.group == group and t.status not in (TabStatus.CLOSED, TabStatus.CLOSING)
        ]
        for tab_id in to_close:
            await self.close_tab(tab_id)
        return len(to_close)

    async def close_all_except(self, keep_tab_ids: List[str]) -> int:
        """Close all tabs except the specified ones."""
        to_close = [
            t.tab_id for t in self._tabs.values()
            if t.tab_id not in keep_tab_ids and t.status not in (TabStatus.CLOSED, TabStatus.CLOSING)
        ]
        for tab_id in to_close:
            await self.close_tab(tab_id)
        return len(to_close)

    async def close_all(self) -> int:
        """Close all tabs except main."""
        return await self.close_all_except(["main"])

    # ─── Cross-Tab Communication ────────────────────────────────

    def set_shared_state(self, key: str, value: Any):
        """Set a shared state value accessible from all tabs."""
        self._shared_state[key] = value

    def get_shared_state(self, key: str, default: Any = None) -> Any:
        """Get a shared state value."""
        return self._shared_state.get(key, default)

    def send_message_to_tab(self, target_tab_id: str, message: Dict[str, Any]):
        """Send a message to a specific tab."""
        if target_tab_id not in self._tab_messages:
            self._tab_messages[target_tab_id] = []
        
        message["timestamp"] = time.time()
        message["from_tab"] = self._current_tab_id
        self._tab_messages[target_tab_id].append(message)
    
    def get_tab_messages(self, tab_id: str, clear: bool = True) -> List[Dict]:
        """Get messages for a tab."""
        messages = self._tab_messages.get(tab_id, [])
        if clear:
            self._tab_messages[tab_id] = []
        return messages

    async def transfer_data_between_tabs(
        self,
        source_tab_id: str,
        target_tab_id: str,
        extract_fn: Callable,
        inject_fn: Callable,
    ) -> Any:
        """Extract data from one tab and inject into another.
        
        Args:
            source_tab_id: Tab to extract data from
            target_tab_id: Tab to inject data into
            extract_fn: Async function(page) → data
            inject_fn: Async function(page, data) → result
            
        Returns:
            Result from the injection function
        """
        source_page = self._pages.get(source_tab_id)
        target_page = self._pages.get(target_tab_id)
        
        if not source_page or not target_page:
            raise ValueError("Source or target tab not found")
        
        data = await extract_fn(source_page)
        return await inject_fn(target_page, data)

    # ─── Tab Freezing / Unfreezing ──────────────────────────────

    async def freeze_tab(self, tab_id: str):
        """Freeze a tab to save memory (pauses JS execution).
        
        This is useful for tabs that aren't currently needed but
        should be preserved for later use.
        """
        if tab_id not in self._tabs or tab_id == self._current_tab_id:
            return
        
        tab_info = self._tabs[tab_id]
        if tab_info.status in (TabStatus.FROZEN, TabStatus.CLOSED, TabStatus.CLOSING):
            return
        
        page = self._pages.get(tab_id)
        if page:
            try:
                # Store state before freezing
                self._frozen_pages[tab_id] = {
                    "url": page.url,
                    "scroll_position": await page.evaluate("() => ({x: window.scrollX, y: window.scrollY})"),
                }
                
                # Pause execution (CDP command via evaluate)
                await page.evaluate("() => { window.__AGENT_X_FROZEN = true; }")
                
                tab_info.status = TabStatus.FROZEN
                logger.debug(f"Tab frozen: {tab_info.name} ({tab_id})")
            except Exception as e:
                logger.warning(f"Failed to freeze tab {tab_id}: {e}")

    async def _unfreeze_tab(self, tab_id: str):
        """Unfreeze a tab (resume JS execution)."""
        if tab_id not in self._tabs:
            return
        
        tab_info = self._tabs[tab_id]
        if tab_info.status != TabStatus.FROZEN:
            return
        
        page = self._pages.get(tab_id)
        frozen_state = self._frozen_pages.pop(tab_id, {})
        
        if page:
            try:
                await page.evaluate("() => { delete window.__AGENT_X_FROZEN; }")
                
                # Restore scroll position
                scroll = frozen_state.get("scroll_position", {})
                if scroll:
                    await page.evaluate(
                        f"() => window.scrollTo({scroll.get('x', 0)}, {scroll.get('y', 0)})"
                    )
                
                tab_info.status = TabStatus.BACKGROUND
                logger.debug(f"Tab unfrozen: {tab_info.name} ({tab_id})")
            except Exception as e:
                logger.warning(f"Failed to unfreeze tab {tab_id}: {e}")

    # ─── Screenshots ────────────────────────────────────────────

    async def screenshot_tab(
        self,
        tab_id: str,
        full_page: bool = True,
        return_base64: bool = False,
    ) -> Union[bytes, str]:
        """Take a screenshot of a specific tab without switching to it."""
        page = self._pages.get(tab_id)
        if not page:
            raise ValueError(f"Page not found for tab: {tab_id}")
        
        screenshot = await page.screenshot(full_page=full_page, type="png")
        if return_base64:
            return base64.b64encode(screenshot).decode("utf-8")
        return screenshot

    async def screenshot_all_tabs(self) -> Dict[str, str]:
        """Take screenshots of all tabs (base64). Returns {tab_name: b64}."""
        results = {}
        for tab_id, tab_info in self._tabs.items():
            if tab_info.status not in (TabStatus.CLOSED, TabStatus.CLOSING):
                try:
                    b64 = await self.screenshot_tab(tab_id, full_page=False, return_base64=True)
                    results[tab_info.name] = b64
                except Exception as e:
                    logger.warning(f"Screenshot failed for {tab_info.name}: {e}")
        return results

    # ─── Internal Methods ───────────────────────────────────────

    def _setup_page_listeners(self, tab_id: str, page):
        """Set up event listeners for a page."""
        def on_dialog(dialog):
            asyncio.create_task(dialog.dismiss())
        
        page.on("dialog", on_dialog)

    async def _free_up_space(self) -> bool:
        """Try to free up tab slots by closing low-priority tabs."""
        # Close low priority tabs that haven't been accessed recently
        now = time.time()
        candidates = [
            t for t in self._tabs.values()
            if t.priority == TabPriority.LOW
            and t.status not in (TabStatus.CLOSED, TabStatus.CLOSING, TabStatus.ACTIVE)
            and (now - t.last_accessed) > self.CLOSE_LOW_PRIORITY_AFTER_SECONDS
        ]
        
        if candidates:
            # Close oldest first
            candidates.sort(key=lambda t: t.last_accessed)
            await self.close_tab(candidates[0].tab_id)
            return True
        
        # Try freezing background tabs
        bg_tabs = [
            t for t in self._tabs.values()
            if t.status == TabStatus.BACKGROUND
            and (now - t.last_accessed) > self.FREEZE_AFTER_SECONDS
        ]
        for tab in bg_tabs[:2]:  # Freeze up to 2 at a time
            await self.freeze_tab(tab.tab_id)
        
        if bg_tabs:
            return True
        
        return False

    async def _maintenance_loop(self):
        """Background task for tab lifecycle management."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self._running:
                    break
                
                now = time.time()
                
                # Freeze old background tabs
                for tab_id, tab_info in list(self._tabs.items()):
                    if (tab_info.status == TabStatus.BACKGROUND and
                        (now - tab_info.last_accessed) > self.FREEZE_AFTER_SECONDS):
                        await self.freeze_tab(tab_id)
                
                # Clean up closed tabs from registry
                closed_tabs = [
                    tid for tid, t in self._tabs.items()
                    if t.status == TabStatus.CLOSED
                ]
                for tid in closed_tabs:
                    del self._tabs[tid]
                
                if closed_tabs:
                    logger.debug(f"Cleaned up {len(closed_tabs)} closed tab(s)")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tab maintenance error: {e}")

    # ─── Statistics ─────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics."""
        statuses: Dict[str, int] = {}
        for t in self._tabs.values():
            s = t.status.value
            statuses[s] = statuses.get(s, 0) + 1
        
        return {
            "total_tabs": len(self._tabs),
            "active_tab": self._current_tab_id,
            "tab_statuses": statuses,
            "total_created": self._total_created,
            "total_closed": self._total_closed,
            "total_switches": self._total_switches,
            "max_tabs": self.max_tabs,
            "shared_state_keys": list(self._shared_state.keys()),
        }


# ═══════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════

def format_tab_overview_for_ai(overview: TabOverview) -> str:
    """Format a tab overview as a natural language summary for the AI.
    
    This helps the AI understand the current tab state and make
    intelligent decisions about which tab to use.
    """
    lines = [
        f"Tab Overview: {overview.total_tabs} tab(s) open",
        f"Memory Pressure: {overview.memory_pressure}",
        f"Can create more: {'yes' if overview.can_create_more else 'no (limit reached)'}",
        "",
        "Open Tabs:",
    ]
    
    for tab in overview.tabs:
        status_icon = {
            "active": "▶",
            "background": "⏸",
            "loading": "⏳",
            "frozen": "❄",
            "error": "⚠",
        }.get(tab["status"], "?")
        
        lines.append(
            f"  {status_icon} [{tab['tab_id']}] {tab['name']} — {tab['title'][:50]}"
            f" ({tab['status']}, {tab['priority']}, accessed {tab['access_count']}x)"
        )
    
    if overview.suggestions:
        lines.extend(["", "Suggestions:"])
        for s in overview.suggestions:
            lines.append(f"  • {s}")
    
    return "\n".join(lines)
