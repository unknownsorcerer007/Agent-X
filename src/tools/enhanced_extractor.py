"""
Agent-OS Enhanced Extractor
===========================
Integrates free open-source tools for better web data extraction:
  - trafilatura: State-of-the-art web text extraction
  - readability-lxml: Mozilla Readability article extraction
  - ddddocr: Free offline captcha OCR (deep-learning based)

All tools are FREE, require NO API keys, and run completely offline.

License references:
  - trafilatura: Apache-2.0
  - readability-lxml: Apache-2.0
  - ddddocr: Apache-2.0
"""

import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger("agent-os.enhanced_extractor")


class TrafilaturaExtractor:
    """Extract clean text and metadata from HTML using trafilatura.
    
    Trafilatura beats BeautifulSoup for text extraction because it:
    - Removes boilerplate (ads, nav, footers) automatically
    - Preserves article structure (paragraphs, headings)
    - Extracts metadata (author, date, description)
    - Handles malformed HTML gracefully
    
    No API key needed. Runs locally. Apache-2.0 license.
    """

    def __init__(self):
        self._available = False
        try:
            import trafilatura
            self._trafilatura = trafilatura
            self._available = True
            logger.info("TrafilaturaExtractor initialized (trafilatura available)")
        except ImportError:
            logger.info("TrafilaturaExtractor: trafilatura not installed, using fallback")

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, html: str, url: str = "") -> Dict[str, Any]:
        """Extract clean text and metadata from HTML.
        
        Args:
            html: Raw HTML string
            url: Source URL (used for metadata resolution)
            
        Returns:
            Dict with: status, text, title, author, date, description, categories
        """
        if not self._available:
            return self._fallback_extract(html, url)

        try:
            # trafilatura.extract returns clean text or None
            text = self._trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
            
            # trafilatura.extract returns metadata dict
            metadata = self._trafilatura.extract(html, url=url, output_format="json", include_comments=False)
            
            result = {
                "status": "success",
                "text": text or "",
                "extraction_method": "trafilatura",
            }

            # Parse metadata if available
            if metadata:
                try:
                    import json
                    meta = json.loads(metadata) if isinstance(metadata, str) else {}
                    result.update({
                        "title": meta.get("title", ""),
                        "author": meta.get("author", ""),
                        "date": meta.get("date", ""),
                        "description": meta.get("description", ""),
                        "categories": meta.get("categories", []),
                        "tags": meta.get("tags", []),
                        "hostname": meta.get("hostname", ""),
                        "language": meta.get("language", ""),
                        "fingerprint": meta.get("fingerprint", ""),
                    })
                except (json.JSONDecodeError, TypeError):
                    pass

            return result

        except Exception as e:
            logger.warning(f"Trafilatura extraction failed: {e}")
            return self._fallback_extract(html, url)

    def _fallback_extract(self, html: str, url: str = "") -> Dict[str, Any]:
        """Fallback extraction using regex when trafilatura is not available."""
        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Remove tags to get plain text
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Truncate to first 50000 chars
        text = text[:50000]

        return {
            "status": "success",
            "text": text,
            "title": title,
            "extraction_method": "regex_fallback",
        }


class ReadabilityExtractor:
    """Extract article main content using Mozilla Readability algorithm.
    
    readability-lxml is a Python port of Mozilla's Readability.js.
    It extracts just the article body and title from noisy HTML pages.
    
    No API key needed. Runs locally. Apache-2.0 license.
    """

    def __init__(self):
        self._available = False
        try:
            from readability import Document
            self._Document = Document
            self._available = True
            logger.info("ReadabilityExtractor initialized (readability-lxml available)")
        except ImportError:
            logger.info("ReadabilityExtractor: readability-lxml not installed, using fallback")

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, html: str) -> Dict[str, Any]:
        """Extract article content from HTML.
        
        Args:
            html: Raw HTML string
            
        Returns:
            Dict with: status, title, summary, article_html, text
        """
        if not self._available:
            return {"status": "error", "error": "readability-lxml not installed", "extraction_method": "none"}

        try:
            doc = self._Document(html)
            title = doc.title()
            summary_html = doc.summary()
            
            # Strip HTML from summary to get plain text
            text = re.sub(r"<[^>]+>", " ", summary_html)
            text = re.sub(r"\s+", " ", text).strip()

            return {
                "status": "success",
                "title": title,
                "article_html": summary_html,
                "text": text,
                "extraction_method": "readability",
            }
        except Exception as e:
            logger.warning(f"Readability extraction failed: {e}")
            return {"status": "error", "error": str(e), "extraction_method": "readability"}


class DdddocrCaptchaSolver:
    """Free offline captcha OCR using ddddocr deep-learning model.
    
    ddddocr is a Chinese open-source OCR library specifically trained on
    common captcha styles (text distortion, noise, overlapping characters).
    
    No API key needed. No internet connection needed. Runs 100% locally.
    Apache-2.0 license.
    """

    def __init__(self):
        self._available = False
        self._ocr = None
        try:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
            self._available = True
            logger.info("DdddocrCaptchaSolver initialized (ddddocr available)")
        except ImportError:
            logger.info("DdddocrCaptchaSolver: ddddocr not installed")
        except Exception as e:
            logger.warning(f"DdddocrCaptchaSolver init failed: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def solve_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Solve a captcha image.
        
        Args:
            image_bytes: Raw image bytes (PNG, JPEG, etc.)
            
        Returns:
            Dict with: status, text, confidence
        """
        if not self._available:
            return {"status": "error", "error": "ddddocr not installed"}

        try:
            result = self._ocr.classification(image_bytes)
            return {
                "status": "success",
                "text": result,
                "confidence": 0.85,  # ddddocr doesn't provide confidence, estimate
                "solver": "ddddocr",
                "cost": "free",
            }
        except Exception as e:
            logger.warning(f"ddddocr solve failed: {e}")
            return {"status": "error", "error": str(e), "solver": "ddddocr"}

    def solve_base64(self, image_b64: str) -> Dict[str, Any]:
        """Solve a captcha from base64-encoded image.
        
        Args:
            image_b64: Base64-encoded image string
            
        Returns:
            Dict with: status, text, confidence
        """
        import base64
        try:
            image_bytes = base64.b64decode(image_b64)
            return self.solve_image(image_bytes)
        except Exception as e:
            return {"status": "error", "error": str(e), "solver": "ddddocr"}


class TesseractCaptchaSolver:
    """Free offline captcha OCR using Google Tesseract engine.
    
    pytesseract wraps Google's Tesseract OCR engine — the gold standard
    in open-source OCR. Best for high-resolution text captchas.
    
    Requires: tesseract binary installed on the system.
    No API key needed. Apache-2.0 license.
    """

    def __init__(self):
        self._available = False
        try:
            import pytesseract
            self._pytesseract = pytesseract
            # Verify tesseract binary is available
            self._pytesseract.get_tesseract_version()
            self._available = True
            logger.info("TesseractCaptchaSolver initialized (pytesseract available)")
        except ImportError:
            logger.info("TesseractCaptchaSolver: pytesseract not installed")
        except Exception:
            logger.info("TesseractCaptchaSolver: tesseract binary not found")

    @property
    def available(self) -> bool:
        return self._available

    def solve_image(self, image_path_or_bytes) -> Dict[str, Any]:
        """Solve a captcha image using Tesseract OCR.
        
        Args:
            image_path_or_bytes: File path string or PIL Image object
            
        Returns:
            Dict with: status, text, confidence
        """
        if not self._available:
            return {"status": "error", "error": "pytesseract/tesseract not available"}

        try:
            from PIL import Image
            import io

            if isinstance(image_path_or_bytes, bytes):
                img = Image.open(io.BytesIO(image_path_or_bytes))
            elif isinstance(image_path_or_bytes, str):
                img = Image.open(image_path_or_bytes)
            else:
                img = image_path_or_bytes

            # Preprocess for better captcha OCR
            # Convert to grayscale
            img = img.convert("L")

            # Threshold to black and white
            img = img.point(lambda x: 0 if x < 128 else 255, "1")

            # Run OCR with captcha-optimized config
            text = self._pytesseract.image_to_string(
                img,
                config="--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
            ).strip()

            return {
                "status": "success",
                "text": text,
                "confidence": 0.7,
                "solver": "tesseract",
                "cost": "free",
            }
        except Exception as e:
            logger.warning(f"Tesseract solve failed: {e}")
            return {"status": "error", "error": str(e), "solver": "tesseract"}


class HybridCaptchaSolver:
    """Combine multiple free OCR solvers for best results.
    
    Tries ddddocr first (best for distorted captchas), then Tesseract
    (best for clean text). Returns the first successful result.
    
    No API keys needed. Completely free and offline.
    """

    def __init__(self):
        self.ddddocr = DdddocrCaptchaSolver()
        self.tesseract = TesseractCaptchaSolver()
        self._solvers_available = []
        if self.ddddocr.available:
            self._solvers_available.append("ddddocr")
        if self.tesseract.available:
            self._solvers_available.append("tesseract")
        logger.info(f"HybridCaptchaSolver: {len(self._solvers_available)} solvers available: {self._solvers_available}")

    @property
    def available_solvers(self) -> list:
        return self._solvers_available

    def solve_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Try all available solvers and return the best result.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Dict with: status, text, confidence, solver, all_results
        """
        results = []

        # Try ddddocr first (better for distorted captchas)
        if self.ddddocr.available:
            result = self.ddddocr.solve_image(image_bytes)
            results.append(result)
            if result.get("status") == "success" and result.get("text"):
                result["all_results"] = results
                result["solvers_tried"] = len(results)
                return result

        # Try Tesseract (better for clean text)
        if self.tesseract.available:
            result = self.tesseract.solve_image(image_bytes)
            results.append(result)
            if result.get("status") == "success" and result.get("text"):
                result["all_results"] = results
                result["solvers_tried"] = len(results)
                return result

        # No solver succeeded
        if results:
            # Return the last result (best attempt)
            best = results[-1]
            best["all_results"] = results
            best["solvers_tried"] = len(results)
            return best

        return {
            "status": "error",
            "error": "No captcha OCR solvers available. Install ddddocr or pytesseract.",
            "solvers_tried": 0,
        }


# ═══════════════════════════════════════════════════════════════
# Convenience singletons
# ═══════════════════════════════════════════════════════════════

_trafilatura_extractor: Optional[TrafilaturaExtractor] = None
_readability_extractor: Optional[ReadabilityExtractor] = None
_hybrid_captcha_solver: Optional[HybridCaptchaSolver] = None


def get_trafilatura_extractor() -> TrafilaturaExtractor:
    """Get or create the global TrafilaturaExtractor singleton."""
    global _trafilatura_extractor
    if _trafilatura_extractor is None:
        _trafilatura_extractor = TrafilaturaExtractor()
    return _trafilatura_extractor


def get_readability_extractor() -> ReadabilityExtractor:
    """Get or create the global ReadabilityExtractor singleton."""
    global _readability_extractor
    if _readability_extractor is None:
        _readability_extractor = ReadabilityExtractor()
    return _readability_extractor


def get_hybrid_captcha_solver() -> HybridCaptchaSolver:
    """Get or create the global HybridCaptchaSolver singleton."""
    global _hybrid_captcha_solver
    if _hybrid_captcha_solver is None:
        _hybrid_captcha_solver = HybridCaptchaSolver()
    return _hybrid_captcha_solver
