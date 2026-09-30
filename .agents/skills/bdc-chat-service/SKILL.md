---
name: bdc-chat-service
description: Chat service guidance for Go/Gin HTTP and WebSocket messaging, Redis pub/sub, persistence, and authenticated channel access.
triggers: [chat-service, websocket, chat, redis-pubsub, channel]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Chat Service

## Scope

`chat-service/cmd/api/main.go` starts the Go/Gin API. `internal/handler/`,
`internal/repository/`, `pkg/hub/`, and `pkg/cache/` contain the HTTP/WebSocket,
data, hub, and Redis integration boundaries. Migrations are forward-only.

## Rules

- Authenticate both HTTP and WebSocket/session paths and verify membership or
  role before reading, posting, editing, deleting, or subscribing to a channel.
- Treat Redis pub/sub as delivery infrastructure, not the source of record;
  persist/audit messages according to the established repository workflow.
- Keep WebSocket payloads compatible, bounded, validated, and resilient to
  disconnect/reconnect. Do not trust a client-supplied user ID.
- Do not add a Kafka topic merely for in-process chat fan-out. If a durable
  cross-service event is required, design the contract with Data/DevOps and
  document it in `docs/DATA_PLATFORM.md`.
- Run `go test ./...` and cover permission, malformed payload, reconnect, and
  persistence failure paths relevant to the change.
