"""
Agent-X CAPTCHA Solver Engine - Production-Grade Dual Solver
Real CAPTCHA solving integration with local OCR and AI Visual models.

Supports:
  - Local offline OCR (ddddocr)
  - Multimodal AI Visual solving (Gemini, OpenAI, Anthropic)
  - Interactive Visual solving (checkboxes & grids) using Human Mimicry
  - 2captcha (as fallback/legacy option)
  - Anti-Captcha (as fallback/legacy option)
  - Auto-detection and fallback between providers
"""
import asyncio
import logging
import time
import os
import re
import random
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("agent-x.captcha-solver")


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
    DDDDOCR = "ddddocr"
    AI_VISUAL = "ai_visual"


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


class DdddocrLocalSolver:
    """Local offline CAPTCHA solver using ddddocr."""

    def __init__(self):
        self._ocr = None
        self._available = False
        try:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
            self._available = True
            logger.info("Local ddddocr CAPTCHA solver initialized")
        except ImportError:
            logger.debug("Local ddddocr package is not installed")
        except Exception as e:
            logger.warning(f"Local ddddocr init failed: {e}")

    @property
    def available(self) -> bool:
        return self._available

    async def solve_image(self, image_base64: str) -> CaptchaSolution:
        import base64
        start = time.monotonic()
        if not self._available:
            return CaptchaSolution(
                success=False,
                error="ddddocr is not available (import failed or package missing)",
                solve_time=time.monotonic() - start,
                provider="ddddocr"
            )
        try:
            image_bytes = base64.b64decode(image_base64)
            loop = asyncio.get_running_loop()
            # Run the OCR engine in a worker thread since classification is CPU-bound
            result = await loop.run_in_executor(None, self._ocr.classification, image_bytes)
            if result:
                result = "".join(result.split())
                return CaptchaSolution(
                    success=True,
                    token=result,
                    solve_time=time.monotonic() - start,
                    provider="ddddocr",
                    cost=0.0
                )
            return CaptchaSolution(
                success=False,
                error="ddddocr returned empty result",
                solve_time=time.monotonic() - start,
                provider="ddddocr"
            )
        except Exception as e:
            logger.warning(f"ddddocr solve failed: {e}")
            return CaptchaSolution(
                success=False,
                error=str(e),
                solve_time=time.monotonic() - start,
                provider="ddddocr"
            )

    async def close(self):
        pass


class AIVisualSolver:
    """Multimodal LLM CAPTCHA Solver using direct HTTP requests to Gemini, OpenAI, or Anthropic."""

    def __init__(self):
        self._session = None

    async def _get_session(self):
        if self._session is None:
            import httpx
            self._session = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._session

    async def solve_image(self, image_base64: str) -> CaptchaSolution:
        """Solve CAPTCHA using the first available visual LLM provider."""
        start = time.time()

        # 1. Google Gemini API (preferred)
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            logger.info("Solving CAPTCHA using Gemini 2.0 Visual Engine...")
            try:
                session = await self._get_session()
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": (
                                        "Solve this CAPTCHA. Identify and output ONLY the letters and/or numbers "
                                        "visible in this image, with absolutely no formatting, spaces, comments, "
                                        "or explanations. If there are math symbols (e.g. 5+3 or 10-2), perform the "
                                        "calculation and return only the final number."
                                    )
                                },
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": image_base64
                                    }
                                }
                            ]
                        }
                    ]
                }
                resp = await session.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        text = "".join(text.split())
                        return CaptchaSolution(
                            success=True,
                            token=text,
                            solve_time=time.time() - start,
                            provider="ai_visual_gemini",
                            cost=0.0
                        )
                    except (KeyError, IndexError) as err:
                        logger.warning(f"Failed to parse Gemini vision response: {err}")
                else:
                    logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"Gemini Vision solver failed: {e}")

        # 2. OpenAI Vision API (fallback)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("Solving CAPTCHA using OpenAI GPT-4o-mini Visual Engine...")
            try:
                session = await self._get_session()
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Solve this CAPTCHA. Identify and output ONLY the letters and/or numbers "
                                        "visible in this image, with absolutely no formatting, spaces, comments, "
                                        "or explanations. If there are math symbols, calculate the result and return it."
                                    )
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 50,
                    "temperature": 0.0
                }
                resp = await session.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    text = "".join(text.split())
                    return CaptchaSolution(
                        success=True,
                        token=text,
                        solve_time=time.time() - start,
                        provider="ai_visual_openai",
                        cost=0.0002
                    )
                else:
                    logger.warning(f"OpenAI API returned status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"OpenAI Vision solver failed: {e}")

        # 3. Anthropic Vision API (fallback)
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            logger.info("Solving CAPTCHA using Anthropic Claude 3.5 Sonnet Visual Engine...")
            try:
                session = await self._get_session()
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 50,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Solve this CAPTCHA. Identify and output ONLY the letters and/or numbers "
                                        "visible in this image, with absolutely no formatting, spaces, comments, "
                                        "or explanations. If there are math symbols, calculate the result and return it."
                                    )
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": image_base64
                                    }
                                }
                            ]
                        }
                    ]
                }
                resp = await session.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["content"][0]["text"].strip()
                    text = "".join(text.split())
                    return CaptchaSolution(
                        success=True,
                        token=text,
                        solve_time=time.time() - start,
                        provider="ai_visual_anthropic",
                        cost=0.0003
                    )
                else:
                    logger.warning(f"Anthropic API returned status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"Anthropic Vision solver failed: {e}")

        return CaptchaSolution(
            success=False,
            error="No visual LLM provider API keys found in environment variables.",
            solve_time=time.time() - start,
            provider="ai_visual"
        )

    async def close(self):
        if self._session:
            await self._session.aclose()
            self._session = None


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
                    cost=0.003,
                )

            if resp.get("request") != "CAPCHA_NOT_READY":
                return CaptchaSolution(
                    success=False,
                    error=str(resp.get("request", "Unknown error")),
                    solve_time=elapsed,
                    provider="2captcha",
                    captcha_id=task_id,
                )

            poll_interval = min(poll_interval + 1, 5)

        return CaptchaSolution(
            success=False,
            error="Timeout waiting for solution",
            solve_time=elapsed,
            provider="2captcha",
            captcha_id=task_id,
        )

    async def get_balance(self) -> Dict[str, Any]:
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
    Enforces local OCR (ddddocr) first, falling back to AIVisualSolver.
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

        # 1. Register local OCR if available
        self.add_provider("ddddocr", "local_free", priority=100)

        # 2. Register AI Visual solver if vision API keys exist
        if any(os.getenv(k) for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")):
            self.add_provider("ai_visual", "ai_free_or_owned", priority=90)

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
            self._solvers[prov.value] = AntiCaptchaSolver(api_key)
        elif prov == SolverProvider.DDDDOCR:
            self._solvers[prov.value] = DdddocrLocalSolver()
        elif prov == SolverProvider.AI_VISUAL:
            self._solvers[prov.value] = AIVisualSolver()

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
                # If solver doesn't support the requested non-image captcha format, skip it
                if ct != CaptchaType.IMAGE:
                    if not hasattr(solver, f"solve_{captcha_type}"):
                        errors.append(f"{provider_name}: does not support token-solving for {captcha_type}")
                        continue

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
                    result = await solver.solve_image(image_base64)
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
        if not solution.success or not solution.token:
            return {"status": "error", "error": "No valid solution to inject"}

        token = solution.token.replace("'", "\\'").replace('"', '\\"')

        try:
            if captcha_type in ("recaptcha_v2", "recaptcha_v3"):
                await page.evaluate(f"""
                    (function(token) {{
                        var ta = document.getElementById('g-recaptcha-response');
                        if (ta) ta.innerHTML = token;

                        var tas = document.querySelectorAll('.g-recaptcha-response');
                        tas.forEach(function(el) {{ el.innerHTML = token; }});

                        var inputs = document.querySelectorAll('input[name="g-recaptcha-response"]');
                        inputs.forEach(function(el) {{ el.value = token; }});

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

                        try {{
                            if (typeof hcaptcha !== 'undefined' && hcaptcha.getResponse) {{
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
                    }})('{token}');
                """)

            return {"status": "success", "captcha_type": captcha_type, "token_injected": True}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def detect_and_solve(self, page) -> Dict[str, Any]:
        """
        Auto-detect CAPTCHA on page and solve it. Falls back to interactive visual
        solving using visual LLMs if token-based solvers are missing or failed.
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
                            var invisible = recaptcha.getAttribute('data-size') === 'invisible' ||
                                           recaptcha.getAttribute('data-badge') === 'inline';
                            result.type = 'recaptcha_v2';
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

            # First, try to solve via standard configured solvers (like 2captcha/anticaptcha if API keys are configured)
            result = None
            if any(p in self._providers for p in ("2captcha", "anti-captcha", "capmonster")):
                result = await self.solve(
                    captcha_type=captcha_type,
                    sitekey=sitekey,
                    page_url=page_url,
                    action=detection.get("action", ""),
                )

            # If token solver succeeded, inject solution
            if result and result.success:
                inject_result = await self.inject_solution(page, result, captcha_type)
                return {
                    "status": "success",
                    "captcha_type": captcha_type,
                    "solve_time": round(result.solve_time, 2),
                    "provider": result.provider,
                    "cost": result.cost,
                    "injected": inject_result.get("status") == "success",
                }

            # If token solvers are missing, failed, or skipped, fall back to interactive visual solving via LLM!
            if "ai_visual" in self._providers:
                visual_result = await self.solve_interactive_visual(page, captcha_type, detection)
                if visual_result.get("success"):
                    return {
                        "status": "success",
                        "captcha_type": captcha_type,
                        "solve_time": round(visual_result.get("solve_time", 0.0), 2),
                        "provider": "ai_visual",
                        "cost": 0.0,
                        "injected": True,
                    }
                else:
                    return {
                        "status": "failed",
                        "captcha_type": captcha_type,
                        "error": visual_result.get("error", "Interactive visual solver failed"),
                    }

            return {
                "status": "failed",
                "captcha_type": captcha_type,
                "error": "No token solvers available and visual AI solver was not triggered.",
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def solve_interactive_visual(
        self,
        page,
        captcha_type: str,
        detection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Solve reCAPTCHA, hCaptcha, or Turnstile visually by clicking checkboxes
        and using visual LLMs to solve grid/image selection challenges.
        """
        start_time = time.time()
        logger.info(f"Starting interactive visual solver for {captcha_type}...")

        try:
            if captcha_type in ("recaptcha_v2", "recaptcha_v3"):
                # 1. Look for anchor iframe (checkbox)
                anchor_frame_selector = "iframe[src*='recaptcha/api2/anchor']"
                try:
                    await page.wait_for_selector(anchor_frame_selector, timeout=5000)
                    anchor_element = await page.query_selector(anchor_frame_selector)
                    if anchor_element:
                        logger.info("Found reCAPTCHA anchor iframe. Clicking checkbox...")
                        box = await anchor_element.bounding_box()
                        if box:
                            await self._click_with_mimicry(page, box["x"] + 30, box["y"] + box["height"] / 2)
                            await asyncio.sleep(2.0)
                except Exception as e:
                    logger.debug(f"reCAPTCHA anchor checkbox click skipped/failed: {e}")

                # 2. Check if image challenge frame appeared
                bframe_selector = "iframe[src*='recaptcha/api2/bframe']"
                try:
                    await page.wait_for_selector(bframe_selector, timeout=3000)
                    bframe_element = await page.query_selector(bframe_selector)
                    if bframe_element:
                        logger.info("reCAPTCHA image challenge popped up. Solving visually...")
                        success = await self._solve_grid_challenge(page, bframe_element, "recaptcha")
                        return {"success": success, "solve_time": time.time() - start_time}
                except Exception as e:
                    logger.debug(f"No active reCAPTCHA image challenge frame found: {e}")

                return {"success": True, "solve_time": time.time() - start_time}

            elif captcha_type == "hcaptcha":
                # 1. Click hCaptcha checkbox
                anchor_selector = "iframe[src*='hcaptcha.com/box']"
                try:
                    await page.wait_for_selector(anchor_selector, timeout=5000)
                    anchor_element = await page.query_selector(anchor_selector)
                    if anchor_element:
                        logger.info("Found hCaptcha anchor. Clicking checkbox...")
                        box = await anchor_element.bounding_box()
                        if box:
                            await self._click_with_mimicry(page, box["x"] + 30, box["y"] + box["height"] / 2)
                            await asyncio.sleep(2.5)
                except Exception as e:
                    logger.debug(f"hCaptcha checkbox click skipped/failed: {e}")

                # 2. Check if challenge frame popped up
                challenge_selector = "iframe[src*='hcaptcha.com/secshow']"
                try:
                    await page.wait_for_selector(challenge_selector, timeout=3000)
                    challenge_element = await page.query_selector(challenge_selector)
                    if challenge_element:
                        logger.info("hCaptcha visual challenge popped up. Solving visually...")
                        success = await self._solve_grid_challenge(page, challenge_element, "hcaptcha")
                        return {"success": success, "solve_time": time.time() - start_time}
                except Exception as e:
                    logger.debug(f"No active hCaptcha challenge frame found: {e}")

                return {"success": True, "solve_time": time.time() - start_time}

            elif captcha_type == "turnstile":
                turnstile_selector = "iframe[src*='challenges.cloudflare.com']"
                try:
                    await page.wait_for_selector(turnstile_selector, timeout=5000)
                    element = await page.query_selector(turnstile_selector)
                    if element:
                        logger.info("Found Turnstile iframe. Clicking checkbox center...")
                        box = await element.bounding_box()
                        if box:
                            await self._click_with_mimicry(page, box["x"] + 45, box["y"] + box["height"] / 2)
                            await asyncio.sleep(3.0)
                            return {"success": True, "solve_time": time.time() - start_time}
                except Exception as e:
                    logger.debug(f"Turnstile interaction skipped: {e}")

        except Exception as err:
            logger.error(f"Interactive visual solver error: {err}")

        return {"success": False, "error": "Visual interactive solve failed"}

    async def _click_with_mimicry(self, page, x: float, y: float):
        """Simulate human-like mouse movement and click at (x, y) coordinates."""
        from src.security.human_mimicry import HumanMimicry
        mimic = HumanMimicry()

        # Start from a random position
        start_x = random.uniform(10.0, 100.0)
        start_y = random.uniform(10.0, 100.0)

        path = mimic.mouse_path(start_x, start_y, x, y)
        for px, py in path:
            await page.mouse.move(px, py)
            await asyncio.sleep(mimic.mouse_delay())

        await asyncio.sleep(mimic.pre_click_pause())
        await page.mouse.down()
        await asyncio.sleep(mimic.click_delay())
        await page.mouse.up()

    async def _solve_grid_challenge(self, page, iframe_element, provider_type: str) -> bool:
        """Capture screenshot of the grid challenge, analyze with vision API, and execute clicks."""
        box = await iframe_element.bounding_box()
        if not box:
            return False

        # 1. Capture challenge screenshot as base64
        import base64
        import json
        screenshot_bytes = await iframe_element.screenshot()
        image_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # 2. Get content frame
        frame = await iframe_element.content_frame()
        if not frame:
            logger.warning("Could not access content frame of challenge iframe")
            return False

        # 3. Retrieve challenge text
        challenge_text = ""
        try:
            if provider_type == "recaptcha":
                el = await frame.query_selector(".rc-imageselect-desc-wrapper")
                if el:
                    challenge_text = await el.inner_text()
            elif provider_type == "hcaptcha":
                el = await frame.query_selector(".challenge-title")
                if el:
                    challenge_text = await el.inner_text()
        except Exception:
            pass

        if not challenge_text:
            challenge_text = "Select all images matching the subject."

        logger.info(f"Challenge instruction: {challenge_text.strip()}")

        prompt = (
            f"This is a {provider_type} CAPTCHA challenge grid: '{challenge_text.strip()}'.\n"
            "Identify the 1-indexed row and column coordinates of all cells in the grid matching the instruction.\n"
            "Output your answer ONLY as a JSON array of [row, col] coordinates, e.g. [[1,2], [3,1]]. "
            "Do not include markdown blocks, explanation, or any other characters."
        )

        resp_text = await self._call_vision_api(image_base64, prompt)
        if not resp_text:
            logger.warning("Visual LLM response is empty")
            return False

        try:
            match = re.search(r"\[\s*\[.*\]\s*\]", resp_text, re.DOTALL)
            if match:
                cells = json.loads(match.group(0))
            else:
                cells = json.loads(resp_text.strip())
            logger.info(f"LLM grid cell coordinates: {cells}")
        except Exception as err:
            logger.warning(f"Error parsing LLM response '{resp_text}': {err}")
            return False

        # Determine grid size (estimate based on coordinates)
        max_val = 3
        for r, c in cells:
            max_val = max(max_val, r, c)
        grid_size = 4 if max_val > 3 else 3

        # Locate grid element bounds
        grid_box = None
        try:
            grid_el = await frame.query_selector(".rc-imageselect-table-3x3, .rc-imageselect-table-4x4, .challenge-container, #task-image")
            if grid_el:
                grid_box = await grid_el.bounding_box()
        except Exception:
            pass

        if not grid_box:
            grid_box = {
                "x": 0,
                "y": 0,
                "width": box["width"],
                "height": box["height"] * 0.75
            }

        cell_width = grid_box["width"] / grid_size
        cell_height = grid_box["height"] / grid_size

        for row, col in cells:
            cell_x = grid_box["x"] + (col - 0.5) * cell_width
            cell_y = grid_box["y"] + (row - 0.5) * cell_height

            abs_x = box["x"] + cell_x
            abs_y = box["y"] + cell_y
            logger.info(f"Interactive click Cell ({row}, {col}) at absolute: ({abs_x}, {abs_y})")
            await self._click_with_mimicry(page, abs_x, abs_y)
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # Click submit button
        submit_btn = None
        try:
            submit_btn = await frame.query_selector("#recaptcha-verify-button, #submit-button, .button-submit")
        except Exception:
            pass

        if submit_btn:
            s_box = await submit_btn.bounding_box()
            if s_box:
                abs_sx = box["x"] + s_box["x"] + s_box["width"] / 2
                abs_sy = box["y"] + s_box["y"] + s_box["height"] / 2
                logger.info(f"Clicking Verify/Submit at ({abs_sx}, {abs_sy})")
                await self._click_with_mimicry(page, abs_sx, abs_sy)
                await asyncio.sleep(2.0)
                return True

        return False

    async def _call_vision_api(self, image_base64: str, prompt: str) -> Optional[str]:
        """Wrapper calling direct Vision LLM HTTP endpoints based on active credentials."""
        solver = self._solvers.get("ai_visual")
        if not solver:
            return None

        # Gemini
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            try:
                session = await solver._get_session()
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": image_base64
                                    }
                                }
                            ]
                        }
                    ]
                }
                resp = await session.post(url, json=payload)
                if resp.status_code == 200:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
            except Exception as e:
                logger.warning(f"Interactive Gemini Vision API call failed: {e}")

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                session = await solver._get_session()
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 150,
                    "temperature": 0.0
                }
                resp = await session.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"Interactive OpenAI Vision API call failed: {e}")

        # Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                session = await solver._get_session()
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 150,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": image_base64
                                    }
                                }
                            ]
                        }
                    ]
                }
                resp = await session.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json()["content"][0]["text"].strip()
            except Exception as e:
                logger.warning(f"Interactive Anthropic Vision API call failed: {e}")

        return None

    def get_stats(self) -> Dict[str, Any]:
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
        for solver in self._solvers.values():
            if hasattr(solver, "close"):
                await solver.close()
