import pytest
import os
from unittest import mock
from src.security.captcha_solver import (
    CaptchaSolver,
    DdddocrLocalSolver,
    AIVisualSolver,
    CaptchaSolution,
    SolverProvider,
)


def test_solver_initialization_default():
    """Verify that CaptchaSolver initializes default providers (local OCR and AI Visual placeholder)."""
    solver = CaptchaSolver()
    
    # Ensure ddddocr local provider is registered (default behavior)
    assert "ddddocr" in solver._providers
    assert isinstance(solver._solvers["ddddocr"], DdddocrLocalSolver)
    assert solver._providers["ddddocr"].priority == 100


def test_solver_fallback_chain(monkeypatch):
    """Verify that ddddocr is chosen over ai_visual due to higher priority, and mock visual fallbacks."""
    # Force mock API keys to ensure ai_visual is registered
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-gemini-key")
    
    solver = CaptchaSolver()
    
    assert "ddddocr" in solver._providers
    assert "ai_visual" in solver._providers
    
    # Best provider should be ddddocr (priority 100 > 90)
    best = solver._get_best_provider()
    assert best == "ddddocr"


@pytest.mark.asyncio
async def test_ddddocr_not_installed_fallback():
    """Verify fallback behavior if ddddocr is unavailable or raises an exception."""
    solver = CaptchaSolver()
    
    # Mock ddddocr availability to False
    solver._solvers["ddddocr"]._available = False
    
    # If ddddocr is unavailable, solve_image should fail gracefully for that solver
    res = await solver._solvers["ddddocr"].solve_image("dummy_base64")
    assert res.success is False
    assert "not available" in res.error


@pytest.mark.asyncio
async def test_ai_visual_no_keys(monkeypatch):
    """Verify that AIVisualSolver fails gracefully when no API keys are present."""
    # Ensure no keys in environment
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    
    ai_solver = AIVisualSolver()
    res = await ai_solver.solve_image("dummy_base64")
    assert res.success is False
    assert "No visual LLM provider API keys" in res.error
    await ai_solver.close()


@pytest.mark.asyncio
async def test_ai_visual_gemini_success(monkeypatch):
    """Verify that AIVisualSolver uses Gemini when GOOGLE_API_KEY is present and mock success."""
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-gemini-key")
    
    ai_solver = AIVisualSolver()
    
    # Mock httpx client response
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": " ABCD12 "}
                            ]
                        }
                    }
                ]
            }

    mock_post = mock.AsyncMock(return_value=MockResponse())
    
    with mock.patch("httpx.AsyncClient.post", mock_post):
        res = await ai_solver.solve_image("dummy_base64")
        assert res.success is True
        assert res.token == "ABCD12"
        assert res.provider == "ai_visual_gemini"
        
    await ai_solver.close()
