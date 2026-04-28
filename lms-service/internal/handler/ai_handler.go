// lms-service/internal/handler/ai_handler.go
// HTTP handlers for AI features exposed to the Next.js frontend.
// These proxy/orchestrate calls between the student, LMS DB, and ai-service.
package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/cache"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// AIHandler handles all AI-related HTTP endpoints.
type AIHandler struct {
	aiClient   *ai.Client
	courseRepo *repository.CourseRepository
	quizRepo   *repository.QuizRepository
	redisCache *cache.RedisCache
}

// NewAIHandler creates a new AIHandler.
func NewAIHandler(aiClient *ai.Client, courseRepo *repository.CourseRepository, quizRepo *repository.QuizRepository, redisCache *cache.RedisCache) *AIHandler {
	return &AIHandler{aiClient: aiClient, courseRepo: courseRepo, quizRepo: quizRepo, redisCache: redisCache}
}

// GetJobStatus godoc
// @Summary Get AI Job Status
// @Tags AI - Core
// @Produce json
// @Param jobId path string true "Job ID"
// @Security BearerAuth
// @Router /ai/jobs/{jobId}/status [get]
func (h *AIHandler) GetJobStatus() gin.HandlerFunc {
	return func(c *gin.Context) {
		jobID := c.Param("jobId")
		redisKey := "ai_job:" + jobID

		data, err := h.redisCache.Get(c.Request.Context(), redisKey)
		if err != nil || data == "" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found or expired"))
			return
		}

		var statusEvent kafka.AIJobStatusEvent
		if err := json.Unmarshal([]byte(data), &statusEvent); err != nil {
			// If it's the pending state format
			var pendingState map[string]interface{}
			_ = json.Unmarshal([]byte(data), &pendingState)
			c.JSON(http.StatusOK, dto.NewDataResponse(pendingState))
			return
		}

		c.JSON(http.StatusOK, dto.NewDataResponse(statusEvent))
	}
}

// ── Phase 1: Error Diagnosis ──────────────────────────────────────────────────

// DiagnoseWrongAnswer godoc
// @Summary      AI Error Diagnosis
// @Description  Analyze why a student answered incorrectly, with deep link to source material.
//
//	Called automatically when student submits a wrong answer.
//
// @Tags         AI - Phase 1
// @Produce      json
// @Param        attemptId path  int true "Quiz Attempt ID"
// @Param        questionId path int true "Question ID"
// @Security     BearerAuth
// @Success      200 {object} ai.DiagnoseResponse
// @Failure      500 {object} dto.ErrorResponse
// @Router       /attempts/{attemptId}/questions/{questionId}/diagnose [post]
func (h *AIHandler) DiagnoseWrongAnswer(c *gin.Context) {
	attemptID, _ := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	questionID, _ := strconv.ParseInt(c.Param("questionId"), 10, 64)
	studentID := c.MustGet("user_id").(int64)

	var body struct {
		WrongAnswer string `json:"wrong_answer" binding:"required"`
		CourseID    int64  `json:"course_id"    binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// Enrichment: load question + options from LMS DB so AI doesn't need to
	qWithOpts, err := h.quizRepo.GetQuestionWithOptions(c.Request.Context(), questionID)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to load question %d for diagnosis enrichment", questionID), err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("question_not_found", "Could not load question data"))
		return
	}

	// Build correct answer string and answer options list
	correctAnswer := ""
	answerOptions := make([]map[string]interface{}, 0, len(qWithOpts.AnswerOptions))
	for _, opt := range qWithOpts.AnswerOptions {
		optMap := map[string]interface{}{
			"option_text": opt.OptionText,
			"is_correct":  opt.IsCorrect,
		}
		answerOptions = append(answerOptions, optMap)
		if opt.IsCorrect {
			if correctAnswer != "" {
				correctAnswer += " | "
			}
			correctAnswer += opt.OptionText
		}
	}

	// Convert sql.NullInt64 to *int64 for AI request
	var nodeIDPtr *int64
	if qWithOpts.NodeID.Valid {
		nodeIDPtr = &qWithOpts.NodeID.Int64
	}

	aiReq := ai.DiagnoseRequest{
		StudentID:     studentID,
		AttemptID:     attemptID,
		QuestionID:    questionID,
		WrongAnswer:   body.WrongAnswer,
		CourseID:      body.CourseID,
		QuestionText:  qWithOpts.QuestionText,
		QuestionType:  qWithOpts.QuestionType,
		Explanation:   qWithOpts.Explanation.String,
		CorrectAnswer: correctAnswer,
		AnswerOptions: answerOptions,
		NodeID:        nodeIDPtr,
	}

	jobID := uuid.New().String()
	
	payload, _ := json.Marshal(aiReq)
	event := kafka.AICommandEvent{
		JobID:       jobID,
		CommandType: "DIAGNOSE_ERROR",
		CourseID:    body.CourseID,
		Payload:     json.RawMessage(payload),
		CreatedAt:   time.Now(),
	}

	redisPayload := map[string]interface{}{
		"job_id": jobID,
		"status": "processing",
	}
	redisData, _ := json.Marshal(redisPayload)
	err = h.redisCache.Set(c.Request.Context(), "ai_job:"+jobID, redisData, 24*time.Hour)
	if err != nil {
		logger.Error("Failed to tracking AI diagnosis job in Redis", err)
	}

	err = kafka.PublishEvent(c.Request.Context(), "lms.ai.command", []byte(jobID), event)
	if err != nil {
		logger.Error("AI diagnosis command publish failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("kafka_error", "Failed to queue diagnosis"))
		return
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(redisPayload))

	// The enrichment will now happen in AI service or on frontend polling.
	// For this async transition, we don't return the immediate results.
}

// GetClassHeatmap godoc
// @Summary      Class Knowledge Heatmap
// @Description  Returns knowledge nodes sorted by class-wide wrong rate. Teacher/Admin only.
// @Tags         AI - Phase 1
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Success      200 {array} ai.HeatmapNode
// @Router       /courses/{courseId}/ai/heatmap [get]
func (h *AIHandler) GetClassHeatmap(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	data, err := h.aiClient.GetClassHeatmap(c.Request.Context(), courseID)
	if err != nil {
		logger.Error("Heatmap failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

// GetStudentHeatmap godoc
// @Summary      Student Knowledge Map
// @Description  Returns per-student knowledge mastery across all nodes in a course.
// @Tags         AI - Phase 1
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Success      200 {array} map[string]interface{}
// @Router       /courses/{courseId}/ai/my-heatmap [get]
func (h *AIHandler) GetStudentHeatmap(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	studentID := c.MustGet("user_id").(int64)

	data, err := h.aiClient.GetStudentHeatmap(c.Request.Context(), studentID, courseID)
	if err != nil {
		logger.Error("Student heatmap failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

// ── Knowledge Nodes ────────────────────────────────────────────────────────────

// CreateKnowledgeNode godoc
// @Summary      Create Knowledge Node
// @Description  Create an atomic knowledge unit for a course (Teacher/Admin only).
// @Tags         AI - Knowledge Graph
// @Accept       json
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Success      201 {object} map[string]interface{}
// @Router       /courses/{courseId}/ai/nodes [post]
func (h *AIHandler) CreateKnowledgeNode(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	var body struct {
		Name        string `json:"name"        binding:"required"`
		NameVI      string `json:"name_vi"`
		NameEN      string `json:"name_en"`
		Description string `json:"description"`
		ParentID    *int64 `json:"parent_id"`
		OrderIndex  int    `json:"order_index"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.aiClient.CreateKnowledgeNode(c.Request.Context(), ai.CreateNodeRequest{
		CourseID:    courseID,
		Name:        body.Name,
		NameVI:      body.NameVI,
		NameEN:      body.NameEN,
		Description: body.Description,
		ParentID:    body.ParentID,
		OrderIndex:  body.OrderIndex,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}

// ListKnowledgeNodes godoc
// @Summary      List Knowledge Nodes for a Course
// @Tags         AI - Knowledge Graph
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Success      200 {array} map[string]interface{}
// @Router       /courses/{courseId}/ai/nodes [get]
func (h *AIHandler) ListKnowledgeNodes(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	nodes, err := h.aiClient.ListKnowledgeNodes(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(nodes))
}

// ── Phase 2: Quiz Generation ───────────────────────────────────────────────────

// GenerateQuiz godoc
// @Summary      AI Auto Quiz Generator (Bloom's Taxonomy)
// @Description  Generate quiz questions for a knowledge node using Bloom's Taxonomy.
//
//	Questions are saved as DRAFT — require instructor review before publish.
//
// @Tags         AI - Phase 2
// @Accept       json
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Success      200 {object} ai.GenerateQuizResponse
// @Router       /courses/{courseId}/ai/generate-quiz [post]
func (h *AIHandler) GenerateQuiz(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	createdBy := c.MustGet("user_id").(int64)

	var body struct {
		NodeID            int64    `json:"node_id"             binding:"required"`
		BloomLevels       []string `json:"bloom_levels"`
		Language          string   `json:"language"`
		QuestionsPerLevel int      `json:"questions_per_level"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	if body.Language == "" {
		body.Language = "vi"
	}
	if body.QuestionsPerLevel == 0 {
		body.QuestionsPerLevel = 1
	}

	jobID := uuid.New().String()
	
	reqPayload := ai.GenerateQuizRequest{
		NodeID:            body.NodeID,
		CourseID:          courseID,
		CreatedBy:         createdBy,
		BloomLevels:       body.BloomLevels,
		Language:          body.Language,
		QuestionsPerLevel: body.QuestionsPerLevel,
	}
	
	payloadBytes, _ := json.Marshal(reqPayload)
	
	event := kafka.AICommandEvent{
		JobID:       jobID,
		CommandType: "GENERATE_QUIZ",
		CourseID:    courseID,
		Payload:     json.RawMessage(payloadBytes),
		CreatedAt:   time.Now(),
	}

	redisPayload := map[string]interface{}{
		"job_id": jobID,
		"status": "processing",
	}
	redisData, _ := json.Marshal(redisPayload)
	_ = h.redisCache.Set(c.Request.Context(), "ai_job:"+jobID, redisData, 24*time.Hour)

	err := kafka.PublishEvent(c.Request.Context(), "lms.ai.command", []byte(jobID), event)
	if err != nil {
		logger.Error("Quiz generation publish failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("kafka_error", "Failed to queue quiz generation"))
		return
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(redisPayload))
}

// ListDraftQuestions godoc
// @Summary      List AI-Generated Draft Questions
// @Description  Returns all DRAFT AI questions awaiting instructor review.
// @Tags         AI - Phase 2
// @Produce      json
// @Param        courseId path int    true  "Course ID"
// @Param        node_id  query int   false "Filter by node ID"
// @Security     BearerAuth
// @Success      200 {array} map[string]interface{}
// @Router       /courses/{courseId}/ai/drafts [get]
func (h *AIHandler) ListDraftQuestions(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	var nodeID *int64
	if nodeIDStr := c.Query("node_id"); nodeIDStr != "" {
		if n, err := strconv.ParseInt(nodeIDStr, 10, 64); err == nil {
			nodeID = &n
		}
	}

	drafts, err := h.aiClient.GetDraftQuestions(c.Request.Context(), courseID, nodeID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(drafts))
}

// ApproveQuestion godoc
// @Summary      Approve AI-Generated Question
// @Description  Instructor approves a DRAFT question → published to a quiz.
// @Tags         AI - Phase 2
// @Accept       json
// @Produce      json
// @Param        genId path int true "Generation ID"
// @Security     BearerAuth
// @Router       /ai/quiz-drafts/{genId}/approve [post]
func (h *AIHandler) ApproveQuestion(c *gin.Context) {
	genID, _ := strconv.ParseInt(c.Param("genId"), 10, 64)
	reviewerID := c.MustGet("user_id").(int64)

	var body struct {
		QuizID     int64  `json:"quiz_id"     binding:"required"`
		ReviewNote string `json:"review_note"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// 1) Ask AI to approve — returns question data instead of writing to LMS DB
	approved, err := h.aiClient.ApproveQuestion(c.Request.Context(), genID, ai.ApproveQuestionRequest{
		ReviewerID: reviewerID,
		QuizID:     body.QuizID,
		ReviewNote: body.ReviewNote,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	ctx := c.Request.Context()

	// 2) LMS inserts the question into its own quiz_questions table
	question := &models.QuizQuestion{
		QuizID:       body.QuizID,
		QuestionType: approved.QuestionType,
		QuestionText: approved.QuestionText,
	}
	if approved.Explanation != "" {
		question.Explanation.String = approved.Explanation
		question.Explanation.Valid = true
	}
	question.Points = 10.0
	question.IsRequired = true
	if approved.NodeID != nil {
		question.NodeID.Int64 = *approved.NodeID
		question.NodeID.Valid = true
	}
	if approved.BloomLevel != "" {
		question.BloomLevel.String = approved.BloomLevel
		question.BloomLevel.Valid = true
	}
	if approved.SourceChunkID != nil {
		question.ReferenceChunkID.Int64 = *approved.SourceChunkID
		question.ReferenceChunkID.Valid = true
	}

	// Get next order_index
	existingQs, _ := h.quizRepo.ListQuestions(ctx, body.QuizID)
	question.OrderIndex = len(existingQs) + 1

	if err := h.quizRepo.CreateQuestion(ctx, question); err != nil {
		logger.Error("Failed to create quiz question from AI approval", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", "Failed to insert quiz question"))
		return
	}

	// 3) Insert answer options
	for i, optMap := range approved.AnswerOptions {
		optText, _ := optMap["text"].(string)
		if optText == "" {
			optText, _ = optMap["option_text"].(string)
		}
		isCorrect, _ := optMap["is_correct"].(bool)

		opt := &models.QuizAnswerOption{
			QuestionID: question.ID,
			OptionText: optText,
			IsCorrect:  isCorrect,
			OrderIndex: i,
		}
		if err := h.quizRepo.CreateAnswerOption(ctx, opt); err != nil {
			logger.Error(fmt.Sprintf("Failed to create answer option for question %d", question.ID), err)
		}
	}

	// 4) Notify AI that we successfully created the question (fire-and-forget)
	go func() {
		_ = h.aiClient.PublishQuestion(context.Background(), genID, question.ID)
	}()

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]int64{"quiz_question_id": question.ID}))
}

// RejectQuestion godoc
// @Summary      Reject AI-Generated Question
// @Tags         AI - Phase 2
// @Accept       json
// @Produce      json
// @Param        genId path int true "Generation ID"
// @Security     BearerAuth
// @Router       /ai/quiz-drafts/{genId}/reject [post]
func (h *AIHandler) RejectQuestion(c *gin.Context) {
	genID, _ := strconv.ParseInt(c.Param("genId"), 10, 64)
	reviewerID := c.MustGet("user_id").(int64)

	var body struct {
		ReviewNote string `json:"review_note" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	err := h.aiClient.RejectQuestion(c.Request.Context(), genID, ai.RejectQuestionRequest{
		ReviewerID: reviewerID,
		ReviewNote: body.ReviewNote,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Question rejected"))
}

// ── Phase 2: Spaced Repetition ─────────────────────────────────────────────────

// GetDueReviews godoc
// @Summary      Get Due Review Questions (Spaced Repetition)
// @Description  Returns questions due for review today based on SM-2 algorithm.
//
//	Used for the 5-minute warm-up session on student login.
//
// @Tags         AI - Phase 2
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/reviews/due [get]
func (h *AIHandler) GetDueReviews(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	studentID := c.MustGet("user_id").(int64)

	reviews, err := h.aiClient.GetDueReviews(c.Request.Context(), studentID, courseID, 20)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	// Enrich question_text from LMS DB (AI no longer queries LMS)
	if len(reviews) > 0 {
		questionIDs := make([]int64, 0, len(reviews))
		for _, r := range reviews {
			if qID, ok := r["question_id"].(float64); ok {
				questionIDs = append(questionIDs, int64(qID))
			}
		}
		if len(questionIDs) > 0 {
			questions, err := h.quizRepo.GetQuestionsByIDs(c.Request.Context(), questionIDs)
			if err == nil {
				qMap := make(map[int64]models.QuizQuestion, len(questions))
				for _, q := range questions {
					qMap[q.ID] = q
				}
				for i, r := range reviews {
					if qID, ok := r["question_id"].(float64); ok {
						if q, found := qMap[int64(qID)]; found {
							reviews[i]["question_text"] = q.QuestionText
							reviews[i]["question_type"] = q.QuestionType
						}
					}
				}
			}
		}
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(reviews))
}

// RecordReviewResponse godoc
// @Summary      Record Spaced Repetition Response
// @Description  Record student quality rating (0-5) for a review question. Updates SM-2 schedule.
// @Tags         AI - Phase 2
// @Accept       json
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/reviews/record [post]
func (h *AIHandler) RecordReviewResponse(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	studentID := c.MustGet("user_id").(int64)

	var body struct {
		QuestionID int64  `json:"question_id" binding:"required"`
		NodeID     *int64 `json:"node_id"`
		Quality    int    `json:"quality" binding:"required,min=0,max=5"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.aiClient.RecordReviewResponse(c.Request.Context(), ai.RecordReviewRequest{
		StudentID:  studentID,
		QuestionID: body.QuestionID,
		CourseID:   courseID,
		NodeID:     body.NodeID,
		Quality:    body.Quality,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// GetReviewStats godoc
// @Summary      Spaced Repetition Stats
// @Tags         AI - Phase 2
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/reviews/stats [get]
func (h *AIHandler) GetReviewStats(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	studentID := c.MustGet("user_id").(int64)

	stats, err := h.aiClient.GetReviewStats(c.Request.Context(), studentID, courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(stats))
}

func (h *AIHandler) TriggerDocumentProcess(c *gin.Context) {
	contentID, _ := strconv.ParseInt(c.Param("contentId"), 10, 64)

	var body struct {
		CourseID    int64  `json:"course_id" binding:"required"`
		NodeID      *int64 `json:"node_id"`
		FileURL     string `json:"file_url"`
		ContentType string `json:"content_type"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}
	if body.ContentType == "" {
		body.ContentType = "application/pdf"
	}

	result, err := h.aiClient.ProcessDocument(c.Request.Context(), ai.ProcessDocumentRequest{
		ContentID:   contentID,
		CourseID:    body.CourseID,
		NodeID:      body.NodeID,
		FileURL:     body.FileURL,
		ContentType: body.ContentType,
	})
	if err != nil {
		logger.Error("Document processing trigger failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}
	c.JSON(http.StatusAccepted, dto.NewDataResponse(result))
}

// TriggerContentAutoIndex godoc
// @Summary      Trigger auto-index for a content document
// @Description  Giáo viên click nút "Index" → AI tự động tạo knowledge nodes.
//
//	Trả về ngay; frontend poll /content/:id/ai-index-status.
//
// @Tags         AI - Auto Index
// @Accept       json
// @Produce      json
// @Param        contentId path int true "Content ID"
// @Security     BearerAuth
// @Success      202 {object} map[string]interface{}
// @Router       /content/{contentId}/ai-index [post]
func (h *AIHandler) TriggerContentAutoIndex(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	// Lấy content để verify quyền và lấy file_path
	content, err := h.courseRepo.GetContentByID(c.Request.Context(), contentID)
	if err != nil {
		logger.Error(fmt.Sprintf("Auto-index: Content %d not found", contentID), err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Content not found"))
		return
	}

	// Log content details for debugging
	logger.Info(fmt.Sprintf("Auto-index debug: ContentID=%d, Type=%s, FilePath.Valid=%v, FilePath.String='%s'",
		contentID, content.Type, content.FilePath.Valid, content.FilePath.String))

	// Chỉ TEACHER hoặc ADMIN mới được index
	if userRole != "ADMIN" {
		// Verify ownership qua section → course
		section, sErr := h.courseRepo.GetSectionByID(c.Request.Context(), content.SectionID)
		if sErr != nil {
			logger.Error(fmt.Sprintf("Auto-index: Section %d fetch failed", content.SectionID), sErr)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", sErr.Error()))
			return
		}
		course, cErr := h.courseRepo.GetByID(c.Request.Context(), section.CourseID)
		if cErr != nil {
			logger.Error(fmt.Sprintf("Auto-index: Course %d fetch failed", section.CourseID), cErr)
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", cErr.Error()))
			return
		}
		if course.CreatedBy != userID {
			logger.Warn(fmt.Sprintf("Auto-index: User %d not authorized for course %d", userID, course.ID))
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only course owner can index documents"))
			return
		}
	}

	// Kiểm tra content có file hoặc text không
	finalFilePath := ""
	finalFileType := "application/pdf"
	finalTextContent := ""

	// Xử lý TEXT content: lấy từ metadata.content (nơi frontend lưu text markdown)
	if content.Type == "TEXT" {
		// Priority 1: Check metadata.content (where frontend saves TEXT markdown)
		if len(content.Metadata) > 0 {
			var meta map[string]interface{}
			if err := json.Unmarshal(content.Metadata, &meta); err == nil {
				if val, ok := meta["content"].(string); ok && val != "" {
					finalTextContent = val
					logger.Info(fmt.Sprintf("Auto-index TEXT: Content %d, text length: %d chars from metadata.content",
						contentID, len(finalTextContent)))
				}
			}
		}

		// Priority 2: Fallback to Description field
		if finalTextContent == "" && content.Description.Valid && content.Description.String != "" {
			finalTextContent = content.Description.String
			logger.Info(fmt.Sprintf("Auto-index TEXT: Content %d, text length: %d chars from Description",
				contentID, len(finalTextContent)))
		}

		if finalTextContent == "" {
			logger.Warn(fmt.Sprintf("Auto-index TEXT fail: Content %d has no text in metadata.content or Description", contentID))
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("no_content", "TEXT content has no text to index"))
			return
		}
	} else {
		// Xử lý FILE content: lấy từ FilePath
		if content.FilePath.Valid && content.FilePath.String != "" {
			finalFilePath = content.FilePath.String
			if content.FileType.Valid {
				finalFileType = content.FileType.String
			}
		} else if len(content.Metadata) > 0 {
			// Fallback: Thử lấy từ metadata JSON
			var meta map[string]interface{}
			if err := json.Unmarshal(content.Metadata, &meta); err == nil {
				if path, ok := meta["file_path"].(string); ok && path != "" {
					finalFilePath = path
					logger.Info(fmt.Sprintf("Auto-index fallback: Using file_path from metadata for content %d: %s", contentID, path))
				} else if vUrl, ok := meta["video_url"].(string); ok && vUrl != "" {
					finalFilePath = vUrl
					logger.Info(fmt.Sprintf("Auto-index fallback: Using video_url from metadata for content %d: %s", contentID, vUrl))
				}
				
				if ftype, ok := meta["file_type"].(string); ok && ftype != "" {
					finalFileType = ftype
				} else if vType, ok := meta["video_type"].(string); ok && vType == "youtube" {
					finalFileType = "video/youtube"
				}
			}
		}

		if finalFilePath == "" {
			logger.Warn(fmt.Sprintf("Auto-index fail: Content %d (Type: %s) has no file_path in column or metadata",
				contentID, content.Type))
			c.JSON(http.StatusBadRequest, dto.NewErrorResponse("no_file", "Content has no file to index"))
			return
		}
	}

	// Xác định courseID từ section
	section, _ := h.courseRepo.GetSectionByID(c.Request.Context(), content.SectionID)
	course, _ := h.courseRepo.GetByID(c.Request.Context(), section.CourseID)

	// Phát sự kiện lên Kafka
	eventID := fmt.Sprintf("evt-autoindex-%d", contentID)
	eventPayload := kafka.ProcessDocumentEvent{
		EventID:        eventID,
		ContentID:      contentID,
		CourseID:       course.ID,
		CourseName:     course.Title,
		InstructorName: fmt.Sprintf("%d", course.CreatedBy),
		FileURL:        finalFilePath,
		ContentType:    finalFileType,
		Title:          content.Title,
		CreatedAt:      time.Now(),
	}

	if content.Type == "TEXT" {
		eventPayload.ContentType = "text/markdown"
		eventPayload.TextContent = finalTextContent
	}

	key := []byte(fmt.Sprintf("%d", contentID))
	err = kafka.PublishEvent(c.Request.Context(), "lms.document.uploaded", key, eventPayload)

	if err != nil {
		logger.Error("Kafka publish failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("kafka_unavailable", err.Error()))
		return
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]interface{}{
		"job_id":     eventID,
		"content_id": contentID,
		"status":     "queued",
	}))
}

// GetContentAutoIndexStatus godoc
// @Summary      Get auto-index status for a content item
// @Tags         AI - Auto Index
// @Produce      json
// @Param        contentId path int true "Content ID"
// @Security     BearerAuth
// @Router       /content/{contentId}/ai-index-status [get]
func (h *AIHandler) GetContentAutoIndexStatus(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	status, err := h.aiClient.GetAutoIndexStatus(c.Request.Context(), contentID)
	if err != nil {
		// Fallback: đọc thẳng từ DB nếu AI service không available
		dbStatus, _, dbErr := h.courseRepo.GetContentAIIndexStatus(c.Request.Context(), contentID)
		if dbErr != nil {
			c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", dbErr.Error()))
			return
		}
		c.JSON(http.StatusOK, dto.NewDataResponse(map[string]string{
			"status": dbStatus,
		}))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(status))
}

// BatchGetContentAutoIndexStatus godoc
// @Summary      Batch get auto-index status for multiple content items
// @Description  Returns status for all requested content IDs in one round-trip.
//
//	Replaces N individual /ai-index-status calls to prevent rate limiting.
//
// @Tags         AI - Auto Index
// @Accept       json
// @Produce      json
// @Security     BearerAuth
// @Success      200 {object} map[string]interface{}
// @Router       /content/batch-ai-index-status [post]
func (h *AIHandler) BatchGetContentAutoIndexStatus(c *gin.Context) {
	var body struct {
		ContentIDs []int64 `json:"content_ids" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// Cap at 100 to prevent abuse
	ids := body.ContentIDs
	if len(ids) > 100 {
		ids = ids[:100]
	}

	result, err := h.aiClient.BatchGetAutoIndexStatus(c.Request.Context(), ids)
	if err != nil {
		// Fallback: return basic status from LMS DB for each content
		logger.Warn(fmt.Sprintf("Batch status from AI failed, falling back to DB: %s", err.Error()))
		fallback := make(map[string]interface{})
		for _, id := range ids {
			dbStatus, _, dbErr := h.courseRepo.GetContentAIIndexStatus(c.Request.Context(), id)
			if dbErr != nil {
				dbStatus = "unindexed"
			}
			fallback[fmt.Sprintf("%d", id)] = map[string]interface{}{
				"content_id": id,
				"status":     dbStatus,
			}
		}
		c.JSON(http.StatusOK, dto.NewDataResponse(fallback))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// GetCourseKnowledgeGraph godoc
// @Summary      Get knowledge graph for a course
// @Tags         AI - Auto Index
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/knowledge-graph [get]
func (h *AIHandler) GetCourseKnowledgeGraph(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	graph, err := h.aiClient.GetKnowledgeGraph(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(graph))
}

// GetGlobalKnowledgeGraph godoc
// @Summary      Get global knowledge graph
// @Description  Returns the entire knowledge graph across all courses.
// @Tags         AI - Knowledge Graph
// @Produce      json
// @Param        min_strength query float64 false "Minimum edge strength (0.0 to 1.0)"
// @Param        limit        query int     false "Limit number of nodes"
// @Security     BearerAuth
// @Router       /ai/knowledge-graph/global [get]
func (h *AIHandler) GetGlobalKnowledgeGraph(c *gin.Context) {
	minStrength := 0.5
	if ms := c.Query("min_strength"); ms != "" {
		if val, err := strconv.ParseFloat(ms, 64); err == nil {
			minStrength = val
		}
	}

	limit := 2000
	if l := c.Query("limit"); l != "" {
		if val, err := strconv.Atoi(l); err == nil {
			limit = val
		}
	}

	graph, err := h.aiClient.GetGlobalKnowledgeGraph(c.Request.Context(), minStrength, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(graph))
}

// TriggerGlobalLinking godoc
// @Summary      Trigger Global Knowledge Linking
// @Description  Triggers a background task to find and create cross-course knowledge relationships.
// @Tags         AI - Knowledge Graph
// @Produce      json
// @Security     BearerAuth
// @Router       /ai/knowledge-graph/link-global [post]
func (h *AIHandler) TriggerGlobalLinking(c *gin.Context) {
	// Only ADMIN can trigger global logic
	userRole := c.GetString("user_role")
	if userRole != "ADMIN" {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only admins can trigger global linking"))
		return
	}

	result, err := h.aiClient.LinkGlobalGraph(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(result))
}

func (h *AIHandler) GetNodeChunks(c *gin.Context) {
    nodeID, _ := strconv.ParseInt(c.Param("nodeId"), 10, 64)
    limit := 50
    chunks, err := h.aiClient.GetNodeChunks(c.Request.Context(), nodeID, limit)
    if err != nil {
        c.JSON(500, dto.NewErrorResponse("ai_error", err.Error()))
        return
    }
    c.JSON(200, dto.NewDataResponse(chunks))

}

// PreviewGraphConsolidation godoc
// @Summary      Preview "Compact Graph" merges
// @Description  Returns a dry-run plan describing which nodes would be merged.
// @Tags         AI - Knowledge Graph
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/consolidate-graph/preview [get]
func (h *AIHandler) PreviewGraphConsolidation(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err := h.assertCourseOwner(c, courseID); err != nil {
		return
	}

	plan, err := h.aiClient.PreviewGraphConsolidation(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(plan))
}

// ConsolidateGraph godoc
// @Summary      Trigger "Compact Graph" merge
// @Description  Queues a Kafka job that merges duplicate / micro knowledge nodes.
// @Tags         AI - Knowledge Graph
// @Produce      json
// @Param        courseId path int true "Course ID"
// @Security     BearerAuth
// @Router       /courses/{courseId}/ai/consolidate-graph [post]
func (h *AIHandler) ConsolidateGraph(c *gin.Context) {
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	if err := h.assertCourseOwner(c, courseID); err != nil {
		return
	}

	resp, err := h.aiClient.TriggerGraphConsolidation(c.Request.Context(), courseID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	jobID := fmt.Sprintf("consolidate-%d", courseID)
	if v, ok := resp["job_id"].(string); ok && v != "" {
		jobID = v
	}

	// Seed Redis with a "pending" entry so the existing job-status poller works.
	pending := map[string]interface{}{
		"job_id": jobID,
		"status": "pending",
	}
	if data, err := json.Marshal(pending); err == nil {
		_ = h.redisCache.Set(c.Request.Context(), "ai_job:"+jobID, data, 24*time.Hour)
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]interface{}{
		"job_id":  jobID,
		"status":  "queued",
		"message": "Graph consolidation queued",
	}))
}

// assertCourseOwner allows ADMINs and the course's creator. Writes the
// error response itself; callers should bail out on non-nil error.
func (h *AIHandler) assertCourseOwner(c *gin.Context, courseID int64) error {
	role := c.GetString("user_role")
	if role == "ADMIN" {
		return nil
	}
	userID := c.MustGet("user_id").(int64)
	course, err := h.courseRepo.GetByID(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
		return err
	}
	if course.CreatedBy != userID {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only course owner can run this action"))
		return fmt.Errorf("forbidden")
	}
	return nil
}

func (h *AIHandler) DeleteKnowledgeNode(c *gin.Context) {
	nodeID, _ := strconv.ParseInt(c.Param("nodeId"), 10, 64)
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	userID := c.MustGet("user_id").(int64)
	userRole := c.GetString("user_role")

	// 1. Verify Ownership
	if userRole != "ADMIN" {
		course, err := h.courseRepo.GetByID(c.Request.Context(), courseID)
		if err != nil {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if course.CreatedBy != userID {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only course owner can delete nodes"))
			return
		}
	}

	// 2. Call AI Client (Cascaded Deletion)
	if err := h.aiClient.DeleteKnowledgeNode(c.Request.Context(), nodeID); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("ai_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Node deleted successfully"))
}