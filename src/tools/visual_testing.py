"""
AI Visual Testing Engine — Zero-Cost Visual Regression Testing
===============================================================
A production-ready visual regression testing module that uses AI vision
to detect UI changes, layout shifts, and visual bugs across pages.

KEY FEATURES:
- Baseline snapshot capture and management
- Pixel-level diff comparison with configurable thresholds
- AI-powered visual analysis (sends visuals to user's connected AI — ZERO external cost)
- Visual change categorization (layout shift, content change, style change, new element)
- Batch testing across multiple URLs
- Historical trend tracking

ZERO COST ARCHITECTURE:
- All visual analysis is sent to the user's AI (Claude, GPT, etc.) via existing MCP connection
- No external vision API calls (no OpenAI, no Google Vision, no AWS Rekognition)
- Uses the user's already-connected AI to analyze visual differences
- All processing happens within the existing Agent-X infrastructure

Usage:
    # Capture baseline
    browser = AgentBrowser(config)
    await browser.navigate("https://example.com")
    await capture_baseline(browser.page, "homepage")

    # Compare against new deployment
    result = await compare_visual(browser.page, "homepage")
    if result.has_changes:
        # Send diff to user's AI for analysis (zero cost)
        analysis = await analyze_with_user_ai(result.diff_image, result.change_regions)
"""
import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

logger = logging.getLogger("agent-x.visual_testing")


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChangeRegion:
    """A detected region of visual change."""
    x: int
    y: int
    width: int
    height: int
    change_type: str  # "layout_shift", "content_change", "style_change", "new_element", "removed_element"
    severity: str  # "critical", "major", "minor", "info"
    confidence: float  # 0.0 - 1.0
    description: str = ""


@dataclass
class VisualDiffResult:
    """Result of a visual comparison."""
    test_name: str
    url: str
    has_changes: bool
    pixel_diff_percent: float
    change_regions: List[ChangeRegion] = field(default_factory=list)
    diff_image_path: Optional[str] = None
    baseline_image_path: Optional[str] = None
    current_image_path: Optional[str] = None
    screenshot_b64: Optional[str] = None  # Base64 for sending to user's AI
    diff_b64: Optional[str] = None  # Base64 diff image for user's AI
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "url": self.url,
            "has_changes": self.has_changes,
            "pixel_diff_percent": round(self.pixel_diff_percent, 4),
            "change_count": len(self.change_regions),
            "change_regions": [
                {
                    "x": r.x, "y": r.y, "width": r.width, "height": r.height,
                    "type": r.change_type, "severity": r.severity,
                    "confidence": round(r.confidence, 2),
                    "description": r.description,
                }
                for r in self.change_regions
            ],
            "diff_image": self.diff_image_path,
            "baseline_image": self.baseline_image_path,
            "current_image": self.current_image_path,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class BaselineEntry:
    """Stored baseline metadata."""
    test_name: str
    url: str
    image_path: str
    viewport: Dict[str, int]
    device_scale_factor: float
    captured_at: str
    checksum: str
    tags: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# Visual Testing Engine
# ═══════════════════════════════════════════════════════════════

class VisualTestingEngine:
    """Production-ready visual regression testing engine.
    
    Captures baseline screenshots, compares against new deployments,
    and generates detailed diff reports — all with zero external cost
    by leveraging the user's connected AI for visual analysis.
    """

    # Severity thresholds based on pixel difference percentage
    SEVERITY_THRESHOLDS = {
        "critical": 10.0,   # >10% changed
        "major": 5.0,       # >5% changed
        "minor": 1.0,       # >1% changed
        "info": 0.0,        # any change
    }

    def __init__(self, baseline_dir: Optional[str] = None):
        self.baseline_dir = Path(baseline_dir or os.path.expanduser("~/.agent-x/visual-baselines"))
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = self.baseline_dir / "results"
        self.results_dir.mkdir(exist_ok=True)
        
        # In-memory baseline registry
        self._baselines: Dict[str, BaselineEntry] = {}
        self._load_baseline_registry()

    def _load_baseline_registry(self):
        """Load baseline metadata from disk."""
        registry_path = self.baseline_dir / "registry.json"
        if registry_path.exists():
            try:
                data = json.loads(registry_path.read_text())
                for name, entry in data.items():
                    self._baselines[name] = BaselineEntry(**entry)
                logger.info(f"Loaded {len(self._baselines)} baseline(s)")
            except Exception as e:
                logger.warning(f"Failed to load baseline registry: {e}")

    def _save_baseline_registry(self):
        """Save baseline metadata to disk."""
        registry_path = self.baseline_dir / "registry.json"
        data = {
            name: {
                "test_name": e.test_name,
                "url": e.url,
                "image_path": e.image_path,
                "viewport": e.viewport,
                "device_scale_factor": e.device_scale_factor,
                "captured_at": e.captured_at,
                "checksum": e.checksum,
                "tags": e.tags,
            }
            for name, e in self._baselines.items()
        }
        registry_path.write_text(json.dumps(data, indent=2))

    # ─── Baseline Management ────────────────────────────────────

    async def capture_baseline(
        self,
        page,
        test_name: str,
        url: Optional[str] = None,
        full_page: bool = True,
        tags: Optional[List[str]] = None,
    ) -> BaselineEntry:
        """Capture and store a baseline screenshot.
        
        Args:
            page: Playwright page object
            test_name: Unique name for this baseline (e.g., "homepage", "login-page")
            url: URL being captured (auto-detected from page if not provided)
            full_page: Whether to capture full page or just viewport
            tags: Optional tags for organizing baselines
        """
        start_time = time.time()
        page_url = url or page.url
        tags = tags or []
        
        # Get viewport info for metadata
        viewport = page.viewport_size or {"width": 1920, "height": 1080}
        device_scale = await page.evaluate("window.devicePixelRatio") if page else 1.0
        
        # Capture screenshot
        screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
        
        # Save baseline image
        image_filename = f"{test_name}_{viewport['width']}x{viewport['height']}.png"
        image_path = str(self.baseline_dir / image_filename)
        Path(image_path).write_bytes(screenshot_bytes)
        
        # Compute checksum
        checksum = hashlib.sha256(screenshot_bytes).hexdigest()[:16]
        
        entry = BaselineEntry(
            test_name=test_name,
            url=page_url,
            image_path=image_path,
            viewport=viewport,
            device_scale_factor=float(device_scale),
            captured_at=datetime.utcnow().isoformat(),
            checksum=checksum,
            tags=tags,
        )
        
        self._baselines[test_name] = entry
        self._save_baseline_registry()
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Baseline captured: {test_name} ({len(screenshot_bytes)} bytes, {elapsed:.0f}ms)")
        return entry

    def get_baseline(self, test_name: str) -> Optional[BaselineEntry]:
        """Get a stored baseline by name."""
        return self._baselines.get(test_name)

    def list_baselines(self, tag: Optional[str] = None) -> List[BaselineEntry]:
        """List all baselines, optionally filtered by tag."""
        if tag:
            return [b for b in self._baselines.values() if tag in b.tags]
        return list(self._baselines.values())

    def delete_baseline(self, test_name: str) -> bool:
        """Delete a baseline and its image."""
        entry = self._baselines.pop(test_name, None)
        if entry:
            try:
                Path(entry.image_path).unlink(missing_ok=True)
            except Exception:
                pass
            self._save_baseline_registry()
            logger.info(f"Baseline deleted: {test_name}")
            return True
        return False

    # ─── Visual Comparison ──────────────────────────────────────

    async def compare_visual(
        self,
        page,
        test_name: str,
        threshold: float = 0.1,  # Pixel difference threshold (0-255)
        full_page: bool = True,
    ) -> VisualDiffResult:
        """Compare current page against stored baseline.
        
        Args:
            page: Playwright page object
            test_name: Name of baseline to compare against
            threshold: Color difference threshold (0-255, default 0.1)
            full_page: Whether to capture full page
            
        Returns:
            VisualDiffResult with change detection details
        """
        start_time = time.time()
        baseline = self._baselines.get(test_name)
        
        if not baseline:
            raise ValueError(f"No baseline found for '{test_name}'. Capture baseline first.")
        
        page_url = page.url or baseline.url
        timestamp = datetime.utcnow().isoformat()
        
        # Capture current screenshot
        current_bytes = await page.screenshot(full_page=full_page, type="png")
        current_path = str(self.results_dir / f"{test_name}_current_{int(time.time())}.png")
        Path(current_path).write_bytes(current_bytes)
        
        # Load baseline image
        baseline_img = Image.open(io.BytesIO(Path(baseline.image_path).read_bytes()))
        current_img = Image.open(io.BytesIO(current_bytes))
        
        # Compare
        result = self._compute_diff(
            baseline_img, 
            current_img, 
            test_name, 
            page_url, 
            threshold,
            baseline.image_path,
            current_path,
        )
        result.timestamp = timestamp
        
        # Encode images for AI analysis (if changes detected)
        if result.has_changes:
            result.screenshot_b64 = base64.b64encode(current_bytes).decode("utf-8")
            if result.diff_image_path and Path(result.diff_image_path).exists():
                diff_bytes = Path(result.diff_image_path).read_bytes()
                result.diff_b64 = base64.b64encode(diff_bytes).decode("utf-8")
        
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        # Save result metadata
        result_path = self.results_dir / f"{test_name}_result_{int(time.time())}.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2))
        
        logger.info(
            f"Visual comparison complete: {test_name} — "
            f"{result.pixel_diff_percent:.2f}% changed, "
            f"{len(result.change_regions)} region(s), "
            f"{result.processing_time_ms:.0f}ms"
        )
        return result

    def _compute_diff(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image,
        test_name: str,
        url: str,
        threshold: float,
        baseline_path: str,
        current_path: str,
    ) -> VisualDiffResult:
        """Compute pixel-level diff between two images."""
        
        # Normalize sizes
        base_width, base_height = baseline_img.size
        curr_width, curr_height = current_img.size
        
        if (base_width, base_height) != (curr_width, curr_height):
            # Resize current to match baseline for comparison
            current_img = current_img.resize((base_width, base_height), Image.Resampling.LANCZOS)
            size_changed = True
        else:
            size_changed = False
        
        # Convert to same mode
        if baseline_img.mode != current_img.mode:
            baseline_img = baseline_img.convert("RGB")
            current_img = current_img.convert("RGB")
        
        # Compute pixel diff
        diff = ImageChops.difference(baseline_img, current_img)
        
        # Apply threshold
        if threshold > 0:
            diff = diff.point(lambda p: p > threshold * 255 and 255 or 0)
        
        # Calculate percentage
        diff_stat = ImageStat.Stat(diff)
        total_pixels = base_width * base_height
        diff_pixels = sum(diff_stat.sum) / (255 * len(diff_stat.sum)) if total_pixels > 0 else 0
        diff_percent = (diff_pixels / total_pixels) * 100 if total_pixels > 0 else 0
        
        has_changes = diff_percent > 0.01  # 0.01% minimum change
        
        # Find change regions
        change_regions: List[ChangeRegion] = []
        
        if has_changes:
            change_regions = self._detect_change_regions(
                diff, base_width, base_height, diff_percent
            )
            
            if size_changed:
                change_regions.append(ChangeRegion(
                    x=0, y=0, width=curr_width, height=curr_height,
                    change_type="layout_shift",
                    severity="major",
                    confidence=1.0,
                    description=f"Page dimensions changed from {base_width}x{base_height} to {curr_width}x{curr_height}",
                ))
        
        # Generate diff visualization
        diff_image_path = None
        if has_changes:
            diff_image_path = self._create_diff_visualization(
                baseline_img, current_img, diff, test_name, change_regions
            )
        
        return VisualDiffResult(
            test_name=test_name,
            url=url,
            has_changes=has_changes,
            pixel_diff_percent=diff_percent,
            change_regions=change_regions,
            diff_image_path=diff_image_path,
            baseline_image_path=baseline_path,
            current_image_path=current_path,
        )

    def _detect_change_regions(
        self,
        diff_img: Image.Image,
        img_width: int,
        img_height: int,
        diff_percent: float,
    ) -> List[ChangeRegion]:
        """Detect distinct regions of change in the diff image."""
        
        # Convert to binary mask
        gray = diff_img.convert("L") if diff_img.mode != "L" else diff_img
        
        # Dilate to merge nearby changes
        dilated = gray.filter(ImageFilter.MaxFilter(size=15))
        
        # Find bounding boxes of change regions
        # Simple approach: divide into grid and find active cells
        regions: List[ChangeRegion] = []
        
        cell_size = 50
        grid_cols = max(1, img_width // cell_size)
        grid_rows = max(1, img_height // cell_size)
        
        for row in range(grid_rows):
            for col in range(grid_cols):
                x1 = col * cell_size
                y1 = row * cell_size
                x2 = min(x1 + cell_size, img_width)
                y2 = min(y1 + cell_size, img_height)
                
                cell = dilated.crop((x1, y1, x2, y2))
                cell_stat = ImageStat.Stat(cell)
                cell_diff = sum(cell_stat.sum) / (255 * len(cell_stat.sum))
                cell_pixels = (x2 - x1) * (y2 - y1)
                cell_percent = (cell_diff / cell_pixels) * 100 if cell_pixels > 0 else 0
                
                if cell_percent > 1.0:  # At least 1% different in this cell
                    # Determine severity
                    if cell_percent > 50:
                        severity = "critical"
                    elif cell_percent > 20:
                        severity = "major"
                    elif cell_percent > 5:
                        severity = "minor"
                    else:
                        severity = "info"
                    
                    # Determine change type based on characteristics
                    if cell_percent > 30:
                        change_type = "content_change"
                    else:
                        change_type = "style_change"
                    
                    regions.append(ChangeRegion(
                        x=x1, y=y1, width=x2-x1, height=y2-y1,
                        change_type=change_type,
                        severity=severity,
                        confidence=min(cell_percent / 100, 1.0),
                        description=f"{change_type.replace('_', ' ').title()}: {cell_percent:.1f}% of region changed",
                    ))
        
        # Merge overlapping regions
        regions = self._merge_regions(regions)
        
        # Add overall severity annotation
        if diff_percent > self.SEVERITY_THRESHOLDS["critical"]:
            overall_severity = "critical"
        elif diff_percent > self.SEVERITY_THRESHOLDS["major"]:
            overall_severity = "major"
        elif diff_percent > self.SEVERITY_THRESHOLDS["minor"]:
            overall_severity = "minor"
        else:
            overall_severity = "info"
        
        for r in regions:
            if r.severity != overall_severity and overall_severity in ["critical", "major"]:
                r.severity = overall_severity
        
        return regions

    def _merge_regions(self, regions: List[ChangeRegion], merge_distance: int = 20) -> List[ChangeRegion]:
        """Merge overlapping or nearby regions."""
        if not regions:
            return regions
        
        # Sort by position
        sorted_regions = sorted(regions, key=lambda r: (r.y, r.x))
        merged: List[ChangeRegion] = [sorted_regions[0]]
        
        for region in sorted_regions[1:]:
            last = merged[-1]
            # Check if regions overlap or are close
            if (region.x <= last.x + last.width + merge_distance and
                region.y <= last.y + last.height + merge_distance and
                last.x <= region.x + region.width + merge_distance and
                last.y <= region.y + region.height + merge_distance):
                # Merge
                new_x = min(last.x, region.x)
                new_y = min(last.y, region.y)
                new_width = max(last.x + last.width, region.x + region.width) - new_x
                new_height = max(last.y + last.height, region.y + region.height) - new_y
                last.x = new_x
                last.y = new_y
                last.width = new_width
                last.height = new_height
                last.confidence = max(last.confidence, region.confidence)
                if region.severity == "critical" or last.severity == "critical":
                    last.severity = "critical"
                elif region.severity == "major" or last.severity == "major":
                    last.severity = "major"
            else:
                merged.append(region)
        
        return merged

    def _create_diff_visualization(
        self,
        baseline: Image.Image,
        current: Image.Image,
        diff: Image.Image,
        test_name: str,
        regions: List[ChangeRegion],
    ) -> str:
        """Create a side-by-side diff visualization with highlighted regions."""
        
        # Ensure all images are RGB
        baseline = baseline.convert("RGB") if baseline.mode != "RGB" else baseline
        current = current.convert("RGB") if current.mode != "RGB" else current
        
        # Create highlighted version of current image
        highlighted = current.copy()
        draw = ImageDraw.Draw(highlighted, "RGBA")
        
        # Color map for severities
        severity_colors = {
            "critical": (255, 0, 0, 128),    # Red
            "major": (255, 128, 0, 128),      # Orange
            "minor": (255, 255, 0, 100),      # Yellow
            "info": (0, 128, 255, 80),        # Blue
        }
        
        for region in regions:
            color = severity_colors.get(region.severity, (128, 128, 128, 100))
            draw.rectangle(
                [region.x, region.y, region.x + region.width, region.y + region.height],
                outline=color[:3] + (255,),
                width=3,
            )
            # Add semi-transparent fill
            overlay = Image.new("RGBA", highlighted.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [region.x, region.y, region.x + region.width, region.y + region.height],
                fill=color,
            )
            highlighted = Image.alpha_composite(highlighted.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(highlighted, "RGBA")
        
        # Create composite: baseline | current | highlighted
        base_width, base_height = baseline.size
        composite = Image.new("RGB", (base_width * 3, base_height + 40), (30, 30, 30))
        
        # Labels
        from PIL import ImageFont
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        
        # Paste images
        composite.paste(baseline, (0, 40))
        composite.paste(current, (base_width, 40))
        composite.paste(highlighted.convert("RGB"), (base_width * 2, 40))
        
        # Draw labels
        label_draw = ImageDraw.Draw(composite)
        label_draw.text((10, 10), "BASELINE", fill=(200, 200, 200), font=font)
        label_draw.text((base_width + 10, 10), "CURRENT", fill=(200, 200, 200), font=font)
        label_draw.text((base_width * 2 + 10, 10), "CHANGES HIGHLIGHTED", fill=(255, 100, 100), font=font)
        
        # Save
        diff_path = str(self.results_dir / f"{test_name}_diff_{int(time.time())}.png")
        composite.save(diff_path, "PNG")
        
        return diff_path

    # ─── Zero-Cost AI Analysis ──────────────────────────────────

    async def analyze_with_user_ai(
        self,
        diff_result: VisualDiffResult,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare visual analysis payload for user's AI (ZERO COST).
        
        Instead of calling external vision APIs, this prepares a structured
        message with the diff images and change data that can be sent to the
        user's already-connected AI (Claude, GPT, etc.) via the MCP/WebSocket
        connection. This means:
        
        - ZERO external API costs
        - Uses the user's existing AI connection
        - Full visual context provided to their AI
        - Their AI can provide natural language analysis
        
        Args:
            diff_result: The visual diff result to analyze
            context: Optional context about what was being tested
            
        Returns:
            Dict with analysis prompt and image data ready for user's AI
        """
        if not diff_result.has_changes:
            return {
                "has_changes": False,
                "summary": "No visual changes detected.",
                "prompt": "No changes to analyze — the page matches the baseline.",
                "images": {},
            }
        
        # Build detailed change description
        change_descriptions = []
        for i, region in enumerate(diff_result.change_regions, 1):
            change_descriptions.append(
                f"{i}. [{region.severity.upper()}] {region.change_type.replace('_', ' ').title()} "
                f"at ({region.x}, {region.y}, {region.width}x{region.height}) — "
                f"confidence: {region.confidence:.0%} — {region.description}"
            )
        
        # Build severity summary
        severity_counts: Dict[str, int] = {}
        for r in diff_result.change_regions:
            severity_counts[r.severity] = severity_counts.get(r.severity, 0) + 1
        
        severity_summary = ", ".join(
            f"{count} {sev}" for sev, count in 
            sorted(severity_counts.items(), key=lambda x: {"critical": 0, "major": 1, "minor": 2, "info": 3}.get(x[0], 4))
        )
        
        # Build the analysis prompt for user's AI
        prompt = f"""You are a visual QA expert analyzing a web page regression test. Review the following visual changes and provide a detailed analysis.

**Test:** {diff_result.test_name}
**URL:** {diff_result.url}
**Overall Change:** {diff_result.pixel_diff_percent:.2f}% of pixels differ
**Severity Breakdown:** {severity_summary}
**Total Change Regions:** {len(diff_result.change_regions)}

**Detected Changes:**
{chr(10).join(change_descriptions) if change_descriptions else "No specific regions detected — diffuse changes across page."}

{f"**Additional Context:** {context}" if context else ""}

Please analyze:
1. What likely caused these changes (code deployment, content update, A/B test, etc.)?
2. Are any changes potentially breaking user experience?
3. Which changes are expected vs unexpected?
4. Recommended actions (approve, investigate, rollback)."""

        # Prepare image payloads
        images = {}
        if diff_result.diff_b64:
            images["diff_visualization"] = {
                "type": "image/png",
                "base64": diff_result.diff_b64,
                "description": "Side-by-side comparison: baseline | current | highlighted changes",
            }
        if diff_result.screenshot_b64:
            images["current_screenshot"] = {
                "type": "image/png",
                "base64": diff_result.screenshot_b64,
                "description": "Current page screenshot",
            }
        
        result = {
            "has_changes": True,
            "test_name": diff_result.test_name,
            "url": diff_result.url,
            "pixel_diff_percent": round(diff_result.pixel_diff_percent, 4),
            "severity_summary": severity_summary,
            "change_count": len(diff_result.change_regions),
            "prompt": prompt,
            "images": images,
            "ready_for_ai": True,
            "note": "Send the 'prompt' and 'images' to the user's connected AI for zero-cost visual analysis.",
        }
        
        logger.info(
            f"AI analysis payload prepared for '{diff_result.test_name}': "
            f"{len(prompt)} chars prompt, {len(images)} image(s) — ZERO external cost"
        )
        return result

    # ─── Batch Testing ──────────────────────────────────────────

    async def run_batch_test(
        self,
        page,
        test_names: List[str],
    ) -> List[VisualDiffResult]:
        """Run visual tests against multiple baselines sequentially."""
        results: List[VisualDiffResult] = []
        for name in test_names:
            if name in self._baselines:
                try:
                    # Navigate to baseline URL first
                    baseline = self._baselines[name]
                    await page.goto(baseline.url, wait_until="networkidle")
                    await asyncio.sleep(1)  # Allow visual stabilization
                    result = await self.compare_visual(page, name)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch test failed for '{name}': {e}")
                    results.append(VisualDiffResult(
                        test_name=name,
                        url=baseline.url if name in self._baselines else "",
                        has_changes=False,
                        pixel_diff_percent=0.0,
                        metadata={"error": str(e)},
                        timestamp=datetime.utcnow().isoformat(),
                    ))
            else:
                logger.warning(f"Baseline not found: {name}")
        return results

    # ─── Cleanup ────────────────────────────────────────────────

    def cleanup_old_results(self, max_age_days: int = 30):
        """Remove result files older than specified days."""
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0
        for f in self.results_dir.glob("*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        logger.info(f"Cleaned up {removed} old result file(s)")
        return removed


# ═══════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════

# Global engine instance (lazy-loaded)
_global_engine: Optional[VisualTestingEngine] = None

def get_engine() -> VisualTestingEngine:
    """Get or create the global visual testing engine."""
    global _global_engine
    if _global_engine is None:
        _global_engine = VisualTestingEngine()
    return _global_engine


async def capture_baseline(page, test_name: str, **kwargs) -> BaselineEntry:
    """Capture a baseline screenshot. Convenience function."""
    engine = get_engine()
    return await engine.capture_baseline(page, test_name, **kwargs)


async def compare_visual(page, test_name: str, **kwargs) -> VisualDiffResult:
    """Compare page against baseline. Convenience function."""
    engine = get_engine()
    return await engine.compare_visual(page, test_name, **kwargs)


async def analyze_visual_diff(diff_result: VisualDiffResult, context: Optional[str] = None) -> Dict[str, Any]:
    """Prepare visual diff for user's AI analysis. Convenience function."""
    engine = get_engine()
    return await engine.analyze_with_user_ai(diff_result, context)
