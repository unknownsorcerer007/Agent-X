import logging
from typing import Optional, Any
from src.core.cdp_stealth import CDPStealthInjector
from src.core.stealth_god import GodModeStealth

logger = logging.getLogger("agent-os.adaptive-stealth")

class AdaptiveStealthManager:
    """
    Dynamically routes stealth injection based on target URL.
    - Normal URLs: CDP Stealth (High Performance, standard evasion)
    - High-Security URLs (Cloudflare, Datadome, Kasada): God Mode (Ultimate Evasion, heavier JS)
    """
    
    HIGH_SECURITY_DOMAINS = [
        "cloudflare",
        "datadome",
        "kasada",
        "perimeterx",
        "akamai",
        "incapsula",
        "imperva",
        "hcaptcha",
        "recaptcha",
        "turnstile",
        "threatmetrix",
        "iovation",
        "sardine"
    ]
    
    def __init__(self, cdp_stealth: CDPStealthInjector, god_mode_stealth: GodModeStealth):
        self.cdp_stealth = cdp_stealth
        self.god_mode_stealth = god_mode_stealth
        
    def is_high_security(self, url: str) -> bool:
        url_lower = url.lower()
        for domain in self.HIGH_SECURITY_DOMAINS:
            if domain in url_lower:
                return True
        return False
        
    async def inject_stealth(self, context, page, url: str, fingerprint: dict) -> bool:
        """
        Injects the appropriate stealth layer for the target URL.
        Returns True if successful.
        """
        try:
            if self.is_high_security(url):
                logger.info(f"[AdaptiveStealth] High-security target detected for {url}. Engaging GOD MODE.")
                # Inject God Mode
                god_ok = await self.god_mode_stealth.inject_into_page(
                    page=page,
                    page_id="main"
                )
                if not god_ok:
                    logger.warning("[AdaptiveStealth] God Mode injection failed, falling back to CDP.")
                    return await self.cdp_stealth.inject_into_page(page=page, page_id="main", fingerprint=fingerprint)
                return True
            else:
                logger.debug(f"[AdaptiveStealth] Standard target detected for {url}. Engaging CDP Stealth.")
                # Inject CDP Stealth
                cdp_ok = await self.cdp_stealth.inject_into_page(
                    page=page,
                    page_id="main",
                    fingerprint=fingerprint
                )
                if not cdp_ok:
                    logger.warning("[AdaptiveStealth] CDP Stealth injection failed, falling back to God Mode.")
                    return await self.god_mode_stealth.inject_into_page(page=page, page_id="main")
                return True
                
        except Exception as e:
            logger.error(f"[AdaptiveStealth] Failed to inject stealth: {e}")
            return False
