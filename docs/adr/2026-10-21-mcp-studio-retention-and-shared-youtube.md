# Own-model MCP authoring and temporary video delivery

Status: implemented; operator rollout and live provider/channel validation pending.

External agents need authorized course evidence and deterministic creation tools
while using their own text model. Long-lived MP4 copies are outside the desired
storage model; a course still needs a durable playable video after expiry.

Expose focused MCP profiles for Studio, flashcards and combined authoring. Keep
source reads paged and scene writes atomic in size: narrative outline before one
scene per call. Authoring never calls BDC text models; managed TTS remains shared
with the flashcard player. Write-scoped keys and explicit confirmation are
required. Accepted learners may create private course projects/cards; course
lesson writes and shared-channel uploads require owner/co-teacher access.

Reuse MinIO rather than worker-local disks. Workers/pods can restart or move;
manifest-backed private objects remain downloadable until their deadline. Reject
public policies/versioning. Persist source artifacts privately; expire MP4, scene
audio and video ZIP at ready + ten minutes. Register objects before PUT, retire
abandoned staging bytes, and run cleanup independently of long renders. Access
expiry is strict; physical deletion retries through storage/worker outages.

Use the shared system YouTube channel configured by admin. Personal-channel
publishing is download-and-upload by the user. Move channel credentials from
ephemeral frontend files into encrypted AI-owned storage; OAuth administration
requires an ADMIN session and state validation. Workers receive credentials only
through the secret-authenticated frontend bridge, never through MCP. Save and
resume one encrypted upload session to avoid duplicate videos after a lost
response. Do not extend temporary retention for uploads.

Attach only a processed unlisted/public YouTube link to a course draft. Check
actual visibility and course/section membership at publication. Reconcile
Studio provenance on retries. An unlisted YouTube link is shareable outside LMS
authorization; user confirmation includes that visibility choice. PDF/Markdown
still attach directly after review.

Rollout requires V022 and matching AI worker/HTTP/frontend. Reconnect the admin
channel once; do not silently import old filesystem tokens. Retire legacy public
video/audio/bundle objects. Never roll an old worker back into active rendering
without stopping its persistent-public-video path.
