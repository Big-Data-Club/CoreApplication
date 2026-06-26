// lms-service/internal/handler/section_overview_handler.go
// HTTP handlers for the Section Overview feature.
//
// Public flow (teacher):
//   POST   /api/v1/courses/:courseId/sections/:sectionId/overview/generate  -> GenerateOverview
//   GET    /api/v1/courses/:courseId/sections/:sectionId/overview/jobs       -> ListJobs
//   GET    /api/v1/section-overview/jobs/:jobId                              -> GetJob
//   PUT    /api/v1/section-overview/lessons/:lessonId                        -> UpdateLesson
//   POST   /api/v1/section-overview/lessons/:lessonId/publish                -> PublishLesson
//   PUT    /api/v1/section-overview/quizzes/:quizId                          -> UpdateQuiz
//   POST   /api/v1/section-overview/quizzes/:quizId/publish                  -> PublishQuiz
//   DELETE /api/v1/section-overview/jobs/:jobId                              -> DeleteJob
//
// Internal callbacks (AI service -> LMS):
//   POST /api/v1/internal/section-overview/status   ← progress / status updates
//   POST /api/v1/internal/section-overview/results  ← completed lesson + quiz data
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
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

// SectionOverviewHandler handles all Section Overview HTTP requests.
type SectionOverviewHandler struct {
	repo       *repository.SectionOverviewRepository
	courseRepo *repository.CourseRepository
	quizRepo   *repository.QuizRepository
	aiClient   *ai.Client
	redisCache *cache.RedisCache
}

// NewSectionOverviewHandler wires the handler to its dependencies.
func NewSectionOverviewHandler(
	repo *repository.SectionOverviewRepository,
	courseRepo *repository.CourseRepository,
	quizRepo *repository.QuizRepository,
	aiClient *ai.Client,
	redisCache *cache.RedisCache,
) *SectionOverviewHandler {
	return &SectionOverviewHandler{
		repo:       repo,
		courseRepo: courseRepo,
		quizRepo:   quizRepo,
		aiClient:   aiClient,
		redisCache: redisCache,
	}
}

// ── Public endpoints ──────────────────────────────────────────────────────────

// GenerateOverview godoc
// @Summary  Trigger section overview generation (lesson + quiz) for a section
// @Tags     Section-Overview
// @Accept   json
// @Produce  json
// @Param    courseId  path int true "Course ID"
// @Param    sectionId path int true "Section ID"
// @Security BearerAuth
// @Router   /courses/{courseId}/sections/{sectionId}/overview/generate [post]
func (h *SectionOverviewHandler) GenerateOverview(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.GenerateSectionOverviewRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if body.QuestionCount < 5 || body.QuestionCount > 30 {
		body.QuestionCount = 10
	}
	if body.Language == "" {
		body.Language = "vi"
	}

	// Authorization: course owner or admin only.
	if userRole != "ADMIN" {
		course, err := h.courseRepo.GetByID(c.Request.Context(), courseID)
		if err != nil {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if course.CreatedBy != userID {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only the course owner can generate a section overview"))
			return
		}
	}

	// Fetch all content in the section and filter to those already indexed.
	allContent, err := h.courseRepo.ListContentBySection(c.Request.Context(), sectionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	var indexedContents []*models.SectionContent
	for _, sc := range allContent {
		if sc.AIIndexStatus.Valid && sc.AIIndexStatus.String == "indexed" {
			indexedContents = append(indexedContents, sc)
		}
	}
	if len(indexedContents) == 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("no_indexed_content",
			"Chưa có nội dung nào được AI index trong chương này"))
		return
	}

	// Persist the job.
	job, err := h.repo.CreateJob(c.Request.Context(), sectionID, courseID, body.Language, body.QuestionCount, userID)
	if err != nil {
		logger.Error("SectionOverview.CreateJob failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Build contents_info slice for the AI service.
	contentsInfo := make([]ai.SectionOverviewContentInfo, 0, len(indexedContents))
	for _, sc := range indexedContents {
		desc := ""
		if sc.Description.Valid {
			desc = sc.Description.String
		}
		contentsInfo = append(contentsInfo, ai.SectionOverviewContentInfo{
			ContentID:   sc.ID,
			Title:       sc.Title,
			ContentType: string(sc.Type),
			Description: desc,
		})
	}

	// Fire-and-forget: call AI service asynchronously.
	jobID := job.ID
	go func() {
		if _, err := h.aiClient.GenerateSectionOverview(c, ai.GenerateSectionOverviewRequest{
			JobID:         jobID,
			SectionID:     sectionID,
			CourseID:      courseID,
			QuestionCount: body.QuestionCount,
			Language:      body.Language,
			ContentsInfo:  contentsInfo,
		}); err != nil {
			logger.Error(fmt.Sprintf("AI GenerateSectionOverview trigger failed for job %d", jobID), err)
			_ = h.repo.UpdateJobStatus(c, jobID, "failed", 0, "trigger_failed", err.Error(), "")
		}
	}()

	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]interface{}{
		"job_id": job.ID,
		"status": job.Status,
	}))
}

// ListJobs godoc
// @Summary  List section overview generation jobs for a section
// @Tags     Section-Overview
// @Produce  json
// @Param    courseId  path int true "Course ID"
// @Param    sectionId path int true "Section ID"
// @Security BearerAuth
// @Router   /courses/{courseId}/sections/{sectionId}/overview/jobs [get]
func (h *SectionOverviewHandler) ListJobs(c *gin.Context) {
	sectionID, _ := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	jobs, err := h.repo.ListJobsBySection(c.Request.Context(), sectionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(jobs))
}

// GetJob godoc
// @Summary  Get a single section overview job with its lesson and quiz
// @Tags     Section-Overview
// @Produce  json
// @Param    jobId path int true "Job ID"
// @Security BearerAuth
// @Router   /section-overview/jobs/{jobId} [get]
func (h *SectionOverviewHandler) GetJob(c *gin.Context) {
	jobID, _ := strconv.ParseInt(c.Param("jobId"), 10, 64)

	job, err := h.repo.GetJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}

	detail := dto.SectionOverviewJobDetailResponse{Job: *job}

	// Lesson — may not exist yet if AI hasn't finished.
	lesson, err := h.repo.GetLesson(c.Request.Context(), jobID)
	if err == nil {
		detail.Lesson = lesson
	}

	// Quiz — may not exist yet.
	quiz, err := h.repo.GetQuiz(c.Request.Context(), jobID)
	if err == nil {
		detail.Quiz = quiz
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(detail))
}

// UpdateLesson godoc
// @Summary  Save teacher edits to a draft overview lesson
// @Tags     Section-Overview
// @Accept   json
// @Produce  json
// @Param    lessonId path int true "Lesson ID"
// @Security BearerAuth
// @Router   /section-overview/lessons/{lessonId} [put]
func (h *SectionOverviewHandler) UpdateLesson(c *gin.Context) {
	lessonID, _ := strconv.ParseInt(c.Param("lessonId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.UpdateOverviewLessonRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	lesson, err := h.repo.GetLessonByID(c.Request.Context(), lessonID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Lesson not found"))
		return
	}
	if userRole != "ADMIN" && lesson.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot edit this lesson"))
		return
	}

	if err := h.repo.UpdateLesson(c.Request.Context(), lessonID, body); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Lesson updated"))
}

// PublishLesson godoc
// @Summary  Promote a draft overview lesson into a published SectionContent and auto-index it
// @Tags     Section-Overview
// @Accept   json
// @Produce  json
// @Param    lessonId path int true "Lesson ID"
// @Security BearerAuth
// @Router   /section-overview/lessons/{lessonId}/publish [post]
func (h *SectionOverviewHandler) PublishLesson(c *gin.Context) {
	lessonID, _ := strconv.ParseInt(c.Param("lessonId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.PublishOverviewLessonRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	lesson, err := h.repo.GetLessonByID(c.Request.Context(), lessonID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Lesson not found"))
		return
	}
	if lesson.Status == "published" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("already_published", "Lesson đã được xuất bản"))
		return
	}
	if userRole != "ADMIN" && lesson.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot publish this lesson"))
		return
	}

	// Resolve next order index if caller didn't supply one.
	orderIdx := body.OrderIndex
	if orderIdx <= 0 {
		existing, _ := h.courseRepo.ListContentBySection(c.Request.Context(), body.SectionID)
		orderIdx = len(existing) + 1
	}

	metadata := map[string]interface{}{
		"content":              lesson.MarkdownContent,
		"overview_lesson_id":   lessonID,
		"overview_job_id":      lesson.JobID,
	}
	metaBytes, _ := json.Marshal(metadata)

	content := &models.SectionContent{
		SectionID:   body.SectionID,
		Type:        models.ContentTypeText,
		Title:       lesson.Title,
		Description: sql.NullString{String: lesson.Summary, Valid: lesson.Summary != ""},
		OrderIndex:  orderIdx,
		Metadata:    metaBytes,
		IsPublished: true,
		IsMandatory: true,
		CreatedBy:   userID,
	}
	saved, err := h.courseRepo.CreateContent(c.Request.Context(), content)
	if err != nil {
		logger.Error("SectionOverview.PublishLesson CreateContent failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	if err := h.repo.MarkLessonPublished(c.Request.Context(), lessonID, saved.ID); err != nil {
		logger.Error("SectionOverview.MarkLessonPublished failed", err)
	}

	// Invalidate cache so the published lesson appears immediately
	if h.redisCache != nil {
		_ = h.redisCache.Delete(c.Request.Context(), cache.KeySectionContents(body.SectionID))
	}

	// Auto-index in the background.
	go func(contentID, courseID int64, title, md string) {
		if _, err := h.aiClient.AutoIndexText(c, ai.AutoIndexTextRequest{
			ContentID:   contentID,
			CourseID:    courseID,
			Title:       title,
			TextContent: md,
		}); err != nil {
			logger.Error(fmt.Sprintf("Auto-index after overview lesson publish failed content=%d", contentID), err)
		}
	}(saved.ID, lesson.CourseID, lesson.Title, lesson.MarkdownContent)

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"overview_lesson_id":  lessonID,
		"section_content_id": saved.ID,
		"status":             "published",
	}))
}

// UpdateQuiz godoc
// @Summary  Save teacher edits to a draft overview quiz
// @Tags     Section-Overview
// @Accept   json
// @Produce  json
// @Param    quizId path int true "Quiz ID"
// @Security BearerAuth
// @Router   /section-overview/quizzes/{quizId} [put]
func (h *SectionOverviewHandler) UpdateQuiz(c *gin.Context) {
	quizID, _ := strconv.ParseInt(c.Param("quizId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.UpdateOverviewQuizRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	quiz, err := h.repo.GetQuizByID(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found"))
		return
	}
	if userRole != "ADMIN" && quiz.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot edit this quiz"))
		return
	}

	if err := h.repo.UpdateQuiz(c.Request.Context(), quizID, body); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Quiz updated"))
}

// PublishQuiz godoc
// @Summary  Promote a draft overview quiz into a published QUIZ SectionContent
// @Tags     Section-Overview
// @Accept   json
// @Produce  json
// @Param    quizId path int true "Quiz ID"
// @Security BearerAuth
// @Router   /section-overview/quizzes/{quizId}/publish [post]
func (h *SectionOverviewHandler) PublishQuiz(c *gin.Context) {
	quizID, _ := strconv.ParseInt(c.Param("quizId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.PublishOverviewQuizRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	oq, err := h.repo.GetQuizByID(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found"))
		return
	}
	if oq.Status == "published" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("already_published", "Quiz đã được xuất bản"))
		return
	}
	if userRole != "ADMIN" && oq.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot publish this quiz"))
		return
	}

	questions := oq.Questions
	if len(questions) == 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("empty_quiz", "Quiz không có câu hỏi"))
		return
	}

	// Resolve next order index.
	orderIdx := body.OrderIndex
	if orderIdx <= 0 {
		existing, _ := h.courseRepo.ListContentBySection(c.Request.Context(), body.SectionID)
		orderIdx = len(existing) + 1
	}

	// Step 1: Create SectionContent (type=QUIZ).
	metadata := map[string]interface{}{
		"overview_quiz_id": oq.ID,
		"overview_job_id":  oq.JobID,
		"ai_generated":     true,
		"questions_count":  len(questions),
	}
	metaBytes, _ := json.Marshal(metadata)

	content := &models.SectionContent{
		SectionID:   body.SectionID,
		Type:        models.ContentTypeQuiz,
		Title:       oq.Title,
		Description: sql.NullString{String: oq.Summary, Valid: oq.Summary != ""},
		OrderIndex:  orderIdx,
		Metadata:    metaBytes,
		IsPublished: true,
		IsMandatory: true,
		CreatedBy:   userID,
	}
	saved, err := h.courseRepo.CreateContent(c.Request.Context(), content)
	if err != nil {
		logger.Error("SectionOverview.PublishQuiz CreateContent failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Step 2: Create quizzes record.
	timeLimitMinutes := body.TimeLimitMinutes
	pointsPerQuestion := 10.0
	totalPoints := pointsPerQuestion * float64(len(questions))
	quizRecord := &models.Quiz{
		ContentID:              saved.ID,
		Title:                  oq.Title,
		Description:            sql.NullString{String: oq.Summary, Valid: oq.Summary != ""},
		IsPublished:            true,
		CreatedBy:              userID,
		MaxAttempts:            sql.NullInt32{Int32: 999, Valid: true},
		ShuffleQuestions:       true,
		ShuffleAnswers:         true,
		PassingScore:           sql.NullFloat64{Float64: 50.0, Valid: true},
		TotalPoints:            totalPoints,
		AutoGrade:              true,
		ShowResultsImmediately: true,
		ShowCorrectAnswers:     true,
		AllowReview:            true,
		ShowFeedback:           true,
	}
	if timeLimitMinutes > 0 {
		quizRecord.TimeLimitMinutes = sql.NullInt32{Int32: int32(timeLimitMinutes), Valid: true}
	}
	if err := h.quizRepo.CreateQuiz(c.Request.Context(), quizRecord); err != nil {
		logger.Error("SectionOverview.PublishQuiz CreateQuiz failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Step 3: Create quiz_questions and quiz_answer_options.
	for i, q := range questions {
		question := &models.QuizQuestion{
			QuizID:       quizRecord.ID,
			QuestionType: "SINGLE_CHOICE",
			QuestionText: q.Question,
			Explanation:  sql.NullString{String: q.Explanation, Valid: q.Explanation != ""},
			Points:       pointsPerQuestion,
			OrderIndex:   i + 1,
			Settings:     []byte("{}"),
			IsRequired:   true,
			BloomLevel:   sql.NullString{String: q.BloomLevel, Valid: q.BloomLevel != ""},
		}
		if err := h.quizRepo.CreateQuestion(c.Request.Context(), question); err != nil {
			logger.Error(fmt.Sprintf("SectionOverview.PublishQuiz CreateQuestion idx=%d failed", i), err)
			continue
		}
		for j, opt := range q.Options {
			option := &models.QuizAnswerOption{
				QuestionID: question.ID,
				OptionText: opt.Text,
				IsCorrect:  opt.IsCorrect,
				OrderIndex: j + 1,
			}
			if err := h.quizRepo.CreateAnswerOption(c.Request.Context(), option); err != nil {
				logger.Error(fmt.Sprintf("SectionOverview.PublishQuiz CreateAnswerOption q=%d opt=%d failed", i, j), err)
			}
		}
	}

	// Step 4: Mark overview quiz as published.
	if err := h.repo.MarkQuizPublished(c.Request.Context(), quizID, quizRecord.ID); err != nil {
		logger.Error("SectionOverview.MarkQuizPublished failed", err)
	}

	// Invalidate cache so the published quiz appears immediately
	if h.redisCache != nil {
		_ = h.redisCache.Delete(c.Request.Context(), cache.KeySectionContents(body.SectionID))
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"overview_quiz_id":    oq.ID,
		"section_content_id": saved.ID,
		"quiz_id":            quizRecord.ID,
		"questions_created":  len(questions),
		"status":             "published",
	}))
}

// DeleteJob godoc
// @Summary  Delete a section overview job and its draft lesson/quiz
// @Tags     Section-Overview
// @Produce  json
// @Param    jobId path int true "Job ID"
// @Security BearerAuth
// @Router   /section-overview/jobs/{jobId} [delete]
func (h *SectionOverviewHandler) DeleteJob(c *gin.Context) {
	jobID, _ := strconv.ParseInt(c.Param("jobId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	job, err := h.repo.GetJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}
	if userRole != "ADMIN" && job.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot delete this job"))
		return
	}
	if err := h.repo.DeleteJob(c.Request.Context(), jobID); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Job deleted"))
}

// ── Internal callback endpoints (AI service -> LMS) ────────────────────────────

// CallbackStatus receives progress / status updates from the AI service.
func (h *SectionOverviewHandler) CallbackStatus(c *gin.Context) {
	var body dto.SectionOverviewCallbackStatus
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if err := h.repo.UpdateJobStatus(
		c.Request.Context(),
		body.JobID, body.Status, body.Progress, body.Stage, body.Error, body.Logs,
	); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("ok"))
}

// CallbackResults receives the completed lesson and quiz from the AI service.
func (h *SectionOverviewHandler) CallbackResults(c *gin.Context) {
	var body dto.SectionOverviewCallbackResults
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// Look up the job to get created_by.
	job, err := h.repo.GetJob(c.Request.Context(), body.JobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}

	// Mark job as completed.
	if err := h.repo.UpdateJobStatus(c.Request.Context(), body.JobID, "completed", 100, "done", "", ""); err != nil {
		logger.Error(fmt.Sprintf("SectionOverview.CallbackResults UpdateJobStatus failed job=%d", body.JobID), err)
	}

	// Persist lesson.
	if _, err := h.repo.CreateLesson(
		c.Request.Context(),
		body.JobID, body.SectionID, body.CourseID, job.CreatedBy,
		body.Lesson.Title, body.Lesson.Summary, body.Lesson.MarkdownContent,
		body.Lesson.References,
	); err != nil {
		logger.Error(fmt.Sprintf("SectionOverview.CallbackResults CreateLesson failed job=%d", body.JobID), err)
	}

	// Persist quiz.
	if _, err := h.repo.CreateQuiz(
		c.Request.Context(),
		body.JobID, body.SectionID, body.CourseID, job.CreatedBy,
		body.Quiz.Title, body.Quiz.Summary,
		body.Quiz.QuestionCount,
		body.Quiz.Questions,
		body.Quiz.References,
	); err != nil {
		logger.Error(fmt.Sprintf("SectionOverview.CallbackResults CreateQuiz failed job=%d", body.JobID), err)
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("ok"))
}
