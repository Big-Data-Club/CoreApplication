// lms-service/internal/handler/micro_quiz_handler.go
// HTTP handlers for the Micro-Quiz feature.
//
// Public flow (UI):
//   POST   /api/v1/courses/:courseId/micro-quizzes/generate   → trigger
//   GET    /api/v1/courses/:courseId/micro-quizzes/jobs        → list jobs
//   GET    /api/v1/micro-quizzes/jobs/:jobId                  → job + quizzes
//   PUT    /api/v1/micro-quizzes/:quizId                      → save edits
//   POST   /api/v1/micro-quizzes/:quizId/publish              → create QUIZ SectionContent
//   DELETE /api/v1/micro-quizzes/:quizId                      → drop draft
//
// Internal flow (AI service callback):
//   POST /api/v1/internal/micro-quizzes/status   ← progress / status updates
//   POST /api/v1/internal/micro-quizzes/quizzes  ← bulk push of generated quizzes

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

type MicroQuizHandler struct {
	microQuizRepo *repository.MicroQuizRepository
	courseRepo    *repository.CourseRepository
	quizRepo     *repository.QuizRepository
	aiClient     *ai.Client
}

func NewMicroQuizHandler(
	microQuizRepo *repository.MicroQuizRepository,
	courseRepo *repository.CourseRepository,
	quizRepo *repository.QuizRepository,
	aiClient *ai.Client,
) *MicroQuizHandler {
	return &MicroQuizHandler{
		microQuizRepo: microQuizRepo,
		courseRepo:    courseRepo,
		quizRepo:     quizRepo,
		aiClient:     aiClient,
	}
}

// ── Public endpoints ──────────────────────────────────────────────────────────

// GenerateMicroQuizzes triggers quiz generation from a content file or YouTube URL.
func (h *MicroQuizHandler) GenerateMicroQuizzes(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.GenerateMicroQuizzesRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
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
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only the course owner can generate micro-quizzes"))
			return
		}
	}

	// Resolve source: either content_id (file in MinIO) or a YouTube URL.
	job := &models.MicroQuizJob{
		CourseID:  courseID,
		Language:  body.Language,
		Status:    models.MicroQuizJobStatusQueued,
		CreatedBy: userID,
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
				"Content không có file để tạo micro-quiz"))
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

	jobID, err := h.microQuizRepo.CreateJob(c.Request.Context(), job)
	if err != nil {
		logger.Error("CreateJob (micro-quiz) failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Fire-and-forget call to AI service.
	if useYouTube {
		go func() {
			var sourceContentID *int64
			if body.ContentID != 0 {
				sourceContentID = &body.ContentID
			}
			_, err := h.aiClient.GenerateMicroQuizzesFromYouTube(c, ai.GenerateMicroQuizzesFromYouTubeRequest{
				JobID:           jobID,
				CourseID:        courseID,
				SectionID:       body.SectionID,
				SourceContentID: sourceContentID,
				YouTubeURL:      body.YouTubeURL,
				Language:        body.Language,
			})
			if err != nil {
				logger.Error(fmt.Sprintf("AI YT trigger failed for micro-quiz job %d", jobID), err)
				_ = h.microQuizRepo.UpdateJobStatus(c, jobID, models.MicroQuizJobStatusFailed, 0,
					"trigger_failed", 0, err.Error())
			}
		}()
	} else {
		go func() {
			_, err := h.aiClient.GenerateMicroQuizzes(c, ai.GenerateMicroQuizzesRequest{
				JobID:           jobID,
				CourseID:        courseID,
				SectionID:       body.SectionID,
				SourceContentID: nullable(job.SourceContentID),
				SourceFilePath:  job.SourceFilePath.String,
				SourceFileType:  job.SourceFileType.String,
				Language:        body.Language,
			})
			if err != nil {
				logger.Error(fmt.Sprintf("AI trigger failed for micro-quiz job %d", jobID), err)
				_ = h.microQuizRepo.UpdateJobStatus(c, jobID, models.MicroQuizJobStatusFailed, 0,
					"trigger_failed", 0, err.Error())
			}
		}()
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]interface{}{
		"job_id": jobID,
		"status": models.MicroQuizJobStatusQueued,
	}))
}

// ListJobs returns all micro-quiz generation jobs for a course.
func (h *MicroQuizHandler) ListJobs(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	jobs, err := h.microQuizRepo.ListJobsByCourse(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(jobs))
}

// GetJob returns a single job with its generated quizzes.
func (h *MicroQuizHandler) GetJob(c *gin.Context) {
	jobID, _ := strconv.ParseInt(c.Param("jobId"), 10, 64)
	job, err := h.microQuizRepo.GetJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}
	quizzes, err := h.microQuizRepo.ListQuizzesByJob(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"job":     job,
		"quizzes": quizzes,
	}))
}

// UpdateQuiz saves teacher edits on a draft micro quiz (JSON questions).
func (h *MicroQuizHandler) UpdateQuiz(c *gin.Context) {
	quizID, _ := strconv.ParseInt(c.Param("quizId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.UpdateMicroQuizRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	quiz, err := h.microQuizRepo.GetQuiz(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found"))
		return
	}
	if userRole != "ADMIN" && quiz.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot edit this quiz"))
		return
	}

	if err := h.microQuizRepo.UpdateQuizContent(
		c.Request.Context(), quizID,
		body.Title, body.Summary, []byte(body.QuestionsJSON), body.OrderIndex,
	); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Quiz updated"))
}

// PublishQuiz promotes a draft micro quiz into a published QUIZ SectionContent.
// It creates: SectionContent(type=QUIZ) → quizzes record → quiz_questions + quiz_answer_options.
func (h *MicroQuizHandler) PublishQuiz(c *gin.Context) {
	quizID, _ := strconv.ParseInt(c.Param("quizId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	var body dto.PublishMicroQuizRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	mq, err := h.microQuizRepo.GetQuiz(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found"))
		return
	}
	if mq.Status == models.MicroQuizStatusPublished {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("already_published", "Quiz đã được xuất bản"))
		return
	}
	if userRole != "ADMIN" && mq.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot publish this quiz"))
		return
	}

	// Parse questions_json into structured items
	var questions []dto.MicroQuizQuestionItem
	if err := json.Unmarshal(mq.QuestionsJSON, &questions); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_json",
			"questions_json không hợp lệ: "+err.Error()))
		return
	}
	if len(questions) == 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("empty_quiz", "Quiz không có câu hỏi"))
		return
	}

	// Resolve next order index
	orderIdx := body.OrderIndex
	if orderIdx <= 0 {
		existing, _ := h.courseRepo.ListContentBySection(c.Request.Context(), body.SectionID)
		orderIdx = len(existing) + 1
	}

	// Step 1: Create SectionContent (type=QUIZ)
	metadata := map[string]interface{}{
		"micro_quiz_id":       mq.ID,
		"micro_quiz_job":      mq.JobID,
		"ai_generated":        true,
		"questions_count":     len(questions),
	}
	metaBytes, _ := json.Marshal(metadata)

	content := &models.SectionContent{
		SectionID:   body.SectionID,
		Type:        models.ContentTypeQuiz,
		Title:       mq.Title,
		Description: sql.NullString{String: firstNonEmpty(mq.Summary.String, ""), Valid: mq.Summary.Valid},
		OrderIndex:  orderIdx,
		Metadata:    metaBytes,
		IsPublished: true,
		IsMandatory: true,
		CreatedBy:   userID,
	}
	saved, err := h.courseRepo.CreateContent(c.Request.Context(), content)
	if err != nil {
		logger.Error("CreateContent (publish micro-quiz) failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Step 2: Create quizzes record
	pointsPerQuestion := 10.0
	totalPoints := pointsPerQuestion * float64(len(questions))
	quizRecord := &models.Quiz{
		ContentID:              saved.ID,
		Title:                  mq.Title,
		Description:            mq.Summary,
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
		IsPublished:            true,
		CreatedBy:              userID,
	}
	if err := h.quizRepo.CreateQuiz(c.Request.Context(), quizRecord); err != nil {
		logger.Error("CreateQuiz (publish micro-quiz) failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	// Step 3: Create quiz_questions + quiz_answer_options for each question
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
		if mq.NodeID.Valid {
			question.NodeID = sql.NullInt64{Int64: mq.NodeID.Int64, Valid: true}
		}

		if err := h.quizRepo.CreateQuestion(c.Request.Context(), question); err != nil {
			logger.Error(fmt.Sprintf("CreateQuestion (micro-quiz publish) idx=%d failed", i), err)
			continue
		}

		// Insert answer options
		for j, opt := range q.Options {
			option := &models.QuizAnswerOption{
				QuestionID: question.ID,
				OptionText: opt.Text,
				IsCorrect:  opt.IsCorrect,
				OrderIndex: j + 1,
			}
			if err := h.quizRepo.CreateAnswerOption(c.Request.Context(), option); err != nil {
				logger.Error(fmt.Sprintf("CreateAnswerOption (micro-quiz publish) q=%d opt=%d failed", i, j), err)
			}
		}
	}

	// Step 4: Mark micro quiz as published
	if err := h.microQuizRepo.MarkPublished(c.Request.Context(), quizID, saved.ID); err != nil {
		logger.Error("MarkPublished (micro-quiz) failed", err)
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"micro_quiz_id":      mq.ID,
		"section_content_id": saved.ID,
		"quiz_id":            quizRecord.ID,
		"questions_created":  len(questions),
		"status":             "published",
	}))
}

// DeleteQuiz deletes a draft micro quiz.
func (h *MicroQuizHandler) DeleteQuiz(c *gin.Context) {
	quizID, _ := strconv.ParseInt(c.Param("quizId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	quiz, err := h.microQuizRepo.GetQuiz(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found"))
		return
	}
	if userRole != "ADMIN" && quiz.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Cannot delete this quiz"))
		return
	}
	if err := h.microQuizRepo.DeleteQuiz(c.Request.Context(), quizID); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Draft quiz deleted"))
}

// ── Internal callbacks (AI service → LMS) ────────────────────────────────────

// CallbackStatus receives job progress updates from the AI service.
func (h *MicroQuizHandler) CallbackStatus(c *gin.Context) {
	var body dto.MicroQuizStatusCallback
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if err := h.microQuizRepo.UpdateJobStatus(
		c.Request.Context(), body.JobID, body.Status,
		body.Progress, body.Stage, body.QuizzesCount, body.Error,
	); err != nil {
		logger.Error(fmt.Sprintf("UpdateJobStatus (micro-quiz) failed job=%d", body.JobID), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("ok"))
}

// CallbackQuizzes receives AI-generated quizzes and persists them.
func (h *MicroQuizHandler) CallbackQuizzes(c *gin.Context) {
	var body dto.MicroQuizzesCallback
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	job, err := h.microQuizRepo.GetJob(c.Request.Context(), body.JobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
		return
	}

	for i, item := range body.Quizzes {
		questionsBytes := []byte(item.QuestionsJSON)
		if len(questionsBytes) == 0 {
			questionsBytes = []byte("[]")
		}
		quiz := &models.MicroQuiz{
			JobID:     body.JobID,
			CourseID:  body.CourseID,
			SectionID: job.SectionID,
			Title:     item.Title,
			Summary:   sql.NullString{String: item.Summary, Valid: item.Summary != ""},
			QuestionsJSON:  questionsBytes,
			QuestionsCount: item.QuestionsCount,
			OrderIndex:     item.OrderIndex,
			Language:       body.Language,
			CreatedBy:      job.CreatedBy,
		}
		if body.SourceContentID != nil {
			quiz.SourceContentID = sql.NullInt64{Int64: *body.SourceContentID, Valid: true}
		}
		if item.NodeID != nil {
			quiz.NodeID = sql.NullInt64{Int64: *item.NodeID, Valid: true}
		}

		if _, err := h.microQuizRepo.CreateQuiz(c.Request.Context(), quiz); err != nil {
			logger.Error(fmt.Sprintf("CreateQuiz (callback) failed for job %d (idx %d)", body.JobID, i), err)
		}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{
		"job_id":  body.JobID,
		"created": len(body.Quizzes),
	}))
}
