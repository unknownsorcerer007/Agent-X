"""
Agent-OS Video Transcriber
Extracts audio from videos and transcribes using local Whisper.cpp.
No external APIs — all processing on-device.
"""
import asyncio
import logging
import os
import tempfile
import subprocess
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger("agent-os.transcriber")


class Transcriber:
    """Video/audio transcription using local Whisper.cpp."""

    def __init__(self, config):
        self.config = config
        self.model_dir = Path(os.path.expanduser("~/.agent-os/models"))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "whisper-model.bin"
        self.whisper_binary = self._find_whisper()

    def _find_whisper(self) -> Optional[str]:
        """Find whisper.cpp binary."""
        # Check common locations
        for path in [
            "/usr/local/bin/whisper-cli",
            "/usr/local/bin/whisper",
            os.path.expanduser("~/.local/bin/whisper"),
            "whisper-cli",
            "whisper",
        ]:
            if os.path.exists(path) or subprocess.run(["which", path], capture_output=True).returncode == 0:
                return path
        return None

    async def transcribe_from_url(self, url: str, language: str = "auto") -> Dict:
        """
        Transcribe video/audio from a URL.
        Supports YouTube, direct video URLs, etc.
        """
        logger.info(f"Transcribing: {url}")

        # Step 1: Download audio using yt-dlp
        audio_path = await self._download_audio(url)
        if not audio_path:
            return {
                "status": "error",
                "error": "Failed to download audio. Ensure yt-dlp is installed: pip install yt-dlp"
            }

        # Step 2: Transcribe
        try:
            result = await self._run_whisper(audio_path, language)
            return result
        finally:
            # Cleanup temp file
            if os.path.exists(audio_path):
                os.unlink(audio_path)

    async def _download_audio(self, url: str) -> Optional[str]:
        """Download audio from URL using yt-dlp."""
        try:
            tmp_dir = tempfile.mkdtemp()
            output_path = os.path.join(tmp_dir, "audio.%(ext)s")

            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-x", "--audio-format", "wav",
                "--audio-quality", "0",
                "-o", output_path,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"yt-dlp failed: {stderr.decode()}")
                return None

            # Find the downloaded file
            for f in os.listdir(tmp_dir):
                if f.startswith("audio."):
                    return os.path.join(tmp_dir, f)

            return None
        except FileNotFoundError:
            logger.error("yt-dlp not found. Install with: pip install yt-dlp")
            return None
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    async def _run_whisper(self, audio_path: str, language: str) -> Dict:
        """Run Whisper transcription."""
        if self.whisper_binary and self.model_path.exists():
            return await self._run_whisper_cpp(audio_path, language)
        else:
            return await self._run_whisper_python(audio_path, language)

    async def _run_whisper_cpp(self, audio_path: str, language: str) -> Dict:
        """Transcribe using whisper.cpp (faster, lower RAM)."""
        cmd = [
            self.whisper_binary,
            "-m", str(self.model_path),
            "-f", audio_path,
            "--output-txt",
            "--output-file", "/tmp/whisper_output",
        ]
        if language != "auto":
            cmd.extend(["-l", language])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        output_file = "/tmp/whisper_output.txt"
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                text = f.read()
            os.unlink(output_file)
            return {"status": "success", "transcript": text, "engine": "whisper.cpp"}
        return {"status": "error", "error": stderr.decode()}

    async def _run_whisper_python(self, audio_path: str, language: str) -> Dict:
        """Fallback: Transcribe using whisper Python package."""
        try:
            import whisper
            model = whisper.load_model("tiny")
            result = model.transcribe(audio_path, language=None if language == "auto" else language)
            return {
                "status": "success",
                "transcript": result["text"],
                "language": result.get("language", "unknown"),
                "engine": "whisper-python",
                "segments": len(result.get("segments", []))
            }
        except ImportError:
            return {
                "status": "error",
                "error": "whisper not installed. Install with: pip install openai-whisper"
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def transcribe_from_page(self, browser) -> Dict:
        """Transcribe video on current page (e.g., YouTube)."""
        # Check if there's a video on the page
        _has_video_resp = await browser.evaluate_js("""() => {
            return !!document.querySelector('video');
        }""")
        has_video = _has_video_resp.get("result") if isinstance(_has_video_resp, dict) and _has_video_resp.get("status") == "success" else _has_video_resp

        if not has_video:
            return {"status": "error", "error": "No video found on current page"}

        # Get video source
        _video_src_resp = await browser.evaluate_js("""() => {
            const video = document.querySelector('video');
            return video ? video.src || video.currentSrc : null;
        }""")
        video_src = _video_src_resp.get("result") if isinstance(_video_src_resp, dict) and _video_src_resp.get("status") == "success" else _video_src_resp

        if video_src:
            return await self.transcribe_from_url(video_src)

        # For YouTube, extract URL and use yt-dlp
        _url_resp = await browser.evaluate_js("() => window.location.href")
        url = _url_resp.get("result") if isinstance(_url_resp, dict) and _url_resp.get("status") == "success" else _url_resp
        return await self.transcribe_from_url(url)
