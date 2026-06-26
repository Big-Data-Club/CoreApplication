---
name: bdc-lms-service
description: >
  Use when working in lms-service/ — Go 1.24 + Gin + PostgreSQL + Redis + Kafka.
  Covers: courses, sections, content, quizzes, forum, enrollments, file upload,
  progress tracking, Kafka AI command publishing, Redis job cache, user sync.
triggers:
  - lms-service/
  - golang
  - gin
  - lms
  - kafka
version: "2.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC LMS Service — Developer Skill

## Role & Scope

You are working on `lms-service/` — the Learning Management System backend.
Built with Go 1.24 + Gin + PostgreSQL + Redis + Kafka.

**Entry point:** `cmd/api/main.go`
**Base URL:** `http://localhost:8081` | Docker: `http://lms-backend:8081`
**Auth:** JWT (same `JWT_SECRET` as auth-service)
**Sync auth:** `X-Sync-Secret: ${LMS_SYNC_SECRET}` (must equal `LMS_API_SECRET`)
**AI auth:** `X-AI-Secret: ${AI_SERVICE_SECRET}` (outbound to ai-service)

---

## Project Structure

```
lms-service/
├── cmd/api/main.go                  Init config, DI, Gin router, start Kafka consumers
├── internal/
│   ├── dto/                         Request/Response validation models
│   ├── handler/                     Gin HTTP handlers
│   ├── middleware/                   JWT auth, rate limiting
│   ├── repository/                  Raw SQL queries (database/sql, explicit $N params)
│   └── service/                     Business logic layer
├── pkg/
│   ├── ai/client.go                 HTTP client for fast synchronous AI queries only
│   ├── cache/redis.go               Redis methods (stores ai_job:{id}, session data)
│   ├── kafka/consumer.go            Subscribes to ai.job.status, ai.document.processed.status
│   └── kafka/producer.go            Publishes to lms.ai.command, lms.document.uploaded
├── migrations/
│   ├── 001_core_schema.sql          Users, courses, sections, content, enrollments
│   ├── 002_quiz_system.sql          Quizzes, questions, attempts, answers, analytics
│   ├── 003_forum.sql                Forum posts, comments, votes, triggers
│   └── 004_ai_references.sql        Soft reference columns for AI integration
└── docs/                            Swagger generated files
```

---

## Architecture — Event-Driven AI Integration

**Rule:** Never use synchronous HTTP to ai-service for tasks that involve LLM calls,
embedding generation, or document processing. These operations take 5 s – 5 min.

### Async AI Workflow

```
Client  ->  POST /api/v1/ai/quiz          (LMS handler)
LMS     ->  Kafka lms.ai.command          {job_id, "GENERATE_QUIZ", payload}
LMS     ->  Redis SET ai_job:{job_id}     {status: "pending"}
LMS     ->  HTTP 202                      {job_id}

ai-worker  polls Kafka lms.ai.command
ai-worker  ->  Kafka ai.job.status        {job_id, "processing"}
ai-worker  ->  executes work
ai-worker  ->  Kafka ai.job.status        {job_id, "completed", result}

lms-service polls Kafka ai.job.status
lms-service ->  Redis SET ai_job:{job_id} {status, result}

Client  ->  GET /api/v1/ai/jobs/{job_id}/status   -> reads Redis
```

---

## Database Conventions

Always use explicit positional parameters in queries:

```go
// ✅ Correct
row := db.QueryRowContext(ctx,
    "SELECT id, title FROM courses WHERE id = $1 AND created_by = $2",
    courseID, userID)

// ❌ Wrong — never use fmt.Sprintf to build SQL
query := fmt.Sprintf("SELECT * FROM courses WHERE id = %d", courseID)
```

---

## Standard CRUD Workflow

### Step 1 — Define DTOs in `internal/dto/`

```go
// internal/dto/course_dto.go
type CreateCourseRequest struct {
    Title       string `json:"title"        binding:"required,min=3,max=255"`
    Description string `json:"description"`
    Level       string `json:"level"        binding:"omitempty,oneof=BEGINNER INTERMEDIATE ADVANCED ALL_LEVELS"`
}

type CourseResponse struct {
    ID          int64  `json:"id"`
    Title       string `json:"title"`
    Description string `json:"description"`
    Status      string `json:"status"`
    CreatedBy   int64  `json:"created_by"`
    CreatedAt   string `json:"created_at"`
}
```

### Step 2 — Repository in `internal/repository/`

```go
// internal/repository/course_repository.go
type CourseRepository struct{ db *sql.DB }

func (r *CourseRepository) Create(ctx context.Context, req *dto.CreateCourseRequest, userID int64) (*dto.CourseResponse, error) {
    var resp dto.CourseResponse
    err := r.db.QueryRowContext(ctx,
        `INSERT INTO courses (title, description, level, created_by, status)
         VALUES ($1, $2, $3, $4, 'DRAFT')
         RETURNING id, title, description, status, created_by, created_at`,
        req.Title, req.Description, req.Level, userID,
    ).Scan(&resp.ID, &resp.Title, &resp.Description, &resp.Status, &resp.CreatedBy, &resp.CreatedAt)
    return &resp, err
}
```

### Step 3 — Service in `internal/service/`

```go
// internal/service/course_service.go
type CourseService struct{ repo *repository.CourseRepository }

func (s *CourseService) CreateCourse(ctx context.Context, req *dto.CreateCourseRequest, userID int64, role string) (*dto.CourseResponse, error) {
    if role != "TEACHER" && role != "ADMIN" {
        return nil, errors.New("insufficient permissions")
    }
    return s.repo.Create(ctx, req, userID)
}
```

### Step 4 — Handler in `internal/handler/`

```go
// internal/handler/course_handler.go
func (h *CourseHandler) Create(c *gin.Context) {
    var req dto.CreateCourseRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    userID, _ := c.Get("user_id")
    role,   _ := c.Get("user_role")

    result, err := h.service.CreateCourse(c.Request.Context(), &req, userID.(int64), role.(string))
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}
```

### Step 5 — Register in `cmd/api/main.go`

```go
courseHandler := handler.NewCourseHandler(courseService)
v1 := router.Group("/api/v1")
v1.Use(middleware.JWTAuth(cfg.JWTSecret))
{
    v1.POST("/courses", courseHandler.Create)
    v1.GET("/courses",  courseHandler.GetAll)
}
```

### Step 6 — Generate Swagger docs

```bash
swag init -g cmd/api/main.go
```

---

## Triggering Async AI Tasks

```go
// internal/handler/ai_handler.go
func (h *AIHandler) GenerateQuiz(c *gin.Context) {
    var req dto.GenerateQuizRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    jobID := uuid.New().String()

    // 1. Publish Kafka command
    event := kafka.AICommandEvent{
        JobID:       jobID,
        CommandType: "GENERATE_QUIZ",
        Payload: map[string]interface{}{
            "node_id":             req.NodeID,
            "course_id":           req.CourseID,
            "created_by":          req.CreatedBy,
            "bloom_levels":        req.BloomLevels,
            "questions_per_level": req.QuestionsPerLevel,
        },
    }
    if err := kafka.PublishAICommand(c.Request.Context(), event); err != nil {
        c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Kafka unavailable"})
        return
    }

    // 2. Seed Redis status
    payload, _ := json.Marshal(map[string]string{"job_id": jobID, "status": "pending"})
    h.redisCache.Set(c.Request.Context(), "ai_job:"+jobID, payload, 24*time.Hour)

    // 3. Return 202
    c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]string{
        "job_id": jobID, "status": "pending",
    }))
}
```

---

## User Sync Endpoint

Consumed by auth-service `UserSyncService`. Validates `X-Sync-Secret` header.

```
POST /api/v1/sync/users       — single user upsert
POST /api/v1/sync/users/bulk  — bulk upsert array
DELETE /api/v1/sync/user/{id} — soft-delete / block
```

---

## File Upload & Storage

`STORAGE_TYPE` controls the backend:
- `local` — filesystem at `/app/uploads` (dev only)
- `minio` — MinIO bucket `lms-files` (required for AI service to access files)

**Important:** Set `STORAGE_TYPE=minio` in any environment where ai-worker
processes documents. The AI worker reads files directly from MinIO via SDK.

---

## AI Index Status Columns in LMS DB

`section_content.ai_index_status` is a display-only column in the LMS database.
The authoritative indexing state lives in `content_index_status` on the AI
PostgreSQL instance. The LMS column is updated via the `ai.document.processed.status`
Kafka topic (consumed by lms-service).

```go
// After receiving ai.document.processed.status event:
_, err = db.ExecContext(ctx,
    `UPDATE section_content SET ai_index_status = $1, ai_indexed_at = $2 WHERE id = $3`,
    event.Status, time.Now(), event.ContentID)
```

---

## Code Quality Checklist

```
[ ] All SQL uses explicit $N parameters — no fmt.Sprintf in queries
[ ] All errors returned explicitly — never discard with _
[ ] go vet ./... passes before commit
[ ] swag init run after adding or modifying any endpoint
[ ] AI tasks use Kafka publish + 202 pattern — not synchronous HTTP to ai-service
[ ] Kafka publish failure returns 503, not 500
[ ] Redis job status seeded before returning 202
[ ] New env var added to docker-compose.yml + .env.example
[ ] Handler only calls Service — never Repository directly
```