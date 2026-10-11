# Chat delivery and capacity

Messages remain in PostgreSQL. The browser sends messages through the authenticated
HTTP API and only clears its draft after persistence is acknowledged. WebSocket
events deliver updates through Redis across replicas. The existing event envelope
is unchanged; channel administration also publishes an internal `access_changed`
event to disconnect sockets whose subscriptions must be checked again.

The hub uses eight queues partitioned by channel ID to keep arrival order inside
each room. Each socket has 64 outbound slots; a full socket or worker queue forces
reconnection rather than blocking other clients. Queue overflow recovery refreshes
the currently open channel's latest history. Pub/sub is not durable: Redis publish
failures can delay recipient visibility until history is refreshed. This change
does not introduce an outbox or guarantee exactly-once delivery.

## Configuration

| Variable | Default | Scope |
| --- | --- | --- |
| `WS_MAX_CLIENTS` | 10000 | admitted sockets per replica |
| `WS_MAX_CLIENTS_PER_USER` | 5 | sockets per user per replica |
| `CHAT_READ_REQUESTS_PER_MINUTE` | 600 | HTTP reads per user across replicas |
| `CHAT_WRITE_REQUESTS_PER_MINUTE` | 120 | HTTP mutations per user across replicas |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | explicit allowed browser origins, comma separated |

WebSocket inbound frames have a 32 KiB limit and a token bucket of 40 frames,
refilling at 10/sec. JWT expiration closes the socket. Membership is checked during
upgrade, before writes, and on heartbeat; admin changes also trigger immediate
subscription revalidation. Redis presence uses one MGET per presence request.
Apply migration V006 for the covering user membership lookup index. History uses
the existing V001 `(channel_id, id DESC)` index without adding a duplicate.

The defaults are admission ceilings, **not measured supported production load**.
Redis must be shared across replicas. Ensure production browser origins are set
explicitly, including when the WebSocket is proxied through the frontend origin.
Tune ceilings against process memory, PostgreSQL pool capacity, Redis latency,
socket counts, reconnect rates, HTTP 429/503 rates and message delivery latency.

## Verification

Run `go test -race ./...` inside chat-service. Run
`go test ./pkg/hub -run '^$' -bench BenchmarkFanOut1000 -benchmem` for a synthetic,
in-process fan-out benchmark. It excludes Redis, database, network and browsers.
Use the existing performance-tests workflow and an approved isolated environment
for end-to-end capacity testing; do not stress the running developer/production stack.

## Browser behavior

Chat uses the application light/dark theme and switches between channel list and
conversation on mobile. Personal settings control sound, compact spacing and
Enter-to-send, persisted separately per account in browser storage. Failed sends
retain text and attachments. Reconnection uses exponential backoff with jitter,
refreshes accessible channels and fetches the active history; message IDs reconcile
HTTP receipts with replayed WebSocket events. History is capped at 500 messages per
visited channel, with unloaded channels storing unread counters instead of bodies.
Administrators manage channels, role permissions and explicit membership at
`/settings/chat-roles`; empty role permissions stay empty rather than being replaced
with implicit grants.
