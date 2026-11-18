"""Caption-first YouTube retrieval and bounded audio fallback, without network."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.youtube_service import YouTubeTranscriptFetcher
from app.services.video_index_service import video_index_service, settings


@pytest.mark.asyncio
async def test_available_captions_do_not_download_audio(monkeypatch):
    fetcher = YouTubeTranscriptFetcher()
    captions = {"segments": [{"text": "MPI", "start": 0, "end": 1}], "language": "en"}
    monkeypatch.setattr(fetcher, "_fetch_api", lambda *args: captions)
    audio = AsyncMock()
    monkeypatch.setattr(fetcher, "_fetch_audio", audio)
    assert await fetcher.fetch("https://youtu.be/abcdefghijk") == captions
    audio.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_missing_captions_try_only_public_bounded_audio(monkeypatch, blocked):
    paths = []
    class Downloader:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            assert url == "https://www.youtube.com/watch?v=abcdefghijk" and download
            options = self.options
            assert options["format"] == "bestaudio" and options["noplaylist"]
            assert options["js_runtimes"] == {"node": {}}
            assert options["max_filesize"] == settings.video_max_input_bytes
            validate = options["match_filter"]
            assert validate({"duration": 120}) is None
            assert validate({"duration": settings.video_max_duration_sec + 1})
            assert validate({"duration": 120, "is_live": True})
            assert validate({"duration": None})
            assert validate({"duration": None}, incomplete=True) is None
            with pytest.raises(ValueError, match="budget"):
                options["progress_hooks"][0]({"downloaded_bytes": settings.video_max_input_bytes + 1})
            path = Path(options["outtmpl"])
            paths.append(path)
            path.write_bytes(b"public audio")
            if blocked:
                raise RuntimeError("YouTube blocked access")
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=Downloader))
    transcript = {"language": "en", "segments": [{"text": "MPI", "start": 4, "end": 8}]}
    transcribe = AsyncMock(return_value=transcript)
    monkeypatch.setattr(video_index_service, "_transcribe", transcribe)
    fetcher = YouTubeTranscriptFetcher()
    monkeypatch.setattr(fetcher, "_fetch_api", lambda *args: None)
    if blocked:
        with pytest.raises(ValueError, match="Upload the source video"):
            await fetcher.fetch("https://youtu.be/abcdefghijk")
        transcribe.assert_not_awaited()
    else:
        result = await fetcher.fetch("https://youtu.be/abcdefghijk")
        assert result == {**transcript, "method": "youtube_audio_whisper"}
        transcribe.assert_awaited_once()
    assert paths and all(not path.exists() for path in paths)
