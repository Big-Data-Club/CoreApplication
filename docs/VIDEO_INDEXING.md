# Video indexing

## Contract

Every indexed video produces retrievable chunks with `source_type=video`,
`start_time_sec` and `end_time_sec`. A citation can therefore open the player
at the exact evidence time (`#t=<start_time_sec>`).

## Pipeline

1. The worker downloads the object, then rejects files over 500 MB or videos
   over two hours before codec/model processing.
2. FFmpeg extracts a mono 16 kHz, 32 kbps temporary audio stream. This avoids
   holding uncompressed WAV files on the already constrained K3s disk.
3. Faster-Whisper transcribes with VAD enabled. The transcript is the primary
   source of truth and supplies the timestamps.
4. `VideoTranscriptChunker` groups complete spoken ideas into approximately
   90-second chunks (minimum 35 seconds), retaining 12 seconds of *actual*
   preceding transcript as overlap.
5. When `VIDEO_VISUAL_INDEX_ENABLED=true`, the pipeline samples at most eight
   representative frames (normally one per 90 seconds). The VLM describes only
   those frames. Each description becomes a timestamped visual-evidence chunk,
   so silent slides, diagrams and code are searchable without treating every
   video frame as content.
6. Audio and visual chunks are sorted into one timeline, embedded, linked to
   knowledge nodes, and stored in PostgreSQL/Qdrant through the standard RAG
   path. The temporary directory is removed when the job exits, including on
   errors.

## Operational controls

| Variable | Default | Purpose |
| --- | ---: | --- |
| `VIDEO_MAX_INPUT_BYTES` | 500 MB | Hard input-size safety limit. |
| `VIDEO_MAX_DURATION_SEC` | 7200 | Maximum video length. |
| `VIDEO_WHISPER_MODEL` | `base` | CPU int8 model; higher models need a dedicated worker. |
| `VIDEO_VISUAL_INDEX_ENABLED` | `true` | Enable bounded VLM frame descriptions. |
| `VIDEO_KEYFRAME_INTERVAL_SEC` | 90 | Representative-frame interval. |
| `VIDEO_MAX_KEYFRAMES` | 8 | Hard cap on VLM calls per video. |

For the current single-node K3s host, keep video jobs serial and leave the
existing 90-minute worker timeout in place. If indexing long lecture archives
becomes common, move Whisper/video work to a separately resourced worker rather
than increasing the AI API pod memory or Kafka concurrency.

## YouTube policy

YouTube URLs are indexed from accessible published captions only. BDC Hub does
not download YouTube audio as an automatic fallback: YouTube may require a
per-video Proof-of-Origin token for audio/subtitle delivery, which makes server
downloads brittle and can lead to 403 or IP-block responses. If captions are
unavailable, the interface asks the content owner to upload the source video;
that upload uses the bounded local transcription pipeline above.
