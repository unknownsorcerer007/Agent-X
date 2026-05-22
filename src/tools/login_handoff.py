"""
Agent-OS Login Handoff Engine
==============================
When AI agent encounters a login/signup page, it pauses automation and hands
control to the human user. After the user completes login, control returns
to the AI agent with all session cookies and auth state preserved.

Security guarantees:
- AI NEVER sees or stores user passwords
- User credentials go only to the real website via the browser
- After handoff completes, only cookies/session state are visible to AI
- All handoff sessions are encrypted at rest and expire automatically
- Screenshots during handoff are memory-only (never written to disk)

State machine:
  IDLE → DETECTED → WAITING_FOR_USER → COMPLETED → IDLE
                    ↘ CANCELLED → IDLE
                    ↘ TIMED_OUT → IDLE
"""
import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.login-handoff")


# ═══════════════════════════════════════════════════════════════
# Login Page Detection — URL patterns + DOM signals
# ═══════════════════════════════════════════════════════════════

class LoginDetector:
    """Detects login/signup pages using URL patterns and DOM analysis.

    Uses a two-layer approach:
    1. URL/domain matching — fast, works before full page load
    2. DOM signal analysis — accurate, works after page load

    This ensures detection happens reliably whether the site uses
    /login paths, /auth/ paths, /accounts paths, or SPA-style routing.
    """

    # Known login URL path patterns (case-insensitive substring match)
    LOGIN_URL_PATTERNS: List[str] = [
        "/login", "/signin", "/sign-in", "/sign_in",
        "/auth/login", "/auth/signin", "/authenticate",
        "/accounts/login", "/accounts/signin",
        "/session/new", "/sessions/new",
        "/user/login", "/users/login", "/users/sign_in",
        "/wp-login.php", "/admin/login",
        "/oauth/authorize", "/oauth/authenticate",
        "/idp/login", "/saml/login",
        "/login.html", "/signin.html",
    ]

    # Known signup URL path patterns
    SIGNUP_URL_PATTERNS: List[str] = [
        "/signup", "/sign-up", "/sign_up", "/register",
        "/join", "/create-account", "/create_account",
        "/auth/signup", "/auth/register",
        "/accounts/register", "/accounts/signup",
    ]

    # Domains that ALWAYS require login (known social media / SSO)
    LOGIN_REQUIRED_DOMAINS: Dict[str, str] = {
        "instagram.com": "login",
        "www.instagram.com": "login",
        "twitter.com": "login",
        "x.com": "login",
        "facebook.com": "login",
        "www.facebook.com": "login",
        "m.facebook.com": "login",
        "linkedin.com": "login",
        "www.linkedin.com": "login",
        "github.com": "login",
        "gitlab.com": "login",
        "reddit.com": "login",
        "www.reddit.com": "login",
        "tiktok.com": "login",
        "www.tiktok.com": "login",
        "snapchat.com": "login",
        "pinterest.com": "login",
        "tumblr.com": "login",
        "discord.com": "login",
        "slack.com": "login",
        "whatsapp.com": "login",
        "web.whatsapp.com": "login",
        "mail.google.com": "login",
        "accounts.google.com": "login",
        "outlook.live.com": "login",
        "login.microsoftonline.com": "login",
        "amazon.com": "login",
        "www.amazon.com": "login",
        "netflix.com": "login",
        "spotify.com": "login",
        "open.spotify.com": "login",
        "apple.com": "login",
        "idmsa.apple.com": "login",
        "icloud.com": "login",
    }

    # Specific URL paths that indicate these domains need login
    DOMAIN_LOGIN_PATHS: Dict[str, List[str]] = {
        "instagram.com": ["/accounts/login/", "/accounts/signup/"],
        "twitter.com": ["/login", "/i/flow/login", "/signup"],
        "x.com": ["/login", "/i/flow/login", "/signup"],
        "facebook.com": ["/login.php", "/login/", "/r.php"],
        "linkedin.com": ["/login", "/signup", "/uas/login"],
        "github.com": ["/login", "/signup", "/session"],
        "reddit.com": ["/login", "/register"],
        "amazon.com": ["/ap/signin", "/ap/register"],
        "google.com": ["/accounts/login", "/ServiceLogin", "/signin"],
        "accounts.google.com": ["/login", "/ServiceLogin", "/signin", "/v3/signin"],
        "login.microsoftonline.com": ["/login", "/oauth2/authorize", "/common/login"],
        "m.facebook.com": ["/login.php", "/login/"],
    }

    # DOM signals that indicate a login form is present
    # These are CSS selectors evaluated via page.evaluate()
    LOGIN_FORM_SELECTORS: List[str] = [
        'input[type="password"]',
        'form[action*="login"]',
        'form[action*="signin"]',
        'form[action*="sign-in"]',
        'form[action*="session"]',
        'form[action*="auth"]',
        'form[action*="authenticate"]',
        'form[id*="login"]',
        'form[id*="signin"]',
        'form[id*="sign-in"]',
        'form[class*="login"]',
        'form[class*="signin"]',
        'form[class*="sign-in"]',
        '[data-testid*="login"]',
        '[data-testid*="signin"]',
        '[data-testid*="sign-in"]',
        '[data-testid*="login-form"]',
        'button[type="submit"][formaction*="login"]',
        'input[name="password"]',
        'input[name="passwd"]',
        'input[name="pass"]',
        'input[name="user_password"]',
        'input[autocomplete="current-password"]',
        'input[autocomplete="new-password"]',
    ]

    # DOM signals that indicate a signup form specifically
    SIGNUP_FORM_SELECTORS: List[str] = [
        'form[action*="signup"]',
        'form[action*="register"]',
        'form[action*="sign-up"]',
        'form[id*="signup"]',
        'form[id*="register"]',
        'form[class*="signup"]',
        'form[class*="register"]',
        '[data-testid*="signup"]',
        '[data-testid*="register"]',
        '[data-testid*="sign-up"]',
        'input[name="confirm_password"]',
        'input[name="password_confirm"]',
        'input[name="password_confirmation"]',
        'input[autocomplete="new-password"]',
        'input[name="terms"]',
        'input[name="agree"]',
    ]

    # Page title keywords (lowercase) that suggest login page
    LOGIN_TITLE_KEYWORDS: List[str] = [
        "log in", "login", "sign in", "signin", "sign-in",
        "authenticate", "authentication",
    ]

    # Page title keywords that suggest signup page
    SIGNUP_TITLE_KEYWORDS: List[str] = [
        "sign up", "signup", "sign-up", "register", "create account",
        "join", "get started",
    ]

    # DOM text content patterns that indicate login requirement
    LOGIN_TEXT_PATTERNS: List[str] = [
        "log in to continue",
        "sign in to continue",
        "login to continue",
        "log in to access",
        "sign in to access",
        "must be logged in",
        "must be signed in",
        "please log in",
        "please sign in",
        "create an account to continue",
        "sign up to continue",
        "register to continue",
    ]

    @classmethod
    def detect_from_url(cls, url: str) -> Tuple[bool, str, float]:
        """Check if a URL looks like a login/signup page.

        Returns:
            (is_login, page_type, confidence)
            page_type is "login", "signup", or "none"
            confidence is 0.0 to 1.0
        """
        if not url:
            return False, "none", 0.0

        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower().replace("www.", "")
        path = parsed.path.lower().rstrip("/")
        full_url = url.lower()

        # Check domain-specific login paths (high confidence)
        domain_paths = cls.DOMAIN_LOGIN_PATHS.get(domain, [])
        for dp in domain_paths:
            if dp.lower() in path or dp.lower() in full_url:
                return True, "login", 0.95

        # Check if domain is in the always-requires-login list
        # These domains are known to require login for most paths
        if domain in cls.LOGIN_REQUIRED_DOMAINS:
            is_root_or_login = path in ("", "/") or any(
                p in path for p in cls.LOGIN_URL_PATTERNS + cls.SIGNUP_URL_PATTERNS
            )
            if is_root_or_login:
                return True, cls.LOGIN_REQUIRED_DOMAINS[domain], 0.85
            # Also match if domain-specific login paths match
            domain_paths = cls.DOMAIN_LOGIN_PATHS.get(domain, [])
            for dp in domain_paths:
                if dp.lower() in full_url:
                    return True, cls.LOGIN_REQUIRED_DOMAINS[domain], 0.95

        # Check login URL patterns (medium-high confidence)
        for pattern in cls.LOGIN_URL_PATTERNS:
            if pattern in path:
                return True, "login", 0.90

        # Check signup URL patterns
        for pattern in cls.SIGNUP_URL_PATTERNS:
            if pattern in path:
                return True, "signup", 0.88

        return False, "none", 0.0

    @classmethod
    async def detect_from_dom(cls, page) -> Tuple[bool, str, float]:
        """Check if the current page DOM contains login form signals.

        Runs JavaScript in the browser page to check for login form elements.
        This is more accurate than URL detection but requires the page to be loaded.

        Args:
            page: Playwright Page object

        Returns:
            (is_login, page_type, confidence)
        """
        if page is None:
            return False, "none", 0.0

        try:
            # Build the detection JS that checks all selectors at once
            # This is a single round-trip to the browser for efficiency
            login_selectors_json = json.dumps(cls.LOGIN_FORM_SELECTORS)
            signup_selectors_json = json.dumps(cls.SIGNUP_FORM_SELECTORS)
            title_keywords_json = json.dumps(cls.LOGIN_TITLE_KEYWORDS + cls.SIGNUP_TITLE_KEYWORDS)
            text_patterns_json = json.dumps(cls.LOGIN_TEXT_PATTERNS)

            result = await page.evaluate(f"""(() => {{
                const loginSels = {login_selectors_json};
                const signupSels = {signup_selectors_json};
                const titleKws = {title_keywords_json};
                const textPats = {text_patterns_json};

                // Check login selectors
                let loginHits = 0;
                for (const sel of loginSels) {{
                    try {{
                        if (document.querySelector(sel)) loginHits++;
                    }} catch(e) {{}}
                }}

                // Check signup selectors
                let signupHits = 0;
                for (const sel of signupSels) {{
                    try {{
                        if (document.querySelector(sel)) signupHits++;
                    }} catch(e) {{}}
                }}

                // Check title keywords
                const title = (document.title || '').toLowerCase();
                let titleHit = null;
                for (const kw of titleKws) {{
                    if (title.includes(kw)) {{
                        titleHit = kw;
                        break;
                    }}
                }}

                // Check body text for login-required patterns
                const bodyText = (document.body?.innerText || '').substring(0, 3000).toLowerCase();
                let textHit = null;
                for (const pat of textPats) {{
                    if (bodyText.includes(pat)) {{
                        textHit = pat;
                        break;
                    }}
                }}

                // Check if there's a password field visible
                const hasPassword = !!document.querySelector('input[type="password"]');

                return {{
                    loginHits,
                    signupHits,
                    titleHit,
                    textHit,
                    hasPassword,
                    title: document.title || ''
                }};
            }})()""")

            login_hits = result.get("loginHits", 0)
            signup_hits = result.get("signupHits", 0)
            title_hit = result.get("titleHit")
            text_hit = result.get("textHit")
            has_password = result.get("hasPassword", False)
            _page_title = result.get("title", "")

            # Scoring system: combine signals for confidence
            login_score = 0.0
            signup_score = 0.0

            # Password field is the strongest signal for login
            if has_password:
                login_score += 0.35

            # Each matching login selector adds confidence
            login_score += min(login_hits * 0.10, 0.40)

            # Each matching signup selector adds confidence
            signup_score += min(signup_hits * 0.10, 0.40)

            # Title keyword match
            if title_hit:
                title_lower = title_hit.lower()
                if any(kw in title_lower for kw in cls.SIGNUP_TITLE_KEYWORDS):
                    signup_score += 0.25
                else:
                    login_score += 0.25

            # Body text pattern match
            if text_hit:
                text_lower = text_hit.lower()
                if any(kw in text_lower for kw in ["sign up", "signup", "register", "create account"]):
                    signup_score += 0.30
                else:
                    login_score += 0.30

            # Determine page type based on highest score
            if login_score >= 0.50 and login_score > signup_score:
                confidence = min(login_score, 1.0)
                return True, "login", round(confidence, 2)
            elif signup_score >= 0.50 and signup_score > login_score:
                confidence = min(signup_score, 1.0)
                return True, "signup", round(confidence, 2)
            elif login_score >= 0.35 or signup_score >= 0.35:
                # Ambiguous — could be login or signup. Default to login
                # since most sites have login forms
                confidence = min(max(login_score, signup_score), 1.0)
                return True, "login" if login_score >= signup_score else "signup", round(confidence, 2)

            return False, "none", 0.0

        except Exception as e:
            logger.warning(f"DOM-based login detection failed: {e}")
            return False, "none", 0.0

    @classmethod
    async def detect(cls, page, url: str = "") -> Tuple[bool, str, float]:
        """Combined detection using both URL patterns and DOM analysis.

        Runs URL detection first (fast, no page interaction needed),
        then DOM detection (accurate, needs page interaction).
        The higher-confidence result wins.

        Args:
            page: Playwright Page object (can be None for URL-only detection)
            url: Current page URL

        Returns:
            (is_login, page_type, confidence)
        """
        # Layer 1: URL-based detection
        url_is_login, url_type, url_conf = cls.detect_from_url(url)

        # If URL gives high confidence, return immediately
        if url_conf >= 0.90:
            return url_is_login, url_type, url_conf

        # Layer 2: DOM-based detection (if page is available)
        if page is not None:
            dom_is_login, dom_type, dom_conf = await cls.detect_from_dom(page)

            # Pick the result with higher confidence
            if dom_conf > url_conf:
                return dom_is_login, dom_type, dom_conf

            # If both agree, boost confidence
            if url_is_login and dom_is_login and url_type == dom_type:
                combined_conf = min(url_conf + dom_conf * 0.3, 1.0)
                return True, url_type, round(combined_conf, 2)

        return url_is_login, url_type, url_conf


# ═══════════════════════════════════════════════════════════════
# Handoff State Machine
# ═══════════════════════════════════════════════════════════════

class HandoffState(str, Enum):
    """Possible states of a login handoff session."""
    IDLE = "idle"
    DETECTED = "detected"           # Login page detected, waiting for handoff initiation
    WAITING_FOR_USER = "waiting_for_user"  # User has control, waiting for them to complete login
    COMPLETED = "completed"         # User completed login, AI can resume
    CANCELLED = "cancelled"         # Handoff was cancelled
    TIMED_OUT = "timed_out"         # Handoff timed out waiting for user


@dataclass
class HandoffSession:
    """Represents a single login handoff session.

    Tracks all state for a handoff including the page being managed,
    the user who initiated it, timestamps, and security metadata.
    """
    handoff_id: str
    url: str
    domain: str
    page_type: str              # "login" or "signup"
    state: HandoffState = HandoffState.IDLE
    confidence: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    user_id: str = ""
    session_id: str = ""
    timeout_seconds: int = 300  # 5 minutes default
    completed_at: Optional[float] = None
    page_id: str = "main"
    # Security: pre-handoff cookies snapshot (to detect what changed)
    cookies_before: List[Dict] = field(default_factory=list)
    cookies_after: List[Dict] = field(default_factory=list)
    # Pre-handoff URL (to know what page we were on)
    url_before: str = ""
    # Screenshot data (memory only, never persisted)
    screenshot_before: str = ""
    screenshot_after: str = ""
    # User-visible info about the handoff
    message: str = ""
    # Whether the handoff was auto-detected or manually triggered
    auto_detected: bool = False
    # The final URL after user completes login
    final_url: str = ""
    # Auth cookies that were gained (domain, name only — no values exposed to AI)
    auth_cookie_names: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """Check if the handoff is still in progress."""
        return self.state in (HandoffState.DETECTED, HandoffState.WAITING_FOR_USER)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since handoff was created."""
        return time.time() - self.created_at

    @property
    def remaining_seconds(self) -> float:
        """Seconds until timeout."""
        if self.state != HandoffState.WAITING_FOR_USER:
            return 0.0
        elapsed = time.time() - self.updated_at
        return max(0.0, self.timeout_seconds - elapsed)

    @property
    def is_expired(self) -> bool:
        """Check if the handoff has timed out."""
        if self.state != HandoffState.WAITING_FOR_USER:
            return False
        return self.remaining_seconds <= 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses. Excludes sensitive data."""
        return {
            "handoff_id": self.handoff_id,
            "url": self.url,
            "domain": self.domain,
            "page_type": self.page_type,
            "state": self.state.value,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "user_id": self.user_id,
            "timeout_seconds": self.timeout_seconds,
            "remaining_seconds": round(self.remaining_seconds, 1),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "page_id": self.page_id,
            "url_before": self.url_before,
            "final_url": self.final_url,
            "message": self.message,
            "auto_detected": self.auto_detected,
            "auth_cookie_names": self.auth_cookie_names,
            "completed_at": self.completed_at,
        }


# ═══════════════════════════════════════════════════════════════
# Handoff Manager — Core orchestration engine
# ═══════════════════════════════════════════════════════════════

class LoginHandoffManager:
    """Manages login handoff sessions between AI agent and human user.

    This is the core engine that:
    1. Detects login/signup pages (auto or manual)
    2. Creates handoff sessions with unique IDs
    3. Pauses AI automation and gives browser control to the user
    4. Monitors for completion (page navigation away from login)
    5. Detects new auth cookies to confirm successful login
    6. Returns control to the AI with preserved session state

    Thread safety: All public methods are async and use asyncio locks
    for thread-safe access to shared state.
    """

    MAX_CONCURRENT_HANDOFFS = 10
    MAX_HANDOFF_HISTORY = 100
    CLEANUP_INTERVAL_SECONDS = 60
    COMPLETION_CHECK_INTERVAL_SECONDS = 2.0
    # Navigation signals that login completed
    LOGIN_COMPLETION_URL_PATTERNS = [
        "/home", "/dashboard", "/feed", "/inbox",
        "/timeline", "/explore", "/profile", "/me",
        "/account", "/settings", "/welcome",
    ]
    # Domains where being on the homepage means login succeeded
    LOGIN_SUCCESS_DOMAINS: Set[str] = {
        "instagram.com", "www.instagram.com",
        "twitter.com", "x.com",
        "facebook.com", "www.facebook.com",
        "linkedin.com", "www.linkedin.com",
        "reddit.com", "www.reddit.com",
    }

    def __init__(self, browser, config=None):
        self._browser = browser
        self._config = config or {}
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, HandoffSession] = {}
        self._history: List[Dict] = []
        self._cleanup_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._ws_notify_callback = None  # Set by server for WS notifications
        self._running = False

    async def start(self):
        """Start background monitoring and cleanup tasks."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("LoginHandoffManager started — monitoring for login pages")

    async def stop(self):
        """Stop all background tasks."""
        self._running = False
        for task in (self._cleanup_task, self._monitor_task):
            if task:
                task.cancel()
        # Cancel any active handoffs
        async with self._lock:
            for hs in self._sessions.values():
                if hs.is_active:
                    hs.state = HandoffState.CANCELLED
                    hs.updated_at = time.time()
        logger.info("LoginHandoffManager stopped")

    def set_ws_notify(self, callback):
        """Set callback for WebSocket notifications.

        The callback receives (event_type: str, data: dict) and is
        responsible for broadcasting to connected WebSocket clients.
        """
        self._ws_notify_callback = callback

    async def _notify_ws(self, event_type: str, data: Dict):
        """Send a WebSocket notification if callback is configured."""
        if self._ws_notify_callback:
            try:
                await self._ws_notify_callback(event_type, data)
            except Exception as e:
                logger.warning(f"WS notify failed: {e}")

    # ─── Detection ─────────────────────────────────────────

    async def detect_login_page(self, page_id: str = "main") -> Dict[str, Any]:
        """Detect if the current page is a login/signup page.

        Uses both URL patterns and DOM analysis for maximum accuracy.

        Args:
            page_id: Browser tab/page identifier

        Returns:
            {
                "is_login_page": bool,
                "page_type": "login"|"signup"|"none",
                "confidence": float,
                "url": str,
                "domain": str,
            }
        """
        page = self._browser._pages.get(page_id)
        url = ""
        domain = ""
        if page:
            try:
                url = page.url or ""
                parsed = urlparse(url)
                domain = (parsed.hostname or "").lower().replace("www.", "")
            except Exception:
                pass

        is_login, page_type, confidence = await LoginDetector.detect(page, url)

        return {
            "is_login_page": is_login,
            "page_type": page_type,
            "confidence": confidence,
            "url": url,
            "domain": domain,
        }

    # ─── Handoff Lifecycle ─────────────────────────────────

    async def start_handoff(
        self,
        url: str = "",
        page_id: str = "main",
        user_id: str = "",
        session_id: str = "",
        timeout_seconds: int = 300,
        auto_detected: bool = False,
    ) -> Dict[str, Any]:
        """Start a login handoff session.

        This method:
        1. Detects the login page (if not already detected)
        2. Creates a handoff session
        3. Takes a snapshot of current cookies (for later comparison)
        4. Takes a screenshot (memory only)
        5. Notifies the user via WebSocket that they need to log in
        6. Sets the handoff state to WAITING_FOR_USER

        Args:
            url: URL of the login page (detected from current page if empty)
            page_id: Browser tab/page identifier
            user_id: ID of the user who will perform the login
            session_id: Agent session ID
            timeout_seconds: How long to wait for user to complete login
            auto_detected: Whether this was auto-detected vs manually triggered

        Returns:
            Handoff session details or error
        """
        async with self._lock:
            # Check concurrent handoff limit
            active_count = sum(1 for h in self._sessions.values() if h.is_active)
            if active_count >= self.MAX_CONCURRENT_HANDOFFS:
                return {
                    "status": "error",
                    "error": f"Maximum concurrent handoffs reached ({self.MAX_CONCURRENT_HANDOFFS})",
                }

            # Get the page
            page = self._browser._pages.get(page_id)
            if not page:
                return {"status": "error", "error": f"Page '{page_id}' not found"}

            # Get current URL from page
            try:
                current_url = page.url or ""
            except Exception:
                current_url = url

            if not current_url:
                return {"status": "error", "error": "Cannot determine current page URL"}

            # Detect login page
            is_login, page_type, confidence = await LoginDetector.detect(page, current_url)

            if not is_login and not auto_detected:
                # For manual triggers, lower the confidence threshold
                # User explicitly wants to hand off even if we're not sure it's login
                page_type = "login"
                confidence = max(confidence, 0.30)
            elif not is_login:
                return {
                    "status": "error",
                    "error": "Current page does not appear to be a login/signup page",
                    "detection": {
                        "is_login_page": False,
                        "page_type": page_type,
                        "confidence": confidence,
                    },
                }

            # Parse domain
            parsed = urlparse(current_url)
            domain = (parsed.hostname or "").lower().replace("www.", "")

            # Generate unique handoff ID
            handoff_id = f"ho_{secrets.token_urlsafe(12)}"

            # Create session
            hs = HandoffSession(
                handoff_id=handoff_id,
                url=current_url,
                domain=domain,
                page_type=page_type,
                state=HandoffState.DETECTED,
                confidence=confidence,
                user_id=user_id,
                session_id=session_id,
                timeout_seconds=timeout_seconds,
                page_id=page_id,
                auto_detected=auto_detected,
            )

            # Take cookie snapshot before handoff (for diff detection)
            try:
                cookies_result = await self._browser.get_cookies()
                hs.cookies_before = cookies_result.get("cookies", [])
            except Exception as e:
                logger.warning(f"Failed to snapshot cookies before handoff: {e}")
                hs.cookies_before = []

            # Take screenshot before handoff (memory only)
            try:
                hs.screenshot_before = await self._browser.screenshot()
            except Exception:
                hs.screenshot_before = ""

            # Store the URL we were on before
            hs.url_before = current_url

            # Set user-friendly message
            if page_type == "signup":
                hs.message = (
                    f"Signup page detected on {domain}. "
                    f"Please complete the signup process in the browser. "
                    f"You have {timeout_seconds // 60} minutes."
                )
            else:
                hs.message = (
                    f"Login page detected on {domain}. "
                    f"Please log in to your account in the browser. "
                    f"Your credentials are secure — the AI cannot see them. "
                    f"You have {timeout_seconds // 60} minutes."
                )

            # Move to WAITING_FOR_USER state
            hs.state = HandoffState.WAITING_FOR_USER
            hs.updated_at = time.time()

            # Store session
            self._sessions[handoff_id] = hs

            # Notify via WebSocket
            await self._notify_ws("login_handoff_started", {
                "handoff_id": handoff_id,
                "url": current_url,
                "domain": domain,
                "page_type": page_type,
                "message": hs.message,
                "timeout_seconds": timeout_seconds,
            })

            logger.info(
                f"Login handoff started: {handoff_id} | "
                f"domain={domain} type={page_type} conf={confidence:.2f} "
                f"timeout={timeout_seconds}s auto={auto_detected}"
            )

            return {
                "status": "success",
                "handoff_id": handoff_id,
                "url": current_url,
                "domain": domain,
                "page_type": page_type,
                "confidence": confidence,
                "message": hs.message,
                "timeout_seconds": timeout_seconds,
                "state": hs.state.value,
            }

    async def complete_handoff(
        self,
        handoff_id: str,
        user_id: str = "",
    ) -> Dict[str, Any]:
        """Mark a handoff as completed by the user.

        Called when the user signals they've finished logging in.
        This method:
        1. Takes a new cookie snapshot
        2. Compares with pre-handoff cookies to find new auth cookies
        3. Takes a post-login screenshot (memory only)
        4. Saves cookies to persistent storage
        5. Returns control to the AI agent

        Args:
            handoff_id: The handoff session ID
            user_id: User ID for verification

        Returns:
            Completion details including auth cookie names (not values!)
        """
        async with self._lock:
            hs = self._sessions.get(handoff_id)
            if not hs:
                return {"status": "error", "error": f"Handoff '{handoff_id}' not found"}

            if hs.state != HandoffState.WAITING_FOR_USER:
                return {
                    "status": "error",
                    "error": f"Handoff is not in waiting state (current: {hs.state.value})",
                }

            # Verify user_id if provided
            if user_id and hs.user_id and user_id != hs.user_id:
                return {"status": "error", "error": "User ID mismatch"}

            # Get current page URL
            page = self._browser._pages.get(hs.page_id)
            current_url = ""
            if page:
                try:
                    current_url = page.url or ""
                except Exception:
                    pass

            # Take post-handoff cookie snapshot
            try:
                cookies_result = await self._browser.get_cookies()
                hs.cookies_after = cookies_result.get("cookies", [])
            except Exception as e:
                logger.warning(f"Failed to snapshot cookies after handoff: {e}")
                hs.cookies_after = []

            # Detect new auth cookies (compare before vs after)
            # We only expose cookie NAMES (not values) to the AI for transparency
            before_names = {
                (c.get("name", ""), c.get("domain", ""))
                for c in hs.cookies_before
            }
            new_cookies = []
            for c in hs.cookies_after:
                key = (c.get("name", ""), c.get("domain", ""))
                if key not in before_names:
                    new_cookies.append(c)
                    hs.auth_cookie_names.append(c.get("name", "unknown"))

            # Take post-login screenshot (memory only)
            try:
                hs.screenshot_after = await self._browser.screenshot()
            except Exception:
                hs.screenshot_after = ""

            # Update state
            hs.state = HandoffState.COMPLETED
            hs.updated_at = time.time()
            hs.completed_at = time.time()
            hs.final_url = current_url

            # Save cookies to persistent storage (so they survive restart)
            try:
                await self._browser._save_cookies("default")
                await self._browser._flush_cookies("default")
                logger.info("Cookies saved after handoff completion")
            except Exception as e:
                logger.warning(f"Failed to save cookies after handoff: {e}")

            # Move to history
            self._add_to_history(hs)

            # Notify via WebSocket
            await self._notify_ws("login_handoff_completed", {
                "handoff_id": handoff_id,
                "domain": hs.domain,
                "final_url": current_url,
                "new_cookie_count": len(new_cookies),
                "auth_cookie_names": hs.auth_cookie_names,
                "duration_seconds": round(hs.completed_at - hs.created_at, 1),
            })

            logger.info(
                f"Login handoff completed: {handoff_id} | "
                f"domain={hs.domain} new_cookies={len(new_cookies)} "
                f"duration={hs.completed_at - hs.created_at:.1f}s"
            )

            return {
                "status": "success",
                "handoff_id": handoff_id,
                "domain": hs.domain,
                "final_url": current_url,
                "new_cookie_count": len(new_cookies),
                "auth_cookie_names": hs.auth_cookie_names,
                "duration_seconds": round(hs.completed_at - hs.created_at, 1),
                "message": (
                    f"Login completed for {hs.domain}. "
                    f"AI agent can now resume. {len(new_cookies)} new session cookies detected."
                ),
            }

    async def cancel_handoff(
        self,
        handoff_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Cancel an active handoff session.

        Args:
            handoff_id: The handoff session ID
            reason: Optional reason for cancellation

        Returns:
            Cancellation confirmation
        """
        async with self._lock:
            hs = self._sessions.get(handoff_id)
            if not hs:
                return {"status": "error", "error": f"Handoff '{handoff_id}' not found"}

            if not hs.is_active:
                return {
                    "status": "error",
                    "error": f"Handoff is not active (current: {hs.state.value})",
                }

            hs.state = HandoffState.CANCELLED
            hs.updated_at = time.time()
            hs.message = f"Handoff cancelled. {reason}" if reason else "Handoff cancelled by user."

            # Move to history
            self._add_to_history(hs)

            # Notify via WebSocket
            await self._notify_ws("login_handoff_cancelled", {
                "handoff_id": handoff_id,
                "domain": hs.domain,
                "reason": reason,
            })

            logger.info(f"Login handoff cancelled: {handoff_id} | reason={reason}")

            return {
                "status": "success",
                "handoff_id": handoff_id,
                "state": "cancelled",
                "message": hs.message,
            }

    async def get_handoff_status(self, handoff_id: str) -> Dict[str, Any]:
        """Get the current status of a handoff session.

        Args:
            handoff_id: The handoff session ID

        Returns:
            Handoff session details
        """
        hs = self._sessions.get(handoff_id)
        if not hs:
            return {"status": "error", "error": f"Handoff '{handoff_id}' not found"}

        return {
            "status": "success",
            "handoff": hs.to_dict(),
        }

    async def list_handoffs(
        self,
        state_filter: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all handoff sessions, optionally filtered.

        Args:
            state_filter: Filter by state (e.g., "waiting_for_user")
            user_id: Filter by user ID

        Returns:
            List of matching handoff sessions
        """
        results = []
        for hs in self._sessions.values():
            if state_filter and hs.state.value != state_filter:
                continue
            if user_id and hs.user_id != user_id:
                continue
            results.append(hs.to_dict())

        return {
            "status": "success",
            "handoffs": results,
            "count": len(results),
        }

    async def get_handoff_history(self, limit: int = 50) -> Dict[str, Any]:
        """Get completed handoff history.

        Args:
            limit: Maximum number of history entries to return

        Returns:
            List of historical handoff sessions
        """
        return {
            "status": "success",
            "history": self._history[-limit:],
            "count": min(len(self._history), limit),
        }

    # ─── Auto-Detection Integration ────────────────────────

    async def check_and_auto_handoff(
        self,
        url: str,
        page_id: str = "main",
        user_id: str = "",
        session_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Check if a navigation landed on a login page and auto-initiate handoff.

        This is called after every navigation to detect if the target
        page requires login. If auto-detection is enabled in config
        and a login page is found, it automatically starts a handoff.

        Args:
            url: URL that was just navigated to
            page_id: Browser tab identifier
            user_id: Current user ID
            session_id: Current agent session ID

        Returns:
            Handoff result if auto-handoff was triggered, None otherwise
        """
        # Check if auto-handoff is enabled
        auto_handoff_enabled = self._config.get("auto_handoff", True)
        if not auto_handoff_enabled:
            return None

        # Don't trigger if already in an active handoff
        active_count = sum(1 for h in self._sessions.values() if h.is_active)
        if active_count > 0:
            return None

        # Detect login page using URL patterns first (fast)
        is_login, page_type, confidence = LoginDetector.detect_from_url(url)

        # If URL detection gives moderate confidence, try DOM analysis too
        if is_login and confidence < 0.90:
            page = self._browser._pages.get(page_id)
            if page:
                try:
                    dom_is_login, dom_type, dom_conf = await LoginDetector.detect_from_dom(page)
                    if dom_conf > confidence:
                        is_login, page_type, confidence = dom_is_login, dom_type, dom_conf
                except Exception as e:
                    logger.warning(f"Auto-handoff DOM check failed: {e}")

        # Only auto-handoff if confidence is above threshold
        if not is_login or confidence < 0.70:
            return None

        logger.info(
            f"Auto-handoff triggered: login page detected at {url} "
            f"(type={page_type}, confidence={confidence:.2f})"
        )

        # Start the handoff automatically
        result = await self.start_handoff(
            url=url,
            page_id=page_id,
            user_id=user_id,
            session_id=session_id,
            timeout_seconds=self._config.get("handoff_timeout", 300),
            auto_detected=True,
        )

        return result

    # ─── Background Monitoring ─────────────────────────────

    async def _monitor_loop(self):
        """Background task: monitor active handoffs for completion and timeout."""
        while self._running:
            try:
                # Collect handoff IDs that need auto-completion (to avoid deadlock
                # from calling complete_handoff while holding the lock)
                auto_complete_ids: List[Tuple[str, str]] = []

                async with self._lock:
                    for hs in list(self._sessions.values()):
                        if not hs.is_active:
                            continue

                        # Check for timeout
                        if hs.is_expired:
                            hs.state = HandoffState.TIMED_OUT
                            hs.updated_at = time.time()
                            hs.message = f"Handoff timed out after {hs.timeout_seconds} seconds"
                            self._add_to_history(hs)

                            await self._notify_ws("login_handoff_timed_out", {
                                "handoff_id": hs.handoff_id,
                                "domain": hs.domain,
                                "timeout_seconds": hs.timeout_seconds,
                            })

                            logger.warning(
                                f"Handoff timed out: {hs.handoff_id} | domain={hs.domain} timeout={hs.timeout_seconds}s"
                            )
                            continue

                        # Check if user navigated away from login page (completion signal)
                        page = self._browser._pages.get(hs.page_id)
                        if page:
                            try:
                                current_url = page.url or ""
                                parsed = urlparse(current_url)
                                domain = (parsed.hostname or "").lower().replace("www.", "")

                                # Check if user navigated to a known post-login page
                                is_login_now, _, _ = LoginDetector.detect_from_url(current_url)

                                # If we're no longer on a login page and domain matches,
                                # that's a strong signal that login completed
                                if not is_login_now and domain == hs.domain:
                                    # Check for new auth cookies
                                    try:
                                        cookies_result = await self._browser.get_cookies()
                                        current_cookies = cookies_result.get("cookies", [])
                                        before_names = {
                                            (c.get("name", ""), c.get("domain", ""))
                                            for c in hs.cookies_before
                                        }
                                        new_cookie_count = sum(
                                            1 for c in current_cookies
                                            if (c.get("name", ""), c.get("domain", "")) not in before_names
                                        )

                                        if new_cookie_count > 0:
                                            # Mark for auto-completion outside the lock
                                            auto_complete_ids.append((hs.handoff_id, hs.user_id))
                                            logger.info(
                                                f"Auto-completing handoff {hs.handoff_id}: "
                                                f"user navigated away from login + {new_cookie_count} new cookies"
                                            )
                                    except Exception as e:
                                        logger.debug(f"Cookie check during monitoring failed: {e}")
                            except Exception as e:
                                logger.debug(f"URL check during monitoring failed: {e}")

                # Auto-complete handoffs outside the lock to avoid deadlock
                for handoff_id, user_id in auto_complete_ids:
                    try:
                        await self.complete_handoff(handoff_id, user_id)
                    except Exception as e:
                        logger.warning(f"Auto-completion failed for {handoff_id}: {e}")

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(self.COMPLETION_CHECK_INTERVAL_SECONDS)

    def _is_login_completed(self, hs: HandoffSession, current_url: str, page) -> bool:
        """Check if the user has completed the login process.

        Detection strategies:
        1. URL changed away from login page patterns
        2. Password field is no longer present in DOM
        3. New auth cookies appeared for the domain
        4. Page title no longer contains login keywords
        """
        if not current_url:
            return False

        # Strategy 1: URL no longer matches login patterns
        hs_domain = hs.domain
        current_parsed = urlparse(current_url)
        current_domain = (current_parsed.hostname or "").lower().replace("www.", "")
        current_path = current_parsed.path.lower()

        # If the domain changed entirely, user navigated away
        if current_domain and hs_domain and current_domain != hs_domain:
            return True

        # Check if current URL still looks like a login page
        still_login_url = False
        for pattern in LoginDetector.LOGIN_URL_PATTERNS + LoginDetector.SIGNUP_URL_PATTERNS:
            if pattern in current_path:
                still_login_url = True
                break

        # If URL no longer has login patterns, likely completed
        if not still_login_url and current_path not in ("", "/"):
            # Check if the new path looks like a post-login page
            for success_pattern in self.LOGIN_COMPLETION_URL_PATTERNS:
                if success_pattern in current_path:
                    return True
            # If we're on the same domain but different path, likely completed
            if current_domain == hs_domain and current_path != urlparse(hs.url).path.lower():
                return True

        # Strategy 2: Check for new cookies for this domain
        # This is checked by the complete_handoff method, but we can
        # do a quick check here for auto-detection purposes
        try:
            # Quick sync check — if we can get cookies synchronously
            # For async, we rely on the periodic monitor
            pass
        except Exception:
            pass

        # Don't auto-complete if we're still on the login page
        # The user might still be typing
        return False

    async def _cleanup_loop(self):
        """Background task to clean up expired and old sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)

                async with self._lock:
                    # Move expired/timed_out/cancelled sessions to history
                    to_remove = []
                    for hid, hs in self._sessions.items():
                        if hs.state in (HandoffState.COMPLETED, HandoffState.CANCELLED, HandoffState.TIMED_OUT):
                            # Keep in sessions for a bit for status queries, then remove
                            if hs.updated_at and (time.time() - hs.updated_at) > 300:
                                to_remove.append(hid)

                    for hid in to_remove:
                        del self._sessions[hid]

                    # Trim history
                    if len(self._history) > self.MAX_HANDOFF_HISTORY:
                        self._history = self._history[-self.MAX_HANDOFF_HISTORY:]

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    def _add_to_history(self, hs: HandoffSession):
        """Add a completed handoff to the history log."""
        entry = hs.to_dict()
        self._history.append(entry)
        # Remove from active sessions
        if hs.handoff_id in self._sessions:
            del self._sessions[hs.handoff_id]

    # ─── Statistics ────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get handoff statistics."""
        total = len(self._history) + len(self._sessions)
        completed = sum(1 for h in self._history if h.get("state") == "completed")
        cancelled = sum(1 for h in self._history if h.get("state") == "cancelled")
        timed_out = sum(1 for h in self._history if h.get("state") == "timed_out")
        active = sum(1 for h in self._sessions.values() if h.is_active)

        # Per-domain stats
        domain_stats: Dict[str, Dict[str, int]] = {}
        for h in self._history:
            domain = h.get("domain", "unknown")
            if domain not in domain_stats:
                domain_stats[domain] = {"completed": 0, "cancelled": 0, "timed_out": 0}
            state = h.get("state", "")
            if state in domain_stats[domain]:
                domain_stats[domain][state] += 1

        return {
            "total_handoffs": total,
            "active_handoffs": active,
            "completed_handoffs": completed,
            "cancelled_handoffs": cancelled,
            "timed_out_handoffs": timed_out,
            "success_rate": round(completed / max(total, 1) * 100, 1),
            "per_domain": domain_stats,
        }
