// lms-service/internal/handler/micro_lesson_handler.go
// HTTP handlers for the Micro-Learning feature.
//
// Public flow (UI):
//   POST   /api/v1/courses/:courseId/micro-lessons/generate    → trigger
//   GET    /api/v1/courses/:courseId/micro-lessons/jobs        → list jobs
//   GET    /api/v1/micro-lessons/jobs/:jobId                   → job + lessons
//   PUT    /api/v1/micro-lessons/:lessonId                     → save edits
//   POST   /api/v1/micro-lessons/:lessonId/publish             → make a SectionContent
//   DELETE /api/v1/micro-lessons/:lessonId                     → drop draft
//
// Internal flow (AI service callback):
//   POST /api/v1/internal/micro-lessons/status   ← progress / status updates
//   POST /api/v1/internal/micro-lessons/lessons  ← bulk push of generated lessons

package handler

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type MicroLessonHandler struct {
	microRepo  *repository.MicroLessonRepository
	courseRepo *repository.CourseRepository
	aiClient   *ai.Client
}

func NewMicroLessonHandler(
	microRepo *repository.MicroLessonRepository,
	courseRepo *repository.CourseRepository,
	aiClient *ai.Client,
) *MicroLessonHandler {
	return &MicroLessonHandler{
		microRepo:  microRepo,
		courseRepo: courseRepo,
		aiClient:   aiClient,
	}
}

// ── Public endpoints ──────────────────────────────────────────────────────────

// GenerateMicroLessons godoc
// @Summary  Trigger micro-lesson generation from a content file or YouTube URL
// @Tags     Micro-Lessons
// @Accept   json
// @Produce  json
// @Param    courseId path int true "Course ID"
// @Security BearerAuth
// @Router   /courses/{courseId}/micro-lessons/generate [post]
func (h *MicroLessonHandler) GenerateMicroLessons(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.GenerateMicroLessonsRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if body.TargetMinutes < 2 || body.TargetMinutes > 15 {
		body.TargetMinutes = 5
	}
	if body.Language == "" {
		body.Language = "vi"
	}

	// Authorization: only the course owner or an admin may trigger generation.
	if userRole != "ADMIN" {
		course, err := h.courseRepo.GetByID(c.Request.Context(), courseID)
		if err != nil {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if course.CreatedBy != userID {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only the course owner can generate micro-lessons"))
			return
		}
	}

	// Resolve source: either content_id (file in MinIO) or a YouTube URL.
	job := &models.MicroLessonJob{
		CourseID:      courseID,
		TargetMinutes: body.TargetMinutes,
		Language:      body.Language,
		Status:        models.MicroJobStatusQueued,
		CreatedBy:     userID,
	}
	if body.SectionID != nil {
		job.SectionID = sql.NullInt64{Int64: *body.SectionID, Valid: true}
	}

	useYouTube := body.YouTubeURL != ""
	if !useYouTube {
		if body.ContentID == 0 {
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request",
				"Phải cung cấp content_id hoặc youtube_url"))
			return
		}
		content, err := h.courseRepo.GetContentByID(c.Request.Context(), body.ContentID)
		if err != nil {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Content not found"))
			return
		}

		filePath, fileType := resolveFileFromContent(content)
		if filePath == "" {
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("no_file",
				"Content không có file để tạo micro-lesson"))
			return
		}
		job.SourceContentID = sql.NullInt64{Int64: body.ContentID, Valid: true}
		job.SourceFilePath = sql.NullString{String: filePath, Valid: true}
		job.SourceFileType = sql.NullString{String: fileType, Valid: true}
	} else {
		job.SourceURL = sql.NullString{String: body.YouTubeURL, Valid: true}
		if body.ContentID != 0 {
			job.SourceContentID = sql.NullInt64{Int64: body.ContentID, Valid: true}
		}
	}

	created, err := h.microRepo.CreateJob(c.Request.Context(), job)
	if err != nil {
		logger.Error("CreateJob failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Fire-and-forget call to AI service. AI will POST status updates and
	// the generated lessons back via the internal callback endpoints below.
	if useYouTube {
		go func() {
			var sourceContentID *int64
			if body.ContentID != 0 {
				sourceContentID = &body.ContentID
			}
			_, err := h.aiClient.GenerateMicroLessonsFromYouTube(c, ai.GenerateMicroLessonsFromYouTubeRequest{
				JobID:           created.ID,
				CourseID:        courseID,
				SectionID:       body.SectionID,
				SourceContentID: sourceContentID,
				YouTubeURL:      body.YouTubeURL,
				TargetMinutes:   body.TargetMinutes,
				Language:        body.Language,
			})
			if err != nil {
				logger.Error(fmt.Sprintf("AI YT trigger failed for job %d", created.ID), err)
				_ = h.microRepo.UpdateJobStatus(c, created.ID, models.MicroJobStatusFailed, 0,
					"trigger_failed", 0, err.Error())
			}
		}()
	} else {
		go func() {
			_, err := h.aiClient.GenerateMicroLessons(c, ai.GenerateMicroLessonsRequest{
				JobID:           created.ID,
				CourseID:        courseID,
				SectionID:       body.SectionID,
				SourceContentID: nullable(job.SourceContentID),
				SourceFilePath:  job.SourceFilePath.String,
				SourceFileType:  job.SourceFileType.String,
				TargetMinutes:   body.TargetMinutes,
				Language:        body.Language,
			})
			if err != nil {
				logger.Error(fmt.Sprintf("AI trigger failed for job %d", created.ID), err)
				_ = h.microRepo.UpdateJobStatus(c, created.ID, models.MicroJobStatusFailed, 0,
					"trigger_failed", 0, err.Error())
			}
		}()
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]interface{}{
		"job_id": created.ID,
		"status": created.Status,
	}))
}

// ListJobs godoc
// @Summary  List micro-lesson generation jobs for a course
// @Tags     Micro-Lessons
// @Produce  json
// @Param    courseId path int true "Course ID"
// @Security BearerAuth
// @Router   /courses/{courseId}/micro-lessons/jobs [get]
func (h *MicroLessonHandler) ListJobs(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	jobs, err := h.microRepo.ListJobsByCourse(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(jobs))
}

// GetJob godoc
// @Summary  Get a single micro-lesson job and all its lessons
// @Tags     Micro-Lessons
// @Produce  json
// @Param    jobId path int true "Job ID"
// @Security BearerAuth
// @Router   /micro-lessons/jobs/{jobId} [get]
func (h *MicroLessonHandler) GetJob(c *gin.Context) {
	jobID, _ := strconv.ParseInt(c.Param("jobId"), 10, 64)
	job, err := h.microRepo.GetJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}
	lessons, err := h.microRepo.ListLessonsByJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"job":     job,
		"lessons": lessons,
	}))
}

// UpdateLesson godoc
// @Summary  Save instructor edits to a draft micro-lesson
// @Tags     Micro-Lessons
// @Accept   json
// @Produce  json
// @Param    lessonId path int true "Lesson ID"
// @Security BearerAuth
// @Router   /micro-lessons/{lessonId} [put]
func (h *MicroLessonHandler) UpdateLesson(c *gin.Context) {
	lessonID, _ := strconv.ParseInt(c.Param("lessonId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.UpdateMicroLessonRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	lesson, err := h.microRepo.GetLesson(c.Request.Context(), lessonID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Lesson not found"))
		return
	}
	if userRole != "ADMIN" && lesson.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot edit this lesson"))
		return
	}
	if body.EstimatedMinutes < 2 || body.EstimatedMinutes > 30 {
		body.EstimatedMinutes = lesson.EstimatedMinutes
	}

	objectivesJSON, _ := json.Marshal(body.Objectives)
	var summary sql.NullString
	if body.Summary != "" {
		summary = sql.NullString{String: body.Summary, Valid: true}
	}

	if err := h.microRepo.UpdateLessonContent(
		c.Request.Context(),
		lessonID,
		body.Title,
		summary,
		objectivesJSON,
		body.MarkdownContent,
		body.EstimatedMinutes,
		body.OrderIndex,
	); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Lesson updated"))
}

// PublishLesson godoc
// @Summary  Promote a draft micro-lesson into a published SectionContent + auto-index it
// @Description Creates a TEXT SectionContent in the chosen section, marks the lesson
//              as published, and triggers the existing auto-index pipeline so the
//              lesson is immediately searchable in the RAG index.
// @Tags     Micro-Lessons
// @Accept   json
// @Produce  json
// @Param    lessonId path int true "Lesson ID"
// @Security BearerAuth
// @Router   /micro-lessons/{lessonId}/publish [post]
func (h *MicroLessonHandler) PublishLesson(c *gin.Context) {
	lessonID, _ := strconv.ParseInt(c.Param("lessonId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.PublishMicroLessonRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	lesson, err := h.microRepo.GetLesson(c.Request.Context(), lessonID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Lesson not found"))
		return
	}
	if userRole != "ADMIN" && lesson.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot publish this lesson"))
		return
	}

	// Resolve next order index in the target section if caller didn't pass one
	orderIdx := body.OrderIndex
	if orderIdx <= 0 {
		existing, _ := h.courseRepo.ListContentBySection(c.Request.Context(), body.SectionID)
		orderIdx = len(existing) + 1
	}

	metadata := map[string]interface{}{
		"content":            lesson.MarkdownContent,
		"estimated_minutes":  lesson.EstimatedMinutes,
		"micro_lesson_id":    lesson.ID,
		"micro_lesson_job":   lesson.JobID,
		"micro_lesson_image_urls": rawJSONOrEmpty(lesson.ImageURLs),
	}
	metaBytes, _ := json.Marshal(metadata)

	content := &models.SectionContent{
		SectionID:   body.SectionID,
		Type:        models.ContentTypeText,
		Title:       lesson.Title,
		Description: sql.NullString{String: firstNonEmpty(lesson.Summary.String, ""), Valid: lesson.Summary.Valid},
		OrderIndex:  orderIdx,
		Metadata:    metaBytes,
		IsPublished: true,
		IsMandatory: true,
		CreatedBy:   userID,
	}
	saved, err := h.courseRepo.CreateContent(c.Request.Context(), content)
	if err != nil {
		logger.Error("CreateContent (publish) failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	if err := h.microRepo.MarkPublished(c.Request.Context(), lessonID, saved.ID); err != nil {
		logger.Error("MarkPublished failed", err)
	}

	// Fire auto-index for the freshly created TEXT content using the
	// existing pipeline. Errors are logged but don't fail the publish.
	go func(contentID, courseID int64, title, md string) {
		if _, err := h.aiClient.AutoIndexText(c, ai.AutoIndexTextRequest{
			ContentID:   contentID,
			CourseID:    courseID,
			Title:       title,
			TextContent: md,
		}); err != nil {
			logger.Error(fmt.Sprintf("Auto-index after publish failed content=%d", contentID), err)
		}
	}(saved.ID, lesson.CourseID, lesson.Title, lesson.MarkdownContent)

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"micro_lesson_id":    lesson.ID,
		"section_content_id": saved.ID,
		"status":             "published",
	}))
}

// DeleteLesson godoc
// @Summary  Delete a draft micro-lesson
// @Tags     Micro-Lessons
// @Produce  json
// @Param    lessonId path int true "Lesson ID"
// @Security BearerAuth
// @Router   /micro-lessons/{lessonId} [delete]
func (h *MicroLessonHandler) DeleteLesson(c *gin.Context) {
	lessonID, _ := strconv.ParseInt(c.Param("lessonId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	lesson, err := h.microRepo.GetLesson(c.Request.Context(), lessonID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Lesson not found"))
		return
	}
	if userRole != "ADMIN" && lesson.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot delete this lesson"))
		return
	}
	if err := h.microRepo.DeleteLesson(c.Request.Context(), lessonID); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Lesson deleted"))
}

// ── Internal callback endpoints (AI service → LMS) ─────────────────────────────

// CallbackStatus is invoked by the AI service to report progress / failure.
func (h *MicroLessonHandler) CallbackStatus(c *gin.Context) {
	var body dto.MicroLessonStatusCallback
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if err := h.microRepo.UpdateJobStatus(
		c.Request.Context(),
		body.JobID, body.Status, body.Progress, body.Stage, body.LessonsCount, body.Error,
	); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("ok"))
}

// CallbackLessons is invoked by the AI service to push the generated lessons.
func (h *MicroLessonHandler) CallbackLessons(c *gin.Context) {
	var body dto.MicroLessonsCallback
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	job, err := h.microRepo.GetJob(c.Request.Context(), body.JobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}

	for i, l := range body.Lessons {
		objectives, _ := json.Marshal(l.Objectives)
		images, _ := json.Marshal(l.ImageURLs)
		summary := sql.NullString{}
		if l.Summary != "" {
			summary = sql.NullString{String: l.Summary, Valid: true}
		}

		lesson := &models.MicroLesson{
			JobID:            body.JobID,
			CourseID:         body.CourseID,
			Title:            l.Title,
			Summary:          summary,
			Objectives:       objectives,
			MarkdownContent:  l.MarkdownContent,
			EstimatedMinutes: l.EstimatedMinutes,
			OrderIndex:       l.OrderIndex,
			ImageURLs:        images,
			Language:         body.Language,
			CreatedBy:        job.CreatedBy,
		}
		if body.SectionID != nil {
			lesson.SectionID = sql.NullInt64{Int64: *body.SectionID, Valid: true}
		}
		if body.SourceContentID != nil {
			lesson.SourceContentID = sql.NullInt64{Int64: *body.SourceContentID, Valid: true}
		}
		if l.NodeID != nil {
			lesson.NodeID = sql.NullInt64{Int64: *l.NodeID, Valid: true}
		}
		if _, err := h.microRepo.CreateLesson(c.Request.Context(), lesson); err != nil {
			logger.Error(fmt.Sprintf("CreateLesson failed for job %d (idx %d)", body.JobID, i), err)
		}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"job_id":       body.JobID,
		"created":      len(body.Lessons),
	}))
}

// ── Helpers ────────────────────────────────────────────────────────────────────

func resolveFileFromContent(content *models.SectionContent) (string, string) {
	filePath := ""
	fileType := ""
	if content.FilePath.Valid && content.FilePath.String != "" {
		filePath = content.FilePath.String
	}
	if content.FileType.Valid {
		fileType = content.FileType.String
	}
	if filePath == "" && len(content.Metadata) > 0 {
		var meta map[string]interface{}
		if err := json.Unmarshal(content.Metadata, &meta); err == nil {
			if v, ok := meta["file_path"].(string); ok && v != "" {
				filePath = v
			}
			if v, ok := meta["file_type"].(string); ok && v != "" {
				fileType = v
			}
			if filePath == "" {
				if v, ok := meta["video_url"].(string); ok && v != "" {
					filePath = v
				}
			}
		}
	}
	return filePath, fileType
}

func nullable(v sql.NullInt64) *int64 {
	if !v.Valid {
		return nil
	}
	return &v.Int64
}

func firstNonEmpty(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

func rawJSONOrEmpty(b []byte) interface{} {
	if len(b) == 0 {
		return []interface{}{}
	}
	var v interface{}
	if err := json.Unmarshal(b, &v); err != nil {
		return []interface{}{}
	}
	return v
}