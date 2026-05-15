# Micro Quiz — AI-Generated Node-Comprehensive Quiz Feature

Thêm tính năng **Micro Quiz**: AI tự động tạo bộ câu hỏi trắc nghiệm bao quát toàn bộ kiến thức của một knowledge node, với số lượng câu hỏi không cố định (phụ thuộc vào số chunks). Giáo viên có thể chỉnh sửa nội dung quiz (Markdown) trước khi xuất bản.

## User Review Required

> [!IMPORTANT]
> **Thiết kế "1 quiz = 1 node, N câu hỏi = f(chunks)"**: Mỗi node sẽ tạo ra 1 micro quiz riêng. Số câu hỏi cho mỗi node = số chunks của node đó (mỗi chunk → 1 câu hỏi). Mỗi câu hỏi được gắn 1 Bloom level, luân phiên qua 6 cấp độ (remember → understand → apply → analyze → evaluate → create) rồi lặp lại. Như vậy nếu node có 12 chunks thì sẽ có 12 câu hỏi, mỗi level 2 câu.

> [!IMPORTANT]  
> **Cùng hệ thống job với micro-lesson**: Micro quiz reuse hoàn toàn pattern job lifecycle (queued → processing → completed/failed), HTTP callback từ AI → LMS, cùng UI flow (generate modal → drawer poll → edit → publish). Khác biệt chính: nội dung lưu dạng quiz Markdown (câu hỏi + đáp án + giải thích), publish tạo QUIZ SectionContent thay vì TEXT.

> [!WARNING]
> **Publish flow**: Khi publish micro quiz, hệ thống sẽ tạo một SectionContent type=QUIZ kèm quiz record + quiz_questions. Khác với micro lesson (chỉ tạo TEXT content). Giáo viên edit quiz ở dạng Markdown trước publish, hệ thống parse Markdown thành structured questions khi publish.

## Open Questions

> [!IMPORTANT]
> 1. **Quiz format khi publish**: Có 2 lựa chọn:
>    - **Option A**: Store quiz as Markdown only (editable, rendered in ContentViewer as markdown quiz). Không tạo quiz_questions records → không tự động chấm điểm.
>    - **Option B**: Parse Markdown thành structured quiz_questions + quiz_answer_options khi publish → hỗ trợ auto-grade.
>    - **Đề xuất**: Option A cho MVP (giáo viên tự chấm / review), sau này upgrade lên B. Hoặc Option B nếu muốn auto-grade ngay.
>    
>    **Tôi đề xuất Option B** — parse thành structured quiz khi publish để tận dụng hệ thống quiz sẵn có (auto-grade, analytics, spaced repetition).

> [!NOTE]
> 2. **YouTube source**: Micro quiz cũng hỗ trợ YouTube source giống micro lesson?  
>    **Đề xuất**: Có, reuse cùng pipeline auto-index.

---

## Proposed Changes

### AI Service — `ai-service/`

#### [NEW] `app/services/micro_quiz_service.py`
New service that generates quiz questions per node. Pipeline:
1. Same auto-index check as micro-lesson (reuse `_fetch_nodes_and_chunks`)
2. For each node: iterate its chunks, assign Bloom levels round-robin
3. Per-chunk LLM call → generate 1 MCQ question (4 options, 1 correct, with explanation)
4. Format output as Markdown quiz block per node
5. POST results back to LMS via callback

Key differences from `micro_lesson_service.py`:
- LLM prompt produces structured quiz JSON: `{question_text, options: [{text, is_correct}], explanation, bloom_level}`
- Output Markdown format:
  ```
  ## Câu 1 (Remember)
  **Câu hỏi**: ...
  - [ ] A. ...
  - [x] B. ... ✓
  - [ ] C. ...
  - [ ] D. ...
  > **Giải thích**: ...
  ```
- Variable question count = len(chunks) per node

#### [NEW] `app/api/endpoints/micro_quizzes.py`
FastAPI router mirroring `micro_lessons.py`:
- `POST /ai/micro-quizzes/generate` — file-based generation
- `POST /ai/micro-quizzes/generate-youtube` — YouTube-based

#### [MODIFY] `main.py`
- Register `micro_quizzes.router`

#### [MODIFY] `app/core/llm_gateway/types.py`
- Add `TASK_MICRO_QUIZ_GEN = "micro_quiz_gen"` task code

---

### LMS Service — `lms-service/`

#### [NEW] `migrations/V003__micro_quizzes.sql`
```sql
CREATE TABLE IF NOT EXISTS micro_quiz_jobs (
    -- Same structure as micro_lesson_jobs
    id                BIGSERIAL PRIMARY KEY,
    course_id         BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id        BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    source_file_path  VARCHAR(1000),
    source_file_type  VARCHAR(100),
    source_url        VARCHAR(1000),
    language          VARCHAR(10) NOT NULL DEFAULT 'vi',
    status            VARCHAR(20) NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','processing','completed','failed')),
    progress          INT DEFAULT 0,
    stage             VARCHAR(64) DEFAULT '',
    quizzes_count     INT DEFAULT 0,
    error             TEXT,
    created_by        BIGINT NOT NULL REFERENCES users(id),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS micro_quizzes (
    id                   BIGSERIAL PRIMARY KEY,
    job_id               BIGINT NOT NULL REFERENCES micro_quiz_jobs(id) ON DELETE CASCADE,
    course_id            BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id           BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id    BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    title                VARCHAR(500) NOT NULL,
    summary              TEXT,
    markdown_content     TEXT NOT NULL,          -- full quiz as editable Markdown
    questions_json       JSONB DEFAULT '[]',     -- structured [{question_text, options, explanation, bloom_level}]
    questions_count      INT DEFAULT 0,
    order_index          INT NOT NULL DEFAULT 0,
    status               VARCHAR(20) NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft','published','archived')),
    published_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    node_id              BIGINT,
    language             VARCHAR(10) DEFAULT 'vi',
    created_by           BIGINT NOT NULL REFERENCES users(id),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at         TIMESTAMP
);
```

#### [NEW] `internal/models/micro_quiz.go`
Go model structs: `MicroQuizJob`, `MicroQuiz` (mirrors MicroLesson pattern)

#### [NEW] `internal/dto/micro_quiz_dto.go`
DTOs:
- `GenerateMicroQuizzesRequest` (contentId, youtubeUrl, sectionId, language)
- `UpdateMicroQuizRequest` (title, summary, markdown_content, questions_json, order_index)
- `PublishMicroQuizRequest` (section_id, order_index)
- `MicroQuizStatusCallback`, `MicroQuizzesCallback` (AI → LMS callbacks)

#### [NEW] `internal/repository/micro_quiz_repo.go`
Repository with same pattern as `micro_lesson_repo.go`:
- `CreateJob`, `GetJob`, `ListJobsByCourse`, `UpdateJobStatus`
- `CreateQuiz`, `GetQuiz`, `ListQuizzesByJob`, `UpdateQuizContent`, `MarkPublished`, `DeleteQuiz`

#### [NEW] `internal/handler/micro_quiz_handler.go`
HTTP handlers mirroring `micro_lesson_handler.go`:
- `GenerateMicroQuizzes` — POST trigger
- `ListJobs` / `GetJob` — job polling
- `UpdateQuiz` — save teacher edits
- `PublishQuiz` — create QUIZ SectionContent + quiz + quiz_questions from `questions_json`
- `DeleteQuiz` — drop draft
- `CallbackStatus` / `CallbackQuizzes` — AI service callbacks

**Publish flow (Option B)**:
1. Create SectionContent type=QUIZ
2. Create quizzes record
3. Parse `questions_json` → insert `quiz_questions` + `quiz_answer_options`
4. Mark micro quiz as published

#### [MODIFY] `pkg/ai/client.go`
Add new request/response types + methods:
- `GenerateMicroQuizzes()` → POST `/ai/micro-quizzes/generate`
- `GenerateMicroQuizzesFromYouTube()` → POST `/ai/micro-quizzes/generate-youtube`

#### [MODIFY] `cmd/api/main.go`
- Initialize `microQuizRepo`, `microQuizHandler`
- Register routes:
  ```
  /courses/:courseId/micro-quizzes/generate    [POST]
  /courses/:courseId/micro-quizzes/jobs        [GET]
  /micro-quizzes/jobs/:jobId                  [GET]
  /micro-quizzes/:quizId                      [PUT]
  /micro-quizzes/:quizId/publish              [POST]
  /micro-quizzes/:quizId                      [DELETE]
  /internal/micro-quizzes/status              [POST]
  /internal/micro-quizzes/quizzes             [POST]
  ```

#### [MODIFY] `cmd/api/main.go` (node merge cascade)
Add cascade for `micro_quizzes.node_id` in the `NodeMergedConsumer`.

---

### Frontend — `frontend/src/`

#### [NEW] `services/microQuizService.ts`
Client mirroring `microLessonService.ts`:
- Types: `MicroQuizJob`, `MicroQuiz`, `GenerateQuizOptions`, `JobWithQuizzes`
- Methods: `generate()`, `listJobs()`, `getJob()`, `updateQuiz()`, `publishQuiz()`, `deleteQuiz()`

#### [NEW] `components/lms/teacher/micro/GenerateMicroQuizzesModal.tsx`
Config modal for micro quiz generation. Same UI pattern as `GenerateMicroLessonsModal.tsx` but with quiz-specific copy:
- Source picker (file / YouTube)
- Language selector
- Section picker (optional)
- Submit → fires generation

#### [NEW] `components/lms/teacher/micro/MicroQuizzesDrawer.tsx`
Job polling + quiz editing drawer. Same pattern as `MicroLessonsDrawer.tsx`:
- Poll job status
- Render quiz cards with Markdown preview
- Inline editing of Markdown quiz content
- Publish to a section (creates QUIZ content)

#### [MODIFY] `components/lms/teacher/page/ContentTab.tsx`
Add "Tạo micro quiz" button alongside existing "Tạo bài học micro" button.

---

## Architecture Diagram

```
Teacher clicks "Tạo Micro Quiz"
         │
    ┌────▼──────────────┐
    │  Frontend:         │
    │  GenerateMicroQui- │
    │  zzesModal.tsx     │
    └────┬──────────────┘
         │ POST /courses/:id/micro-quizzes/generate
    ┌────▼──────────────┐
    │  LMS Handler:      │
    │  micro_quiz_handler│
    │  .go               │
    │  1. Auth check      │
    │  2. Create job row  │
    │  3. Fire-and-forget │
    │     to AI service   │
    └────┬──────────────┘
         │ POST /ai/micro-quizzes/generate
    ┌────▼──────────────┐
    │  AI Service:       │
    │  micro_quiz_       │
    │  service.py        │
    │  1. Auto-index     │
    │  2. Fetch nodes    │
    │  3. For each node: │
    │     For each chunk:│
    │       LLM → 1 MCQ  │
    │  4. Format Markdown│
    │  5. POST callback  │
    └────┬──────────────┘
         │ POST /internal/micro-quizzes/quizzes
    ┌────▼──────────────┐
    │  LMS Handler:      │
    │  CallbackQuizzes   │
    │  → Insert rows     │
    └────┬──────────────┘
         │
    ┌────▼──────────────┐
    │  Frontend:         │
    │  MicroQuizzesDrawer│
    │  polls GET /jobs/  │
    │  → shows quiz cards│
    │  → teacher edits   │
    │  → publish         │
    └───────────────────┘
```

---

## Verification Plan

### Automated Tests
- `go test ./internal/repository/...` — verify micro quiz repo SQL
- `go test ./internal/handler/...` — verify handler bindings
- `pytest ai-service/tests/` — verify new endpoint + service
- Frontend: manual test in browser (generate → poll → edit → publish)

### Manual Verification
1. Upload a document → trigger micro quiz generation → verify quiz cards appear in drawer
2. Edit quiz markdown → save → verify persistence
3. Publish quiz → verify QUIZ SectionContent + quiz_questions created
4. Student takes the published quiz → verify auto-grade works
5. Verify node merge cascade updates micro_quizzes.node_id
