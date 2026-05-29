# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.0.x   | :white_check_mark: |
| < 4.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Agent X, please report it responsibly.

**Please DO NOT:**
- Open a public issue for security vulnerabilities
- Share details in public forums or social media

**Instead:**
- Contact us via X/Twitter: [@Unknown339264](https://x.com/Unknown339264)
- Or email security concerns to the project maintainer

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours and work with you to verify and address the issue.

## Security Best Practices for Users

1. **Keep your `.env` file secure** — Never commit it, use `chmod 600 .env`
2. **Rotate tokens regularly** — Use `python main.py --agent-token` with a new token
3. **Disable legacy auth in production** — Set `allow_legacy_token_auth: false`
4. **Use HTTPS in production** — Deploy behind a reverse proxy with TLS
5. **Keep dependencies updated** — Run `pip install -U -r requirements.txt` regularly
6. **Monitor logs** — Watch for unusual authentication patterns

## Security Features

Agent X includes several built-in security features:

- **bcrypt password hashing** (12 rounds)
- **JWT access + refresh tokens** with configurable expiry
- **API key scoped permissions** with rate limiting
- **Encrypted cookie storage** using Fernet (AES-128-CBC + HMAC)
- **Input validation** on all endpoints
- **JS code sanitization** for `evaluate-js` endpoint
- **CORS origin validation**
- **Audit logging** for all authentication events
