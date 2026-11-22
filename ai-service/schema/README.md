# Consolidated schema: ai-service

Start with [`current.sql`](current.sql). This single file contains the final
columns, table constraints, indexes, functions, triggers and repository seed
defaults reconstructed from this service's SQL. It is not a concatenation of
CREATE/ALTER steps, and it is not a dump of a live Neon database.

Tables covered: `agent_episodes`, `agent_message_feedback`, `agent_messages`, `agent_sessions`, `agent_telemetry_logs`, `ai_diagnoses`, `ai_quiz_generations`, `document_chunks`, `content_index_status`, `course_blueprints`, `course_material_routing_jobs`, `embedding_reindex_jobs`, `flashcard_repetitions`, `flashcards`, `graph_consolidation_log`, `knowledge_node_relations`, `knowledge_nodes`, `lab_authoring_jobs`, `llm_api_keys`, `llm_models`, `llm_providers`, `llm_usage_log`, `mcp_api_keys`, `mcp_audit_log`, `mcp_authoring_requests`, `personal_flashcard_decks`, `personal_flashcard_jobs`, `personal_flashcard_reviews`, `personal_flashcards`, `quiz_insight_results`, `review_delivery_receipts`, `spaced_repetitions`, `speech_jobs`, `student_facts`, `student_knowledge_progress`, `studio_jobs`, `studio_legacy_media_swept`, `studio_projects`, `studio_shared_youtube_connection`, `studio_temporary_media`, `studio_youtube_uploads`, `task_model_bindings`, `user_concept_mastery`.

Fresh-schema adjustment: the old `idx_sr_student_due_today` used `CURRENT_DATE` in a partial-index predicate, which PostgreSQL rejects because it is not immutable. The consolidated snapshot uses `next_review_date IS NOT NULL` for that covering index. Historical SQL stays byte-for-byte unchanged; this does not alter a production index.

The historical patches remain in [`migrations/releases`](../migrations/releases/)
for deployed ledgers, audit and rollback compatibility. Existing deployments
continue to use that history; startup does not execute `schema/current.sql`.
Lab, Chat and Workspace snapshots also record the covered original migration
names so startup does not replay the baseline after a fresh installation.

## Inspect or regenerate

From the Core repository root, with Docker available:

```sh
python3 scripts/build-sql-snapshots.py --service ai-service
python3 scripts/build-sql-snapshots.py --service ai-service --check
python3 scripts/check-sql-releases.py
```

The generator creates isolated PostgreSQL 17 databases in a temporary container,
replays repository inputs, normalizes the resulting DDL and checks a second
restoration. It reads no production connection settings and stops its own
container afterwards. `manifest.json` records input hashes and the output hash.
Only regenerate the affected service to avoid unrelated seed timestamp changes.

For a deliberately empty PostgreSQL database, an operator can apply the file
with `psql -X -v ON_ERROR_STOP=1 --single-transaction -f ai-service/schema/current.sql`.
The operator must select the intended empty database through normal libpq
connection settings. Do not run this file against an existing Neon database.
New deployed changes still use forward migrations; after review, update this
consolidated representation through the generator.
