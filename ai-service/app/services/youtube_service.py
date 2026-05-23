"""
app/services/youtube_service.py

Fetch YouTube transcript — ưu tiên youtube-transcript-api (~50ms, 0 CPU).
Whisper fallback bị tắt mặc định vì tốn ~500MB RAM cho server nhỏ.
Bật qua env: YOUTUBE_WHISPER_FALLBACK=true
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_WHISPER_FALLBACK = os.getenv("YOUTUBE_WHISPER_FALLBACK", "false").lower() == "true"

_YT_RE = re.compile(
    r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})"
)


def extract_video_id(url: str) -> Optional[str]:
    m = _YT_RE.search(url)
    return m.group(1) if m else None


def is_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url) and extract_video_id(url))


class YouTubeTranscriptFetcher:
    """
    Lấy transcript YouTube theo thứ tự ưu tiên:
      1. Manual subtitles (vi hoặc en)
      2. Auto-generated captions
      3. Whisper (chỉ khi YOUTUBE_WHISPER_FALLBACK=true và yt-dlp + faster-whisper đã cài)

    Output tương thích VideoTranscriptChunker.chunk_whisper_json():
      {"segments": [{"start": float, "end": float, "text": str}, ...]}
    """

    async def fetch(
        self,
        video_url: str,
        preferred_language: str = "vi",
    ) -> dict:
        video_id = extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Cannot extract video ID from: {video_url}")

        loop = asyncio.get_event_loop()

        # Method 1: youtube-transcript-api (nhanh, nhẹ)
        result = await loop.run_in_executor(
            None, self._fetch_api, video_id, preferred_language
        )
        if result:
            return result

        # Method 2: Whisper fallback (nặng — chỉ bật khi cần)
        if _WHISPER_FALLBACK:
            logger.warning(
                "No transcript via API for %s, falling back to Whisper", video_id
            )
            result = await loop.run_in_executor(
                None, self._fetch_whisper, video_url, preferred_language
            )
            if result:
                return result

        raise ValueError(
            f"No transcript available for {video_id}. "
            f"Try setting YOUTUBE_WHISPER_FALLBACK=true for videos without captions."
        )

    # ── Method 1: youtube-transcript-api ──────────────────────────────────────

    def _fetch_api(self, video_id: str, preferred_lang: str) -> Optional[dict]:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            logger.error("youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
            return None

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as exc:
            logger.warning("list_transcripts failed for %s: %s", video_id, exc)
            return None

        # Thứ tự ưu tiên: manual vi/en → auto vi/en → bất kỳ
        other_lang = "en" if preferred_lang == "vi" else "vi"
        attempts = [
            (preferred_lang, False),
            (other_lang, False),
            (preferred_lang, True),
            (other_lang, True),
        ]

        for lang, generated in attempts:
            try:
                t = (
                    transcript_list.find_generated_transcript([lang])
                    if generated
                    else transcript_list.find_manually_created_transcript([lang])
                )
                raw = t.fetch()
                segments = self._normalize(raw)
                logger.info(
                    "YouTube transcript: %d segments, lang=%s, generated=%s, id=%s",
                    len(segments), lang, generated, video_id,
                )
                return {"segments": segments, "language": lang, "method": "youtube_api"}
            except Exception:
                continue

        # Last resort: lấy bất kỳ transcript nào, dịch nếu cần
        try:
            t = next(iter(transcript_list))
            actual_lang = t.language_code
            if actual_lang not in (preferred_lang, "en", "vi"):
                t = t.translate(preferred_lang)
                actual_lang = preferred_lang
            raw = t.fetch()
            segments = self._normalize(raw)
            logger.info(
                "YouTube transcript (translated): %d segments, id=%s", len(segments), video_id
            )
            return {"segments": segments, "language": actual_lang, "method": "youtube_api_translated"}
        except Exception as exc:
            logger.warning("All transcript API attempts failed for %s: %s", video_id, exc)
            return None

    def _normalize(self, raw: list) -> list[dict]:
        """youtube-transcript-api → Whisper format"""
        segments = []
        for item in raw:
            text = item.get("text", "").strip()
            # Bỏ noise tags
            if not text or text in ("[Music]", "[Applause]", "[Laughter]", "[music]"):
                continue
            start = float(item.get("start", 0))
            dur = float(item.get("duration", 2))
            segments.append({"text": text, "start": start, "end": start + max(dur, 0.5)})
        return segments

    # ── Method 2: yt-dlp + faster-whisper (optional, heavy) ───────────────────

    def _download_audio(self, video_url: str, audio_path: str) -> Optional[str]:
        """Download audio from YouTube using yt-dlp with multiple fallback strategies."""
        import os
        import glob

        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp not installed. Run: pip install yt-dlp")
            return None

        # Try multiple format + player_client combos
        strategies = [
            {"format": "bestaudio/best", "player_client": ["web"]},
            {"format": "bestaudio/best", "player_client": ["mweb", "web"]},
            {"format": "bestaudio*", "player_client": ["web"]},
            {"format": "worstaudio", "player_client": ["web"]},
            {"format": "bestaudio/best", "player_client": ["tv_embedded"]},
        ]

        for i, strategy in enumerate(strategies):
            # Clean up previous attempt files
            for f in glob.glob(f"{audio_path}.*"):
                try:
                    os.remove(f)
                except OSError:
                    pass

            ydl_opts = {
                "format": strategy["format"],
                "outtmpl": f"{audio_path}.%(ext)s",
                "noplaylist": True,
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "extractor_args": {
                    "youtube": {"player_client": strategy["player_client"]}
                },
                "source_address": "0.0.0.0",  # Force IPv4
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            try:
                logger.info(
                    "yt-dlp attempt %d/%d: format=%s, client=%s",
                    i + 1, len(strategies),
                    strategy["format"], strategy["player_client"],
                )
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(video_url, download=True)
            except Exception as exc:
                logger.warning("yt-dlp attempt %d failed: %s", i + 1, exc)
                continue

            # Find the downloaded audio file
            for ext in ("m4a", "webm", "opus", "mp3", "ogg", "wav"):
                p = f"{audio_path}.{ext}"
                if os.path.exists(p):
                    logger.info("Audio downloaded: %s", p)
                    return p

            # Glob fallback in case of unexpected extension
            matches = glob.glob(f"{audio_path}.*")
            if matches:
                logger.info("Audio downloaded (glob): %s", matches[0])
                return matches[0]

        logger.error("All yt-dlp download strategies failed for %s", video_url)
        return None

    def _fetch_whisper(self, video_url: str, language: str) -> Optional[dict]:
        import tempfile
        import os

        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            logger.error(
                "Whisper fallback requires: pip install faster-whisper. Error: %s", e
            )
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio")
            actual_path = self._download_audio(video_url, audio_path)
            if not actual_path:
                return None

            try:
                # "base" thay vì "small" — nhanh hơn 2x, đủ cho tiếng Việt
                model = WhisperModel("base", device="cpu", compute_type="int8")
                lang_code = language if language in ("vi", "en") else None
                segs, info = model.transcribe(
                    actual_path,
                    language=lang_code,
                    beam_size=1,        # nhanh hơn
                    vad_filter=True,    # bỏ silence
                )
                segments = [
                    {"text": s.text.strip(), "start": s.start, "end": s.end}
                    for s in segs if s.text.strip()
                ]
                logger.info(
                    "Whisper: %d segments, detected=%s", len(segments), info.language
                )
                return {
                    "segments": segments,
                    "language": info.language or language,
                    "method": "whisper",
                }
            except Exception as exc:
                logger.error("Whisper transcription failed: %s", exc)
                return None


youtube_fetcher = YouTubeTranscriptFetcher()