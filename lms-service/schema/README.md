# Consolidated schema: lms-service

Start with [`current.sql`](current.sql). This single file contains the final
columns, table constraints, indexes, functions, triggers and repository seed
defaults reconstructed from this service's SQL. It is not a concatenation of
CREATE/ALTER steps, and it is not a dump of a live Neon database.

Tables covered: `bulk_enrollment_logs`, `competency_frameworks`, `content_progress`, `content_skills`, `course_co_teachers`, `course_competencies`, `course_sections`, `courses`, `enrollments`, `farm_learning_attempts`, `forum_comments`, `forum_posts`, `forum_votes`, `knowledge_node_mastery`, `learner_skill_states`, `learning_events`, `learning_notification_events`, `learning_notification_reads`, `lms_callback_receipts`, `lms_file_assets`, `lms_processed_interactions`, `lms_quiz_effects`, `micro_lesson_interactions`, `micro_lesson_jobs`, `micro_lessons`, `micro_quiz_jobs`, `micro_quizzes`, `organization_members`, `organizations`, `permissions`, `question_bank_items`, `question_skills`, `quiz_analytics`, `quiz_answer_options`, `quiz_attempts`, `quiz_correct_answers`, `quiz_questions`, `quiz_student_answers`, `quizzes`, `role_definitions`, `role_permissions`, `section_content`, `section_overview_jobs`, `section_overview_lessons`, `section_overview_quizzes`, `skill_prerequisites`, `skill_recommendations`, `skill_relationships`, `skills`, `user_roles`, `users`.

The historical patches remain in [`migrations/releases`](../migrations/releases/)
for deployed ledgers, audit and rollback compatibility. Existing deployments
continue to use that history; startup does not execute `schema/current.sql`.
Lab, Chat and Workspace snapshots also record the covered original migration
names so startup does not replay the baseline after a fresh installation.

## Inspect or regenerate

From the Core repository root, with Docker available:

```sh
python3 scripts/build-sql-snapshots.py --service lms-service
python3 scripts/build-sql-snapshots.py --service lms-service --check
python3 scripts/check-sql-releases.py
```

The generator creates isolated PostgreSQL 17 databases in a temporary container,
replays repository inputs, normalizes the resulting DDL and checks a second
restoration. It reads no production connection settings and stops its own
container afterwards. `manifest.json` records input hashes and the output hash.
Only regenerate the affected service to avoid unrelated seed timestamp changes.

For a deliberately empty PostgreSQL database, an operator can apply the file
with `psql -X -v ON_ERROR_STOP=1 --single-transaction -f lms-service/schema/current.sql`.
The operator must select the intended empty database through normal libpq
connection settings. Do not run this file against an existing Neon database.
New deployed changes still use forward migrations; after review, update this
consolidated representation through the generator.
