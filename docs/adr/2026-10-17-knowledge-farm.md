# ADR: Knowledge Farm owns gameplay; Auth owns awarded user score

Status: accepted for implementation. Owners: Farm, Auth, Frontend.

Use a separate Go service and PostgreSQL database for the educational farm.
Reuse supplied XanhMarket sprites, selection and server-clock growth concepts;
exclude real-farm commerce/integrations. Use existing React UI rather than add
an engine dependency for six starter plots. Species learning cards have cited
external sources and explicitly distinguish game timers from real husbandry.

A server-graded quiz or recall flashcard is required for every harvest. The
initial content pack belongs to Farm; this is not an LMS assessment attempt.
Grant 5 score per correct harvest up to 100/day UTC. Future course-scoped
content requires authenticated LMS APIs, never database joins.

Write harvest, answer receipt and reward outbox in one transaction. Publish
`farm.harvest.reward.v1` keyed by Auth user ID with stable challenge/harvest ID.
Auth validates HMAC and atomically inserts an inbox receipt and increments
`users.total_score`. The existing field remains the canonical account score.
Java retries failed delivery without acknowledging it. UI distinguishes
awarded farm score from the eventual account total.

Consequences: no distributed transaction and no synchronous Auth dependency
on each harvest. Duplicate delivery is harmless. An invalid event blocks its
partition until repaired; operations must monitor lag. Outbox/inbox retention
and coordinated key rotation are required. Task-score increments also become
atomic and User dirty-column updates avoid overwriting concurrent increments.

See [feature and rollout guide](../features/KNOWLEDGE_FARM.md).
