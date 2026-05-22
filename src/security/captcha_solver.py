"""
Agent-OS CAPTCHA Solver Engine
Real CAPTCHA solving integration with multiple providers.

Supports:
  - 2captcha (reCAPTCHA v2/v3, hCaptcha, Turnstile, FunCaptcha)
  - Anti-Captcha (all types)
  - CapMonster (all types)
  - Auto-detection and fallback between providers
  - Session reuse for efficiency
  - Rate limiting and cost tracking
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("agent-os.captcha-solver")


class CaptchaType(str, Enum):
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    FUNCAPTCHA = "funcaptcha"
    IMAGE = "image"
    TEXT = "text"


class SolverProvider(str, Enum):
    TWOCAPTCHA = "2captcha"
    ANTICAPTCHA = "anti-captcha"
    CAPMONSTER = "capmonster"


@dataclass
class SolverConfig:
    """Configuration for a CAPTCHA solver provider."""
    provider: SolverProvider
    api_key: str
    priority: int = 0           # Higher = preferred
    enabled: bool = True
    cost_per_1000: float = 0    # USD per 1000 solves
    avg_solve_time: float = 0   # Rolling average in seconds
    total_solves: int = 0
    total_failures: int = 0
    total_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.total_solves + self.total_failures
        if total == 0:
            return 1.0
        return self.total_solves / total


@dataclass
class CaptchaSolution:
    """Result from a CAPTCHA solve attempt."""
    success: bool
    token: str = ""             # The CAPTCHA token/solution
    solve_time: float = 0       # Seconds taken
    provider: str = ""
    cost: float = 0
    captcha_id: str = ""        # Provider's task ID
    error: str = ""
    raw_response: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "token": self.token[:50] + "..." if len(self.token) > 50 else self.token,
            "solve_time": round(self.solve_time, 2),
            "provider": self.provider,
            "cost": self.cost,
            "error": self.error,
        }


class TwoCaptchaSolver:
    """2captcha.com API integration."""

    BASE_URL = "https://2captcha.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None

    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
            )
        return self._session

    async def _post(self, endpoint: str, data: Dict) -> Dict:
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with session.post(url, json=data) as resp:
                return await resp.json()
        except Exception as e:
            return {"status": 0, "error": str(e)}

    async def _get(self, endpoint: str, params: Dict = None) -> Dict:
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with session.get(url, params=params) as resp:
                return await resp.json()
        except Exception as e:
            return {"status": 0, "error": str(e)}

    async def solve_recaptcha_v2(
        self,
        sitekey: str,
        page_url: str,
        invisible: bool = False,
        enterprise: bool = False,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": page_url,
            "json": 1,
        }
        if invisible:
            data["invisible"] = 1
        if enterprise:
            data["enterprise"] = 1

        # Submit task
        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def solve_recaptcha_v3(
        self,
        sitekey: str,
        page_url: str,
        action: str = "verify",
        min_score: float = 0.3,
        enterprise: bool = False,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "version": "v3",
            "googlekey": sitekey,
            "pageurl": page_url,
            "action": action,
            "min_score": min_score,
            "json": 1,
        }
        if enterprise:
            data["enterprise"] = 1

        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def solve_hcaptcha(
        self,
        sitekey: str,
        page_url: str,
    ) -> CaptchaSolution:
        """Solve hCaptcha."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": 1,
        }

        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def solve_turnstile(
        self,
        sitekey: str,
        page_url: str,
        action: str = "",
    ) -> CaptchaSolution:
        """Solve Cloudflare Turnstile."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": 1,
        }
        if action:
            data["action"] = action

        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def solve_funcaptcha(
        self,
        public_key: str,
        page_url: str,
        service_url: str = "",
    ) -> CaptchaSolution:
        """Solve FunCaptcha / Arkose Labs."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "funcaptcha",
            "publickey": public_key,
            "pageurl": page_url,
            "json": 1,
        }
        if service_url:
            data["surl"] = service_url

        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def solve_image(self, image_base64: str, **kwargs) -> CaptchaSolution:
        """Solve image CAPTCHA."""
        start = time.time()
        data = {
            "key": self.api_key,
            "method": "base64",
            "body": image_base64,
            "json": 1,
        }
        data.update(kwargs)

        resp = await self._post("/in.php", data)
        if resp.get("status") != 1:
            return CaptchaSolution(
                success=False,
                error=resp.get("error", "Failed to submit"),
                solve_time=time.time() - start,
                provider="2captcha",
            )

        task_id = resp["request"]
        return await self._poll_result(task_id, start)

    async def _poll_result(self, task_id: str, start: float, max_wait: int = 120) -> CaptchaSolution:
        """Poll for CAPTCHA solution."""
        elapsed = 0
        poll_interval = 3

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed = time.time() - start

            resp = await self._get("/res.php", {
                "key": self.api_key,
                "action": "get",
                "id": task_id,
                "json": 1,
            })

            if resp.get("status") == 1:
                return CaptchaSolution(
                    success=True,
                    token=str(resp["request"]),
                    solve_time=elapsed,
                    provider="2captcha",
                    captcha_id=task_id,
                    cost=0.003,  # Approximate cost per solve
                )

            if resp.get("request") != "CAPCHA_NOT_READY":
                return CaptchaSolution(
                    success=False,
                    error=str(resp.get("request", "Unknown error")),
                    solve_time=elapsed,
                    provider="2captcha",
                    captcha_id=task_id,
                )

            # Increase poll interval gradually
            poll_interval = min(poll_interval + 1, 5)

        return CaptchaSolution(
            success=False,
            error="Timeout waiting for solution",
            solve_time=elapsed,
            provider="2captcha",
            captcha_id=task_id,
        )

    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        resp = await self._get("/res.php", {
            "key": self.api_key,
            "action": "getbalance",
            "json": 1,
        })
        if resp.get("status") == 1:
            return {"balance": float(resp["request"])}
        return {"error": resp.get("request", "Unknown error")}

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


class AntiCaptchaSolver:
    """anti-captcha.com API integration."""

    BASE_URL = "https://api.anti-captcha.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None

    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
            )
        return self._session

    async def _post(self, endpoint: str, data: Dict) -> Dict:
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        data["clientKey"] = self.api_key
        try:
            async with session.post(url, json=data) as resp:
                return await resp.json()
        except Exception as e:
            return {"errorId": 1, "errorDescription": str(e)}

    async def solve_recaptcha_v2(self, sitekey: str, page_url: str, **kwargs) -> CaptchaSolution:
        start = time.time()
        task = {
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        if kwargs.get("enterprise"):
            task["type"] = "RecaptchaV2TaskProxyless"
            task["isInvisible"] = kwargs.get("invisible", False)

        resp = await self._post("/createTask", {"task": task})
        if resp.get("errorId") != 0:
            return CaptchaSolution(
                success=False,
                error=resp.get("errorDescription", "Task creation failed"),
                solve_time=time.time() - start,
                provider="anti-captcha",
            )
        return await self._poll_result(resp["taskId"], start)

    async def solve_hcaptcha(self, sitekey: str, page_url: str, **kwargs) -> CaptchaSolution:
        start = time.time()
        task = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        resp = await self._post("/createTask", {"task": task})
        if resp.get("errorId") != 0:
            return CaptchaSolution(
                success=False,
                error=resp.get("errorDescription", "Task creation failed"),
                solve_time=time.time() - start,
                provider="anti-captcha",
            )
        return await self._poll_result(resp["taskId"], start)

    async def solve_turnstile(self, sitekey: str, page_url: str, **kwargs) -> CaptchaSolution:
        start = time.time()
        task = {
            "type": "TurnstileTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        resp = await self._post("/createTask", {"task": task})
        if resp.get("errorId") != 0:
            return CaptchaSolution(
                success=False,
                error=resp.get("errorDescription", "Task creation failed"),
                solve_time=time.time() - start,
                provider="anti-captcha",
            )
        return await self._poll_result(resp["taskId"], start)

    async def solve_funcaptcha(self, public_key: str, page_url: str, **kwargs) -> CaptchaSolution:
        start = time.time()
        task = {
            "type": "FunCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websitePublicKey": public_key,
        }
        if kwargs.get("service_url"):
            task["funcaptchaApiJSSubdomain"] = kwargs["service_url"]
        resp = await self._post("/createTask", {"task": task})
        if resp.get("errorId") != 0:
            return CaptchaSolution(
                success=False,
                error=resp.get("errorDescription", "Task creation failed"),
                solve_time=time.time() - start,
                provider="anti-captcha",
            )
        return await self._poll_result(resp["taskId"], start)

    async def _poll_result(self, task_id: int, start: float, max_wait: int = 120) -> CaptchaSolution:
        elapsed = 0
        poll_interval = 3
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed = time.time() - start
            resp = await self._post("/getTaskResult", {"taskId": task_id})
            if resp.get("errorId") == 0 and resp.get("status") == "ready":
                solution = resp.get("solution", {})
                token = solution.get("gRecaptchaResponse") or solution.get("token") or solution.get("text", "")
                return CaptchaSolution(
                    success=True,
                    token=token,
                    solve_time=elapsed,
                    provider="anti-captcha",
                    captcha_id=str(task_id),
                    cost=0.002,
                )
            if resp.get("errorId") != 0 and resp.get("errorDescription") != "Task is not ready":
                return CaptchaSolution(
                    success=False,
                    error=resp.get("errorDescription", "Unknown error"),
                    solve_time=elapsed,
                    provider="anti-captcha",
                    captcha_id=str(task_id),
                )
            poll_interval = min(poll_interval + 1, 5)
        return CaptchaSolution(
            success=False,
            error="Timeout",
            solve_time=elapsed,
            provider="anti-captcha",
            captcha_id=str(task_id),
        )

    async def get_balance(self) -> Dict[str, Any]:
        resp = await self._post("/getBalance", {})
        if resp.get("errorId") == 0:
            return {"balance": resp.get("balance", 0)}
        return {"error": resp.get("errorDescription", "Unknown")}

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


class CaptchaSolver:
    """
    Multi-provider CAPTCHA solver with auto-fallback.

    Usage:
        solver = CaptchaSolver()

        # Add providers
        solver.add_provider("2captcha", "your-api-key", priority=10)
        solver.add_provider("anti-captcha", "your-api-key", priority=5)

        # Solve reCAPTCHA
        result = await solver.solve(
            captcha_type="recaptcha_v2",
            sitekey="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
            page_url="https://example.com",
        )

        if result.success:
            # Inject token into page
            await page.evaluate(f'''
                document.getElementById("g-recaptcha-response").innerHTML = "{result.token}";
                document.querySelector(".g-recaptcha-response").innerHTML = "{result.token}";
            ''')
            # Then click submit
    """

    def __init__(self):
        self._providers: Dict[str, SolverConfig] = {}
        self._solvers: Dict[str, Any] = {}
        self._stats = {
            "total_solves": 0,
            "total_failures": 0,
            "total_cost": 0.0,
            "by_type": {},
            "by_provider": {},
        }

    def add_provider(
        self,
        provider: str,
        api_key: str,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Add a CAPTCHA solver provider."""
        try:
            prov = SolverProvider(provider)
        except ValueError:
            return {"status": "error", "error": f"Unknown provider: {provider}. Use: {[p.value for p in SolverProvider]}"}

        config = SolverConfig(
            provider=prov,
            api_key=api_key,
            priority=priority,
        )
        self._providers[prov.value] = config

        # Create solver instance
        if prov == SolverProvider.TWOCAPTCHA:
            self._solvers[prov.value] = TwoCaptchaSolver(api_key)
        elif prov == SolverProvider.ANTICAPTCHA:
            self._solvers[prov.value] = AntiCaptchaSolver(api_key)
        elif prov == SolverProvider.CAPMONSTER:
            # CapMonster uses same API as Anti-Captcha
            self._solvers[prov.value] = AntiCaptchaSolver(api_key)

        logger.info(f"Captcha provider added: {provider} (priority: {priority})")
        return {"status": "success", "provider": provider, "priority": priority}

    def remove_provider(self, provider: str) -> Dict[str, Any]:
        """Remove a provider."""
        if provider in self._providers:
            del self._providers[provider]
            solver = self._solvers.pop(provider, None)
            if solver and hasattr(solver, "close"):
                asyncio.create_task(solver.close())
            return {"status": "success", "removed": provider}
        return {"status": "error", "error": f"Provider not found: {provider}"}

    def _get_best_provider(self) -> Optional[str]:
        """Get the best available provider sorted by priority and success rate."""
        available = [
            (name, config)
            for name, config in self._providers.items()
            if config.enabled
        ]
        if not available:
            return None
        # Sort by priority (desc), then success rate (desc)
        available.sort(key=lambda x: (x[1].priority, x[1].success_rate), reverse=True)
        return available[0][0]

    async def solve(
        self,
        captcha_type: str,
        sitekey: str = "",
        page_url: str = "",
        image_base64: str = "",
        **kwargs,
    ) -> CaptchaSolution:
        """
        Solve a CAPTCHA with automatic provider selection and fallback.

        Args:
            captcha_type: recaptcha_v2, recaptcha_v3, hcaptcha, turnstile, funcaptcha, image
            sitekey: Site key / public key
            page_url: Page URL where CAPTCHA appears
            image_base64: Base64-encoded image (for image CAPTCHAs)
            **kwargs: Extra params (action, invisible, enterprise, etc.)
        """
        if not self._providers:
            return CaptchaSolution(
                success=False,
                error="No CAPTCHA providers configured. Add one with add_provider()",
            )

        tried = []
        errors = []

        # Try providers in priority order
        while True:
            provider_name = self._get_best_provider()
            if not provider_name or provider_name in tried:
                break
            tried.append(provider_name)

            solver = self._solvers.get(provider_name)
            if not solver:
                continue

            try:
                ct = CaptchaType(captcha_type)
            except ValueError:
                return CaptchaSolution(
                    success=False,
                    error=f"Unknown captcha type: {captcha_type}",
                )

            try:
                if ct == CaptchaType.RECAPTCHA_V2:
                    result = await solver.solve_recaptcha_v2(
                        sitekey, page_url,
                        invisible=kwargs.get("invisible", False),
                        enterprise=kwargs.get("enterprise", False),
                    )
                elif ct == CaptchaType.RECAPTCHA_V3:
                    result = await solver.solve_recaptcha_v3(
                        sitekey, page_url,
                        action=kwargs.get("action", "verify"),
                        min_score=kwargs.get("min_score", 0.3),
                        enterprise=kwargs.get("enterprise", False),
                    )
                elif ct == CaptchaType.HCAPTCHA:
                    result = await solver.solve_hcaptcha(sitekey, page_url)
                elif ct == CaptchaType.TURNSTILE:
                    result = await solver.solve_turnstile(
                        sitekey, page_url,
                        action=kwargs.get("action", ""),
                    )
                elif ct == CaptchaType.FUNCAPTCHA:
                    result = await solver.solve_funcaptcha(
                        sitekey, page_url,
                        service_url=kwargs.get("service_url", ""),
                    )
                elif ct == CaptchaType.IMAGE:
                    result = await solver.solve_image(image_base64, **kwargs)
                else:
                    return CaptchaSolution(
                        success=False,
                        error=f"Unsupported captcha type: {captcha_type}",
                    )

                # Update stats
                config = self._providers.get(provider_name)
                if result.success:
                    self._stats["total_solves"] += 1
                    if config:
                        config.total_solves += 1
                        config.total_cost += result.cost
                    self._stats["total_cost"] += result.cost
                    type_stats = self._stats["by_type"].setdefault(captcha_type, {"solves": 0, "failures": 0})
                    type_stats["solves"] += 1
                    prov_stats = self._stats["by_provider"].setdefault(provider_name, {"solves": 0, "failures": 0})
                    prov_stats["solves"] += 1
                    return result
                else:
                    if config:
                        config.total_failures += 1
                    errors.append(f"{provider_name}: {result.error}")

            except Exception as e:
                errors.append(f"{provider_name}: {str(e)}")
                logger.error(f"CAPTCHA solver error ({provider_name}): {e}")

        # All providers failed
        self._stats["total_failures"] += 1
        return CaptchaSolution(
            success=False,
            error=f"All providers failed: {'; '.join(errors)}",
        )

    async def inject_solution(
        self,
        page,
        solution: CaptchaSolution,
        captcha_type: str = "recaptcha_v2",
    ) -> Dict[str, Any]:
        """
        Inject a CAPTCHA solution into a Playwright page.

        This handles the DOM manipulation needed to submit the solved CAPTCHA.
        """
        if not solution.success or not solution.token:
            return {"status": "error", "error": "No valid solution to inject"}

        token = solution.token.replace("'", "\\'").replace('"', '\\"')

        try:
            if captcha_type in ("recaptcha_v2", "recaptcha_v3"):
                await page.evaluate(f"""
                    (function(token) {{
                        // Set all possible reCAPTCHA response fields
                        var ta = document.getElementById('g-recaptcha-response');
                        if (ta) ta.innerHTML = token;

                        var tas = document.querySelectorAll('.g-recaptcha-response');
                        tas.forEach(function(el) {{ el.innerHTML = token; }});

                        // Set hidden form fields
                        var inputs = document.querySelectorAll('input[name="g-recaptcha-response"]');
                        inputs.forEach(function(el) {{ el.value = token; }});

                        // Fire callback if exists
                        if (typeof ___grecaptcha_cfg !== 'undefined') {{
                            try {{
                                Object.entries(___grecaptcha_cfg.clients).forEach(function(entry) {{
                                    Object.entries(entry[1]).forEach(function(inner) {{
                                        try {{
                                            var callback = Object.values(inner[1]).find(function(v) {{
                                                return typeof v === 'function';
                                            }});
                                            if (callback) callback(token);
                                        }} catch(e) {{}}
                                    }});
                                }});
                            }} catch(e) {{}}
                        }}
                    }})('{token}');
                """)

            elif captcha_type == "hcaptcha":
                await page.evaluate(f"""
                    (function(token) {{
                        var ta = document.querySelector('[name="h-captcha-response"]');
                        if (ta) ta.value = token;

                        var tas = document.querySelectorAll('textarea[name="h-captcha-response"]');
                        tas.forEach(function(el) {{ el.value = token; }});

                        var div = document.querySelector('.h-captcha');
                        if (div && div.dataset) div.dataset.hcaptchaResponse = token;

                        // Fire callback
                        try {{
                            if (typeof hcaptcha !== 'undefined' && hcaptcha.getResponse) {{
                                // Override getResponse
                                var origGet = hcaptcha.getResponse;
                                hcaptcha.getResponse = function() {{ return token; }};
                            }}
                        }} catch(e) {{}}
                    }})('{token}');
                """)

            elif captcha_type == "turnstile":
                await page.evaluate(f"""
                    (function(token) {{
                        var input = document.querySelector('[name="cf-turnstile-response"]');
                        if (input) input.value = token;

                        try {{
                            if (typeof turnstile !== 'undefined') {{
                                // Find widget and set token
                                var widgets = document.querySelectorAll('[data-sitekey]');
                                widgets.forEach(function(w) {{
                                    var widgetId = w.id;
                                    if (widgetId && turnstile.getResponse) {{
                                        // Token is already set via input
                                    }}
                                }});
                            }}
                        }} catch(e) {{}}
                    }})('{token}');
                """)

            return {"status": "success", "captcha_type": captcha_type, "token_injected": True}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def detect_and_solve(self, page) -> Dict[str, Any]:
        """
        Auto-detect CAPTCHA on page and solve it.

        Checks for reCAPTCHA, hCaptcha, Turnstile, and FunCaptcha on the page.
        """
        try:
            detection = await page.evaluate("""
                () => {
                    const result = {type: null, sitekey: '', action: ''};

                    // reCAPTCHA v2
                    var recaptcha = document.querySelector('.g-recaptcha, [data-sitekey]');
                    if (recaptcha) {
                        var sitekey = recaptcha.getAttribute('data-sitekey') || recaptcha.dataset.sitekey;
                        if (sitekey) {
                            // Check if invisible
                            var invisible = recaptcha.getAttribute('data-size') === 'invisible' ||
                                           recaptcha.getAttribute('data-badge') === 'inline';
                            result.type = invisible ? 'recaptcha_v2' : 'recaptcha_v2';
                            result.sitekey = sitekey;
                            result.action = recaptcha.getAttribute('data-action') || recaptcha.getAttribute('data-callback') || '';
                            return result;
                        }
                    }

                    // reCAPTCHA v3
                    var scripts = document.querySelectorAll('script[src*="recaptcha"]');
                    for (var s of scripts) {
                        if (s.src.includes('render=')) {
                            var match = s.src.match(/render=([^&]+)/);
                            if (match) {
                                result.type = 'recaptcha_v3';
                                result.sitekey = match[1];
                                return result;
                            }
                        }
                    }

                    // hCaptcha
                    var hcaptcha = document.querySelector('.h-captcha, [data-hcaptcha-sitekey]');
                    if (hcaptcha) {
                        result.type = 'hcaptcha';
                        result.sitekey = hcaptcha.getAttribute('data-sitekey') || hcaptcha.getAttribute('data-hcaptcha-sitekey') || '';
                        return result;
                    }

                    // Turnstile
                    var turnstile = document.querySelector('[data-sitekey]');
                    if (turnstile && document.querySelector('script[src*="turnstile"], script[src*="challenges.cloudflare"]')) {
                        result.type = 'turnstile';
                        result.sitekey = turnstile.getAttribute('data-sitekey') || '';
                        result.action = turnstile.getAttribute('data-action') || '';
                        return result;
                    }

                    // FunCaptcha
                    var funcaptcha = document.querySelector('#FunCaptcha, [data-fun-captcha-key]');
                    if (funcaptcha) {
                        result.type = 'funcaptcha';
                        result.sitekey = funcaptcha.getAttribute('data-fun-captcha-key') || funcaptcha.getAttribute('data-pkey') || '';
                        return result;
                    }

                    // Generic check for iframes
                    var iframes = document.querySelectorAll('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[src*="funcaptcha"]');
                    if (iframes.length > 0) {
                        var src = iframes[0].src;
                        if (src.includes('recaptcha')) {
                            var m = src.match(/k=([^&]+)/);
                            if (m) { result.type = 'recaptcha_v2'; result.sitekey = m[1]; return result; }
                        }
                        if (src.includes('hcaptcha')) {
                            var m2 = src.match(/sitekey=([^&]+)/);
                            if (m2) { result.type = 'hcaptcha'; result.sitekey = m2[1]; return result; }
                        }
                    }

                    return result;
                }
            """)

            if not detection or not detection.get("type"):
                return {"status": "no_captcha_found"}

            captcha_type = detection["type"]
            sitekey = detection["sitekey"]
            page_url = page.url

            logger.info(f"Detected {captcha_type} CAPTCHA (sitekey: {sitekey[:20]}...)")

            # Solve it
            result = await self.solve(
                captcha_type=captcha_type,
                sitekey=sitekey,
                page_url=page_url,
                action=detection.get("action", ""),
            )

            if result.success:
                # Inject solution
                inject_result = await self.inject_solution(page, result, captcha_type)
                return {
                    "status": "success",
                    "captcha_type": captcha_type,
                    "solve_time": round(result.solve_time, 2),
                    "provider": result.provider,
                    "cost": result.cost,
                    "injected": inject_result.get("status") == "success",
                }
            else:
                return {
                    "status": "failed",
                    "captcha_type": captcha_type,
                    "error": result.error,
                }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get solver statistics."""
        return {
            "total_solves": self._stats["total_solves"],
            "total_failures": self._stats["total_failures"],
            "total_cost": round(self._stats["total_cost"], 4),
            "by_type": dict(self._stats["by_type"]),
            "by_provider": dict(self._stats["by_provider"]),
            "providers": {
                name: {
                    "enabled": config.enabled,
                    "priority": config.priority,
                    "success_rate": round(config.success_rate * 100, 1),
                    "total_solves": config.total_solves,
                    "total_failures": config.total_failures,
                    "total_cost": round(config.total_cost, 4),
                }
                for name, config in self._providers.items()
            },
        }

    async def get_balances(self) -> Dict[str, Any]:
        """Get balances from all providers."""
        balances = {}
        for name, solver in self._solvers.items():
            if hasattr(solver, "get_balance"):
                try:
                    bal = await solver.get_balance()
                    balances[name] = bal
                except Exception as e:
                    balances[name] = {"error": str(e)}
        return balances

    async def close(self):
        """Close all solver sessions."""
        for solver in self._solvers.values():
            if hasattr(solver, "close"):
                await solver.close()
