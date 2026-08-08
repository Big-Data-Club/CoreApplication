# Course blueprint workflow

The create-course button and teacher chatbot must open `CourseBlueprintWorkspace` rather than creating a course immediately. The workspace uses the following API contract:

1. Upload one or more `file` parts to `POST /api/v1/files/upload`. A one-file response remains unchanged; a multi-file request returns `{ files: [...] }`.
2. LMS first resolves the teacher's permitted organizations and eligible co-teachers. Send them as `allowed_organization_ids` and `allowed_co_teacher_ids`, together with the current `governance` selection, to `POST /ai/course-blueprints`. Each file entry has `{ id, filename, file_path, content_type }`; `text` is optional for chatbot attachments that are already normalised.
3. Render the returned `plan` as editable course metadata, tags, governance (organization, visibility, co-teachers, thumbnail), and draggable chapters. Show each chapter's source file chips and prerequisite chips. Do not show a plain numeric order as the reason for an ordering decision.
4. Save edits through `PUT /ai/course-blueprints/{id}` with `version`. On `409`, reload the draft; on `422`, display the returned graph/source errors next to the affected chapter.
5. Only enable “Tạo khóa học” after `POST .../{id}/approve` succeeds. The LMS materialiser then creates the draft course, sections in `validation.topological_order`, and document content from the saved manifest. “Hủy” calls `POST .../{id}/cancel`; it creates nothing.

The same component is requested from chatbot tool event `create_course_from_materials` with `{ origin: "chatbot" }`. This keeps all uploads, review, edit, approve, and cancel behaviour identical across entry points.

## Operational model routing

Bind the `course_blueprint` task in Admin → LLM Registry. Use a capable structured-output model as primary and at least one lower-cost compatible fallback. The workflow maps every source into small bounded calls, then reduces the evidence ledger, so it does not depend on putting a whole textbook in one model context. Gateway key pools, TPM limits, usage logging, and fallback policy apply exactly as they do to existing tasks.

## Durable execution

`POST /course-blueprints` persists a `PROCESSING` row then emits a Kafka wake-up
event. The dedicated `course-blueprint-worker` owns OCR and LLM stages; it uses
a database lease and recovery sweep so a browser disconnect, pod restart, or
Kafka delivery retry cannot discard a job. It is deployed separately from the
general AI worker and can scale independently.
