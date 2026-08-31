"""Bounded multimodal extraction for uploaded lecture videos.

The transcript is the primary retrieval signal.  A small set of sampled
keyframes is only used to capture slides, diagrams and code that are not
spoken aloud.  All temporary audio/frame artefacts are deleted before return.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import subprocess
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.services.chunker import DocumentChunk, VideoTranscriptChunker, detect_language

logger = logging.getLogger(__name__)
settings = get_settings()

_whisper_model = None
_whisper_lock = asyncio.Lock()


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=timeout,
    )


def _probe_duration(video_path: Path) -> float:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(video_path),
    ], timeout=30)
    return max(0.0, float(json.loads(result.stdout)["format"]["duration"]))


async def _get_whisper_model():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            # int8 CPU keeps the model usable on the constrained K3s node.
            _whisper_model = await asyncio.to_thread(
                WhisperModel,
                settings.video_whisper_model,
                device="cpu",
                compute_type="int8",
            )
    return _whisper_model


class VideoIndexService:
    async def extract(self, video_bytes: bytes) -> tuple[str, list[DocumentChunk]]:
        if len(video_bytes) > settings.video_max_input_bytes:
            raise ValueError(
                f"Video is too large to index safely ({len(video_bytes) // (1024 * 1024)} MB; "
                f"limit is {settings.video_max_input_bytes // (1024 * 1024)} MB)"
            )
        with tempfile.TemporaryDirectory(prefix="bdc-video-index-") as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "source-video"
            video_path.write_bytes(video_bytes)
            duration = await asyncio.to_thread(_probe_duration, video_path)
            if duration <= 0:
                raise ValueError("Video has no readable duration")
            if duration > settings.video_max_duration_sec:
                raise ValueError(
                    f"Video is longer than the {settings.video_max_duration_sec // 3600}-hour indexing limit"
                )

            transcript = await self._transcribe(video_path, tmp_path)
            chunker = VideoTranscriptChunker(
                segment_duration_sec=settings.video_chunk_target_sec,
                overlap_sec=settings.video_chunk_overlap_sec,
            )
            chunks = chunker.chunk_whisper_json({"segments": transcript["segments"]})
            language = transcript.get("language") or detect_language(
                " ".join(item["text"] for item in transcript["segments"][:30])
            )
            for chunk in chunks:
                chunk.language = language

            visual_chunks = await self._extract_visual_evidence(
                video_path, duration, language, tmp_path,
            )
            chunks.extend(visual_chunks)
            chunks.sort(key=lambda chunk: (chunk.start_time_sec or 0, chunk.end_time_sec or 0))
            for index, chunk in enumerate(chunks):
                chunk.index = index

            raw_text = "\n\n".join(chunk.text for chunk in chunks)
            return raw_text, chunks

    async def _transcribe(self, video_path: Path, tmp_path: Path) -> dict:
        audio_path = tmp_path / "audio.mp3"
        await asyncio.to_thread(
            _run,
            [
                "ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
                "-b:a", "32k", str(audio_path),
            ],
            timeout=settings.video_ffmpeg_timeout_sec,
        )
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise ValueError("Video has no readable audio track")

        model = await _get_whisper_model()

        def transcribe() -> tuple[list[dict], str | None]:
            segments_iter, info = model.transcribe(
                str(audio_path), beam_size=3, vad_filter=True,
                word_timestamps=False,
            )
            return [
                {"text": segment.text.strip(), "start": segment.start, "end": segment.end}
                for segment in segments_iter if segment.text and segment.text.strip()
            ], getattr(info, "language", None)

        segments, language = await asyncio.to_thread(transcribe)
        if not segments:
            raise ValueError("No speech could be transcribed from this video")
        return {"segments": segments, "language": language}

    async def _extract_visual_evidence(
        self, video_path: Path, duration: float, language: str, tmp_path: Path,
    ) -> list[DocumentChunk]:
        if not settings.video_visual_index_enabled or not settings.vlm_enabled:
            return []
        # Sampling is intentionally bounded.  It captures slides/diagrams while
        # preventing a long lecture from turning into hundreds of VLM calls.
        interval = max(1, settings.video_keyframe_interval_sec)
        times = list(range(interval, max(interval + 1, int(duration)), interval))
        if not times:
            times = [0]
        if len(times) > settings.video_max_keyframes:
            step = duration / settings.video_max_keyframes
            times = [int(step * i) for i in range(1, settings.video_max_keyframes + 1)]
        times = sorted(set(min(max(0, second), max(0, int(duration) - 1)) for second in times))

        async def describe(second: int) -> DocumentChunk | None:
            frame_path = tmp_path / f"frame-{second}.jpg"
            try:
                await asyncio.to_thread(
                    _run,
                    [
                        "ffmpeg", "-y", "-ss", str(second), "-i", str(video_path),
                        "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "4", str(frame_path),
                    ],
                    timeout=45,
                )
                if not frame_path.exists() or frame_path.stat().st_size < 2_048:
                    return None
                from app.core.vlm import describe_image_bytes
                description = await describe_image_bytes(frame_path.read_bytes(), language, "image/jpeg")
                if not description or "không thể mô tả" in description.lower():
                    return None
                return DocumentChunk(
                    text=f"[Visual evidence at {second // 60:02d}:{second % 60:02d}] {description}",
                    index=0, source_type="video", start_time_sec=second,
                    end_time_sec=min(int(duration), second + interval), language=language,
                )
            except Exception as exc:
                logger.warning("Video keyframe extraction failed at %ss: %s", second, exc)
                return None

        results = await asyncio.gather(*(describe(second) for second in times))
        return [chunk for chunk in results if chunk is not None]


video_index_service = VideoIndexService()
