---
name: bdc-auth-service
description: Auth and management service guidance for Spring Boot identity, roles, user synchronisation, and notification consumption.
triggers: [auth-and-management-service, spring-boot, java, jwt, identity, organisation]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Auth and Management Service

## Scope

This service owns identity, authentication, roles and management-domain data.
Inspect the current controller/service/repository/configuration code before
adding a route; package names and API paths are implementation details, not
guaranteed by this skill.

## Rules

- Keep authorization decisions server-side and use the established Spring
  Security configuration, exception handling, DTO validation, and transaction
  conventions.
- Preserve the authenticated user-sync contract to LMS. Do not make LMS query
  Auth tables directly.
- `personalize.notification.trigger` is consumed by the notification listener;
  changes require compatible event handling, data/privacy review, and the Data
  Platform guide update.
- Keep passwords, JWT material, SMTP configuration, and internal secrets out of
  logs, tests, docs, and response payloads.
- Add tests for unauthorised, forbidden, validation, and failure paths along
  with the intended success case. Run `mvn test`.

## References

- `src/main/java/` - implementation source of truth.
- `src/main/resources/` - runtime configuration templates.
- `docs/DATA_PLATFORM.md` - Kafka notification contract.
