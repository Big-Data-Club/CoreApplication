# Curriculum scope and evidence-based learning design

Status: implemented for Studio sources, course question-bank generation and
source-based micro-lesson/micro-quiz generation. Owners: LMS, AI and frontend.

## Decision

Teachers select a course, chapters (`section_ids`) or lessons (`content_ids`).
TEXT, DOCUMENT, VIDEO and IMAGE are lesson source formats. Knowledge nodes,
graph relationships and parent/child chunks are internal retrieval and
interpretation tools. Their number does not determine the number of lessons,
slides, quizzes or questions.

LMS resolves the selection into canonical source records after checking course
edit access. Overlapping chapter/lesson selections form a union in curriculum
order. A foreign or unsupported explicit selection fails the entire request.
Plain-text lessons can be used before indexing. Documents/video/images require
ready extracted content; an unavailable selected lesson fails visibly, rather
than disappearing from the scope or being replaced by its title.

AI hydrates parent passages within the same course and content, deduplicates
parents, preserves unassigned material/images, and supplies course-scoped graph
relationships to the planner. Related concepts guide interpretation; graph
labels alone are never sufficient factual evidence. This implementation keeps
the evidence inside the selected lessons; it does not retrieve arbitrary
unselected courses or lessons.

The shared planner groups material by measurable objectives and cognitive load,
with bounded, source-labelled evidence. Several nodes/materials can support one
unit and one complex concept can require multiple units. Plans must reference
valid sources and cover every selected source. Micro quizzes use three candidate
checks per objective (understanding, application, analysis), independently of
chunk count; at least two valid distinct questions are required. Failed units
fail the generation before draft callbacks, avoiding silent partial coverage.

Course bank questions preserve content IDs, internal node IDs, objective and a
verbatim source quote in `settings.authoring_context`. The legacy singular
`node_id` is null for these synthesized questions and for new micro outputs;
it no longer implies an artificial one-to-one mapping. Micro-question JSON
also carries `source_quote`. This does not yet introduce a many-to-many mastery
mapping for micro lessons in LMS persistence.

## Boundaries and compatibility

- `POST /api/v1/courses/{courseId}/authoring-context` accepts curriculum IDs.
  `check_only` validates authoring permission without loading sources. Service
  calls must supply a positive authenticated user ID; their roles are loaded
  from LMS rather than inheriting the internal transport's administrator role.
- The existing LMS question-bank generation request accepts `section_ids` and
  `content_ids`; both empty means the whole course. Canonical source snapshots
  cross the authenticated LMS-to-AI boundary, not the browser-to-AI boundary.
- LMS uses the new `/ai/quiz/generate-from-sources` path so an older AI deployment
  fails instead of silently ignoring the new scope and sampling the whole graph.
- Studio accepts `type: curriculum` with the same ID arrays, resolves through
  LMS, and stores per-lesson snapshots. Adding sources invalidates the old plan
  and artifacts. The BFF always overwrites `user_id` with session identity.
- Existing node-based APIs remain for older clients/agent tools. Existing
  generated records are not rewritten. No database migration or Kafka schema
  change is required.

Deploy LMS and AI before the frontend. A partially upgraded installation may
return a visible unavailable/unsupported error; it must not broaden the scope.
Rollback frontend first, then AI/LMS. Studio snapshots and question provenance
follow their existing project/bank record retention and permissions. Their
purpose is authoring and source review, not analytics publication.

## Verification and limits

Offline regressions cover canonical selection, overlap, invalid course scope,
parent hydration/deduplication, missing sources, semantic grouping, coverage,
valid answer cardinality, source quotes and model-independent quiz count.
These structural checks do not prove factual or pedagogical quality. Review
generated content with real lesson fixtures before publishing.

Current lifecycle remains unchanged: Studio planning and bank generation use
the existing request flow, and micro generation uses existing background tasks
and LMS callbacks. Durable worker migration is a separate operational follow-up;
this change does not claim worker retry guarantees. Studio currently exposes
slides, documents and reports. Its `video` backend kind renders slide material;
this work does not implement a finished video encoder or narration service.

Source of truth:
[scope resolution](../../lms-service/internal/service/authoring_context.go),
[evidence](../../ai-service/app/services/learning_context.py),
[learning design](../../ai-service/app/services/learning_design.py),
[Studio](../../ai-service/app/services/studio/studio_service.py).
