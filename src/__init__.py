"""
Agent-X Package Entry

Injects a dynamic compatibility patch redirecting any imports of the standard 'playwright'
library to the stealth-patched 'patchright' library. This avoids namespace conflicts
and ensures that all parts of the application run with the anti-detection binaries.
"""
import sys
import logging

logger = logging.getLogger("agent-x.patchright-alias")

try:
    import patchright
    # Redirect base playwright module
    sys.modules['playwright'] = patchright
    
    # Redirect async API
    try:
        import patchright.async_api
        sys.modules['playwright.async_api'] = patchright.async_api
    except ImportError:
        pass
        
    # Redirect sync API
    try:
        import patchright.sync_api
        sys.modules['playwright.sync_api'] = patchright.sync_api
    except ImportError:
        pass

    logger.debug("Successfully aliased 'playwright' -> 'patchright'")
except ImportError:
    logger.warning("Failed to import patchright during namespace aliasing setup")
