"""Local audio transcription keeps real speech and timestamps without API calls."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import video_index_service as video


@pytest.mark.asyncio
async def test_extracts_lossless_mono_audio_before_transcribing(monkeypatch, tmp_path):
    def ffmpeg(command, **kwargs):
        assert command[:3] == ["ffmpeg", "-y", "-nostdin"]
        assert command[command.index("-map") + 1] == "0:a:0"
        assert command[command.index("-ar") + 1] == "16000"
        assert command[command.index("-ac") + 1] == "1"
        assert command[command.index("-c:a") + 1] == "flac"
        Path(command[-1]).write_bytes(b"test audio")
    model = Mock()
    model.transcribe.return_value = (iter([SimpleNamespace(text=" MPI Scatterv ", start=3.5, end=7.5)]),
                                    SimpleNamespace(language="vi"))
    monkeypatch.setattr(video, "_run", ffmpeg)
    monkeypatch.setattr(video, "_get_whisper_model", AsyncMock(return_value=model))
    result = await video.VideoIndexService()._transcribe(tmp_path / "video.mp4", tmp_path)
    assert result == {"language": "vi", "segments": [{"text": "MPI Scatterv", "start": 3.5, "end": 7.5}]}
    assert model.transcribe.call_args.kwargs["vad_filter"] is True


@pytest.mark.asyncio
async def test_transcript_remains_usable_when_optional_visuals_return_nothing(monkeypatch):
    service = video.VideoIndexService()
    paths = []
    def probe(path):
        paths.append(path)
        return 30
    monkeypatch.setattr(video, "_probe_duration", probe)
    monkeypatch.setattr(service, "_transcribe", AsyncMock(return_value={"language": "vi", "segments": [
        {"text": "MPI Scatterv giải thích phân phối dữ liệu.", "start": 3, "end": 10}]}))
    monkeypatch.setattr(service, "_extract_visual_evidence", AsyncMock(return_value=[]))
    text, chunks = await service.extract(b"video")
    assert "MPI Scatterv" in text
    assert chunks[0].start_time_sec == 3 and chunks[0].end_time_sec == 10
    assert all(not path.exists() for path in paths)
