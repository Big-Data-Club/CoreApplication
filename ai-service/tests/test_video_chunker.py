from app.services.chunker import VideoTranscriptChunker


def test_video_chunks_keep_real_overlap_and_playable_timecodes():
    segments = [
        {"start": second, "end": second + 10, "text": f"Sentence {second}."}
        for second in range(0, 140, 10)
    ]

    chunks = VideoTranscriptChunker(
        segment_duration_sec=45,
        overlap_sec=12,
        min_segment_duration_sec=20,
        target_chars=10_000,
    ).chunk_whisper_json({"segments": segments})

    assert len(chunks) >= 2
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.source_type == "video" for chunk in chunks)
    assert all(chunk.start_time_sec is not None and chunk.end_time_sec is not None for chunk in chunks)
    assert all(chunk.start_time_sec < chunk.end_time_sec for chunk in chunks)
    # The second chunk really contains the tail of the preceding chunk, not
    # merely an overlapping timestamp.
    assert "Sentence 30." in chunks[0].text
    assert "Sentence 30." in chunks[1].text


def test_video_chunker_ignores_invalid_and_empty_segments():
    chunks = VideoTranscriptChunker().chunk_whisper_json({"segments": [
        {"start": "bad", "end": 3, "text": "Ignored"},
        {"start": 4, "end": 3, "text": "Usable evidence."},
        {"start": 5, "end": 8, "text": ""},
    ]})

    assert len(chunks) == 1
    assert chunks[0].start_time_sec == 4
    assert chunks[0].end_time_sec == 5
