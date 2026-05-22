"""
Agent-OS Authentication Handler
Handles auto-login, session cookie injection, and local credential vault.
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional, List
from cryptography.fernet import Fernet

logger = logging.getLogger("agent-os.auth")


class AuthHandler:
    """Manages authentication for automated browsing."""

    def __init__(self, config):
        self.config = config
        self.vault_path = Path(os.path.expanduser("~/.agent-os/vault.enc"))
        self._key = self._get_or_create_key()
        self._fernet = Fernet(self._key)

    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key for the vault.

        Key is stored in XDG_DATA_HOME or ~/.local/share/agent-os/ to
        separate it from the vault file in ~/.agent-os/.
        Falls back to ~/.agent-os/.vault_key if XDG path unavailable.
        """
        # Prefer XDG data directory (separates key from config)
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        key_path = Path(xdg_data) / "agent-os" / ".vault_key"

        if key_path.exists():
            return key_path.read_bytes()

        # Fallback: check legacy location
        legacy_path = Path(os.path.expanduser("~/.agent-os/.vault_key"))
        if legacy_path.exists():
            # Migrate to new location
            key = legacy_path.read_bytes()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            key_path.chmod(0o600)
            try:
                legacy_path.unlink()
                logger.info("Migrated vault key from legacy location to XDG data dir")
            except Exception:
                pass
            return key

        # Generate new key
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        return key

    def save_credentials(self, domain: str, credentials: Dict[str, str]):
        """Save encrypted credentials for a domain."""
        vault = self._load_vault()
        vault[domain] = credentials
        encrypted = self._fernet.encrypt(json.dumps(vault).encode())
        self.vault_path.write_bytes(encrypted)
        logger.info(f"Credentials saved for {domain}")

    def get_credentials(self, domain: str) -> Optional[Dict[str, str]]:
        """Get credentials for a domain."""
        vault = self._load_vault()
        return vault.get(domain)

    def list_domains(self) -> List[str]:
        """List domains with saved credentials."""
        return list(self._load_vault().keys())

    def delete_credentials(self, domain: str):
        """Delete credentials for a domain."""
        vault = self._load_vault()
        if domain in vault:
            del vault[domain]
            encrypted = self._fernet.encrypt(json.dumps(vault).encode())
            self.vault_path.write_bytes(encrypted)

    def _load_vault(self) -> Dict:
        """Load and decrypt the credential vault."""
        if not self.vault_path.exists():
            return {}
        try:
            encrypted = self.vault_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
            return {}

    async def auto_login(self, browser, url: str, domain: str) -> Dict:
        """Attempt auto-login using stored credentials."""
        creds = self.get_credentials(domain)
        if not creds:
            return {"status": "error", "error": f"No credentials stored for {domain}"}

        await browser.navigate(url)

        # Common login form selectors - find email and password fields
        email_selectors = [
            'input[type="email"]', 'input[name="email"]', 'input[name="username"]',
            'input[id="email"]', 'input[id="username"]', 'input[placeholder*="email" i]',
            'input[placeholder*="username" i]', 'input[type="text"][name*="user"]',
            'input[type="text"][name*="email"]', 'input[type="text"][name*="login"]',
        ]
        password_selectors = [
            'input[type="password"]', 'input[name="password"]',
            'input[id="password"]', 'input[placeholder*="password" i]',
        ]

        # Find the actual selectors that exist on the page
        email_sel = None
        password_sel = None
        for sel in email_selectors:
            _el_resp = await browser.evaluate_js(f"""(() => {{ return !!document.querySelector('{sel}'); }})()""")
            el = _el_resp.get("result") if isinstance(_el_resp, dict) and _el_resp.get("status") == "success" else _el_resp
            if el:
                email_sel = sel
                break
        for sel in password_selectors:
            _el_resp = await browser.evaluate_js(f"""(() => {{ return !!document.querySelector('{sel}'); }})()""")
            el = _el_resp.get("result") if isinstance(_el_resp, dict) and _el_resp.get("status") == "success" else _el_resp
            if el:
                password_sel = sel
                break

        if not email_sel or not password_sel:
            return {"status": "error", "error": "Could not find login form fields"}

        # Fill using the found selectors
        email_value = creds.get("username", creds.get("email", ""))
        password_value = creds.get("password", "")

        result = await browser.fill_form({
            email_sel: email_value,
            password_sel: password_value,
        })

        # Try to click submit
        submit_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Sign in")', 'button:has-text("Log in")',
            'button:has-text("Login")', 'button:has-text("Submit")',
        ]
        for sel in submit_selectors:
            click_result = await browser.click(sel)
            if click_result.get("status") == "success":
                break

        return {"status": "success", "domain": domain, "filled_fields": result.get("filled", [])}
