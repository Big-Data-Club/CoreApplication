"""
app/services/youtube_service.py

Fetch published YouTube captions for indexing.

Do not silently download YouTube audio as a fallback.  YouTube's delivery
clients increasingly require per-video Proof-of-Origin tokens, so such a
fallback is unreliable on a server and can cause repeated 403/IP blocks.  A
video without captions should be uploaded by its owner for local transcription.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

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
      3. Nếu không có caption: yêu cầu upload video gốc để xử lý nội bộ.

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

        raise ValueError(
            "YouTube video has no accessible captions. Upload the source video "
            "to BDC Hub to transcribe it securely, or add captions on YouTube first."
        )

    # ── Method 1: youtube-transcript-api ──────────────────────────────────────

    def _fetch_api(self, video_id: str, preferred_lang: str) -> Optional[dict]:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            logger.error("youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
            return None

        try:
            transcript_list = YouTubeTranscriptApi().list(video_id)
        except Exception as exc:
            logger.warning("list_transcripts failed for %s: %s", video_id, exc)
            return None

        # Thứ tự ưu tiên: manual vi/en -> auto vi/en -> bất kỳ
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
                raw = t.fetch().to_raw_data()
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
            raw = t.fetch().to_raw_data()
            segments = self._normalize(raw)
            logger.info(
                "YouTube transcript (translated): %d segments, id=%s", len(segments), video_id
            )
            return {"segments": segments, "language": actual_lang, "method": "youtube_api_translated"}
        except Exception as exc:
            logger.warning("All transcript API attempts failed for %s: %s", video_id, exc)
            return None

    def _normalize(self, raw: list) -> list[dict]:
        """youtube-transcript-api -> Whisper format"""
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

youtube_fetcher = YouTubeTranscriptFetcher()
