# Contributing to Agent X

Thank you for your interest in contributing to Agent X! This document provides guidelines and instructions for contributing.

## Development Setup

1. **Fork and clone:**
   ```bash
   git clone https://github.com/unknownsorcerer007/Agent-X.git
   cd Agent-X
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   python -m patchright install chromium
   ```

4. **Install pre-commit hooks (optional but recommended):**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Branch Naming

- `feat/description` — New features
- `fix/description` — Bug fixes
- `docs/description` — Documentation changes
- `refactor/description` — Code refactoring
- `test/description` — Test additions/changes
- `chore/description` — Maintenance tasks

## Commit Style

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`

Examples:
- `fix(stealth): align WebGL vendor with browser profile platform`
- `feat(browser): add Firefox fallback engine`
- `docs(readme): update installation instructions`

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add/update tests if applicable
4. Run `pytest tests/ -v` to verify
5. Update relevant documentation
6. Open a PR with a clear description

## Code Standards

- **Python:** PEP 8 compliant, type hints encouraged
- **No secrets:** Never commit API keys, tokens, or passwords
- **Logging:** Use structured logging (`logger.info/debug/warning/error`) not `print()`
- **Error handling:** Use specific exceptions, avoid bare `except:`
- **Security:** Validate all inputs, use parameterized queries, sanitize JS code

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_all.py -v -k test_name

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Questions?

- Open a [Discussion](https://github.com/unknownsorcerer007/Agent-X/discussions) for questions
- Open an [Issue](https://github.com/unknownsorcerer007/Agent-X/issues) for bugs
- Follow us on X: [@Unknown339264](https://x.com/Unknown339264)
