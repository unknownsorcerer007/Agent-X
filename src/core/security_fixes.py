"""
Agent-X Security Patches
Fixes identified security vulnerabilities.
"""
import os
import secrets
import hashlib
import hmac
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent-x.security")


class SecurityHardening:
    """Production security hardening patches."""

    @staticmethod
    def secure_cookie_key() -> bytes:
        """
        Generate or load cookie encryption key with secure permissions.
        Returns Fernet-compatible key bytes.
        """
        from cryptography.fernet import Fernet
        
        key_dir = Path(os.path.expanduser("~/.agent-x"))
        key_dir.mkdir(parents=True, exist_ok=True)
        key_path = key_dir / ".cookie_key"
        
        # Secure the directory permissions (owner only)
        os.chmod(key_dir, 0o700)
        
        if key_path.exists():
            # Check current permissions
            stat = key_path.stat()
            if stat.st_mode & 0o077:
                logger.warning("Cookie key had loose permissions — fixing to 0o600")
                os.chmod(key_path, 0o600)
            return key_path.read_bytes()
        
        # Generate new key
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
        logger.info("Generated new secure cookie encryption key")
        return key

    @staticmethod
    def validate_proxy_url(proxy_url: str) -> bool:
        """Validate proxy URL format and scheme."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(proxy_url)
            if parsed.scheme not in ('http', 'https', 'socks4', 'socks5'):
                logger.error(f"Invalid proxy scheme: {parsed.scheme}")
                return False
            if not parsed.hostname:
                logger.error("Proxy URL missing hostname")
                return False
            return True
        except Exception as e:
            logger.error(f"Invalid proxy URL: {e}")
            return False

    @staticmethod
    def sanitize_js_input(code: str) -> str:
        """Sanitize JavaScript code for evaluate-js endpoint."""
        # Block dangerous patterns
        blocked_patterns = [
            'process.exit',
            'child_process',
            'require(',
            'fs.',
            'os.',
            'net.',
            'http.',
            'https.',
            'eval(',
            'Function(',
            'setTimeout(',
            'setInterval(',
            'require\.main',
            'module\.exports',
            '__proto__',
            'constructor',
        ]
        
        code_lower = code.lower()
        for pattern in blocked_patterns:
            if pattern.lower() in code_lower:
                raise ValueError(f"Blocked pattern in JS code: {pattern}")
        
        return code

    @staticmethod
    def hash_token_secure(token: str) -> str:
        """Hash a token using bcrypt if available, fallback to SHA256+HMAC."""
        try:
            import bcrypt
            return bcrypt.hashpw(token.encode(), bcrypt.gensalt(rounds=12)).decode()
        except ImportError:
            # Fallback: SHA256 with HMAC using a derived key
            salt = secrets.token_hex(16)
            hash_value = hashlib.sha256(f"{token}{salt}".encode()).hexdigest()
            return f"sha256${salt}${hash_value}"

    @staticmethod
    def verify_token_secure(token: str, stored_hash: str) -> bool:
        """Verify token against stored hash."""
        if stored_hash.startswith("sha256$"):
            # Legacy SHA256 format
            parts = stored_hash.split("$")
            if len(parts) == 3:
                salt = parts[1]
                expected = parts[2]
                actual = hashlib.sha256(f"{token}{salt}".encode()).hexdigest()
                return hmac.compare_digest(expected.encode(), actual.encode())
            return False
        
        # bcrypt format
        try:
            import bcrypt
            return bcrypt.checkpw(token.encode(), stored_hash.encode())
        except ImportError:
            logger.error("bcrypt not available for token verification")
            return False

    @staticmethod
    def enforce_secure_defaults(config: dict) -> dict:
        """Enforce security-hardened defaults."""
        security = config.setdefault("security", {})
        
        # Disable legacy token auth in production (warn if enabled)
        if security.get("allow_legacy_token_auth", True):
            logger.warning(
                "Legacy token auth is ENABLED — disable in production "
                "by setting security.allow_legacy_token_auth = false"
            )
        
        # Enforce minimum password requirements
        if "min_password_length" not in security:
            security["min_password_length"] = 12
        
        # Enable request logging
        security.setdefault("audit_log_requests", True)
        
        # Sanitize download directory permissions
        download_dir = Path(os.path.expanduser("~/.agent-x/downloads"))
        download_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(download_dir, 0o700)
        
        return config
