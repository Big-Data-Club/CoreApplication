# Collaborative Workspace owns documents and permissions

Status: implemented locally; production rollout is separate.

The BDC Workspace combines personal notes, team documents and structured
databases. Reference Fields and Notion inform interaction patterns; their
application data and complete implementation are not copied. There is no Notion
account import requirement.

## Decision

Use a dedicated Node service with an owned PostgreSQL database. Reuse BDC access
JWTs. NextAuth-authenticated BFF routes forward the server session access token;
browser identity fields never determine authority. Space roles and explicit page
grants are evaluated on every REST action and document write. Personal space
membership is private. A page grant does not expose ordinary descendants;
database grants include the record pages that constitute that database.

Use Yjs CRDTs with the BlockNote editor. A single-use hashed, 60-second ticket is
sent in the first WebSocket frame, never in a URL. Socket authority expires with
the BDC access token. A document row lock serializes durable merged updates;
operation IDs make replay idempotent. ACK follows the commit. PostgreSQL
LISTEN/NOTIFY fans durable state out to replicas; periodic sync catches missed
notifications. Redis and Chat remain independent.

Keep a separate IndexedDB recovery document per account/page/generation.
Server state is authoritative; local recovery merges only after edit permission
is confirmed. Live editors may keep drafting during an interruption. An initial
offline page open requires a connection. Version restore increments generation
so old offline updates cannot resurrect restored-away content.

Records are pages with typed properties. Views share record identities. Personal
view settings remain private. Formula parsing has bounded tokens/depth and no
JavaScript evaluation. Relations/rollups recheck source permissions. Metadata and
property updates use expected versions rather than silently overwriting peers.

Store bounded private attachments in PostgreSQL initially, so backup and resource
authorization are coherent for the expected sub-100-user deployment. File bytes
are sniffed; URLs are served only after current page permission checks. Moving to
private object storage requires a new storage adapter and authorization contract.

Reuse canonical Tasks through authenticated APIs. Workspace stores links, not
duplicate tasks or leaderboard points. Notebook conversion fetches entries for
the current user through the AI API. AI assistance uses the existing tool-free
flash mode and requires an explicit insert action after preview.

## Consequences

A new service/database and WebSocket route must be operated and backed up.
LISTEN requires a direct or session pool connection. PostgreSQL growth must be
monitored; version and archive retention is non-destructive until product policy
is agreed. Two-browser and ten-writer correctness checks are not capacity/stress
certification. Production canary, managed database setup, backup verification and
observability are required before inviting the full audience.
