package handler

import (
	"fmt"
	"net/http"
	"path/filepath"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
	"example/hello/pkg/storage"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type QuizHandler struct {
	quizService *service.QuizService
	storage     storage.Storage
}

func NewQuizHandler(quizService *service.QuizService, storage storage.Storage) *QuizHandler {
	return &QuizHandler{
		quizService: quizService,
		storage:     storage,
	}
}

// ============================================
// QUIZ MANAGEMENT (Teacher)
// ============================================

// CreateQuiz godoc
// @Summary Create a quiz
// @Description Create a new quiz for a course content (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param request body dto.CreateQuizRequest true "Quiz data"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.QuizResponse} "Quiz created successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or validation error"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - teacher/admin only"
// @Router /quizzes [post]
func (h *QuizHandler) CreateQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	var req dto.CreateQuizRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	quiz, err := h.quizService.CreateQuiz(c.Request.Context(), &req, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to create quiz", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("creation_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(quiz))
}

// GetQuiz godoc
// @Summary Get quiz details
// @Description Get detailed information about a quiz
// @Tags Quiz
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizResponse} "Quiz details"
// @Failure 400 {object} dto.ErrorResponse "Invalid quiz ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 404 {object} dto.ErrorResponse "Quiz not found"
// @Router /quizzes/{quizId} [get]
func (h *QuizHandler) GetQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	quiz, err := h.quizService.GetQuiz(c.Request.Context(), quizID, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to get quiz", err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(quiz))
}

// UpdateQuiz godoc
// @Summary Update quiz
// @Description Update quiz details (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Param request body dto.UpdateQuizRequest true "Updated quiz data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizResponse} "Quiz updated successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or validation error"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Router /quizzes/{quizId} [put]
func (h *QuizHandler) UpdateQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	var req dto.UpdateQuizRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	quiz, err := h.quizService.UpdateQuiz(c.Request.Context(), quizID, &req, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to update quiz", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(quiz))
}

// DeleteQuiz godoc
// @Summary Delete quiz
// @Description Delete a quiz (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Quiz deleted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid quiz ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Router /quizzes/{quizId} [delete]
func (h *QuizHandler) DeleteQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	if err := h.quizService.DeleteQuiz(c.Request.Context(), quizID, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to delete quiz", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("deletion_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Quiz deleted successfully"))
}

// ============================================
// QUESTION MANAGEMENT (Teacher)
// ============================================

// CreateQuestion godoc
// @Summary Create a question
// @Description Create a new question for a quiz (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Param request body dto.CreateQuestionRequest true "Question data"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.QuestionResponse} "Question created successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or validation error"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Router /quizzes/{quizId}/questions [post]
func (h *QuizHandler) CreateQuestion(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	var req dto.CreateQuestionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	req.QuizID = quizID // Ensure quiz ID matches URL

	question, err := h.quizService.CreateQuestion(c.Request.Context(), &req, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to create question", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("creation_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(question))
}

// UpdateQuestion godoc
// @Summary Update question
// @Description Update question details (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param questionId path int true "Question ID"
// @Param request body dto.UpdateQuestionRequest true "Updated question data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuestionResponse} "Question updated successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or validation error"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Router /questions/{questionId} [put]
func (h *QuizHandler) UpdateQuestion(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	questionID, err := strconv.ParseInt(c.Param("questionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_question_id", "Invalid question ID"))
		return
	}

	var req dto.UpdateQuestionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	question, err := h.quizService.UpdateQuestion(c.Request.Context(), questionID, &req, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to update question", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(question))
}

// DeleteQuestion godoc
// @Summary Delete question
// @Description Delete a question from a quiz (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param questionId path int true "Question ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Question deleted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid question ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Router /questions/{questionId} [delete]
func (h *QuizHandler) DeleteQuestion(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	questionID, err := strconv.ParseInt(c.Param("questionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_question_id", "Invalid question ID"))
		return
	}

	if err := h.quizService.DeleteQuestion(c.Request.Context(), questionID, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to delete question", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("deletion_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Question deleted successfully"))
}

// ListQuestions godoc
// @Summary List questions
// @Description Get all questions for a quiz (correct answers hidden for students)
// @Tags Quiz
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.QuestionResponse} "List of questions"
// @Failure 400 {object} dto.ErrorResponse "Invalid quiz ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /quizzes/{quizId}/questions [get]
func (h *QuizHandler) ListQuestions(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	// Teachers see correct answers, students don't
	includeCorrectAnswers := userRole.(string) != "STUDENT"

	questions, err := h.quizService.ListQuestions(c.Request.Context(), quizID, userID.(int64), userRole.(string), includeCorrectAnswers)
	if err != nil {
		logger.Error("Failed to list questions", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(questions))
}

// ============================================
// STUDENT QUIZ OPERATIONS
// ============================================

// StartQuizAttempt godoc
// @Summary Start quiz attempt
// @Description Start a new attempt to take a quiz
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.QuizAttemptResponse} "Quiz attempt started"
// @Failure 400 {object} dto.ErrorResponse "Cannot start attempt (max attempts reached, quiz not available, etc.)"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /quizzes/{quizId}/start [post]
func (h *QuizHandler) StartQuizAttempt(c *gin.Context) {
	userID, _ := c.Get("user_id")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	ipAddress := c.ClientIP()
	userAgent := c.Request.UserAgent()

	attempt, err := h.quizService.StartQuizAttempt(c.Request.Context(), quizID, userID.(int64), ipAddress, userAgent)
	if err != nil {
		logger.Error("Failed to start quiz attempt", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("start_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(attempt))
}

// SubmitAnswer godoc
// @Summary Submit an answer
// @Description Submit an answer for a question in an active quiz attempt
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param attemptId path int true "Attempt ID"
// @Param request body dto.SubmitAnswerRequest true "Answer data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.StudentAnswerResponse} "Answer submitted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or quiz already submitted"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /attempts/{attemptId}/answers [post]
func (h *QuizHandler) SubmitAnswer(c *gin.Context) {
	userID, _ := c.Get("user_id")

	attemptID, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}

	var req dto.SubmitAnswerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	req.AttemptID = attemptID

	answer, err := h.quizService.SubmitAnswer(c.Request.Context(), &req, userID.(int64))
	if err != nil {
		logger.Error("Failed to submit answer", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("submission_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(answer))
}

// SubmitQuiz godoc
// @Summary Submit quiz
// @Description Submit (finalize) a quiz attempt for grading
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param attemptId path int true "Attempt ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.SuccessResponse} "Quiz submitted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid attempt ID or quiz already submitted"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /attempts/{attemptId}/submit [post]
func (h *QuizHandler) SubmitQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")

	attemptID, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}

	result, err := h.quizService.SubmitQuiz(c.Request.Context(), attemptID, userID.(int64))
	if err != nil {
		logger.Error("Failed to submit quiz", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("submission_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// GetQuizResult godoc
// @Summary Get quiz result
// @Description Get the result of a submitted quiz attempt
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param attemptId path int true "Attempt ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizResultResponse} "Quiz result"
// @Failure 400 {object} dto.ErrorResponse "Invalid attempt ID or quiz not submitted"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not your attempt"
// @Router /attempts/{attemptId}/result [get]
func (h *QuizHandler) GetQuizResult(c *gin.Context) {
	userID, _ := c.Get("user_id")

	attemptID, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}

	result, err := h.quizService.GetQuizResult(c.Request.Context(), attemptID, userID.(int64))
	if err != nil {
		logger.Error("Failed to get quiz result", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("retrieval_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// ReviewQuiz godoc
// @Summary Review quiz
// @Description Review a completed quiz attempt with correct answers (if allowed by quiz settings)
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param attemptId path int true "Attempt ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizReviewResponse} "Quiz review with correct answers"
// @Failure 400 {object} dto.ErrorResponse "Invalid attempt ID or review not allowed"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not your attempt"
// @Router /attempts/{attemptId}/review [get]
func (h *QuizHandler) ReviewQuiz(c *gin.Context) {
	userID, _ := c.Get("user_id")

	attemptID, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}

	review, err := h.quizService.ReviewQuiz(c.Request.Context(), attemptID, userID.(int64))
	if err != nil {
		logger.Error("Failed to review quiz", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("review_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(review))
}

// ============================================
// GRADING OPERATIONS (Teacher)
// ============================================

// GradeAnswer godoc
// @Summary Grade an answer
// @Description Manually grade a student's answer (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param answerId path int true "Answer ID"
// @Param request body dto.GradeAnswerRequest true "Grade data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Answer graded successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - teacher/admin only"
// @Router /answers/{answerId}/grade [post]
func (h *QuizHandler) GradeAnswer(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	answerID, err := strconv.ParseInt(c.Param("answerId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_answer_id", "Invalid answer ID"))
		return
	}

	var req dto.GradeAnswerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	req.AnswerID = answerID

	if err := h.quizService.GradeAnswer(c.Request.Context(), &req, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to grade answer", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("grading_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Answer graded successfully"))
}

// BulkGrade godoc
// @Summary Bulk grade answers
// @Description Grade multiple answers at once (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param request body dto.BulkGradeRequest true "Bulk grade data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Answers graded successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - teacher/admin only"
// @Router /quizzes/{quizId}/bulk-grade [post]
func (h *QuizHandler) BulkGrade(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	var req dto.BulkGradeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	if err := h.quizService.BulkGrade(c.Request.Context(), &req, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to bulk grade", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("grading_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Answers graded successfully"))
}

// ListAnswersForGrading godoc
// @Summary List answers for grading
// @Description Get all student answers that need manual grading (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.StudentAnswerForGrading} "List of answers needing grading"
// @Failure 400 {object} dto.ErrorResponse "Invalid quiz ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - teacher/admin only"
// @Router /quizzes/{quizId}/grading [get]
func (h *QuizHandler) ListAnswersForGrading(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	answers, err := h.quizService.ListStudentAnswersForGrading(c.Request.Context(), quizID, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to list answers for grading", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(answers))
}

// ============================================
// IMAGE UPLOAD HANDLERS
// ============================================

// UploadQuestionImage godoc
// @Summary Upload question image
// @Description Upload an image for a quiz question (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept multipart/form-data
// @Produce json
// @Param questionId path int true "Question ID"
// @Param image formData file true "Image file (JPEG, PNG, GIF, WebP, max 5MB)"
// @Param position formData string false "Image position (above_question, below_question, inline)" default(above_question)
// @Param caption formData string false "Image caption"
// @Param alt_text formData string false "Alternative text for accessibility"
// @Param display_width formData string false "Display width (e.g., 100%, 500px)" default(100%)
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.QuestionImage} "Image uploaded successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid file or file too large"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /questions/{questionId}/images [post]
func (h *QuizHandler) UploadQuestionImage(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	questionID, err := strconv.ParseInt(c.Param("questionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_question_id", "Invalid question ID"))
		return
	}

	position := c.PostForm("position")
	if position == "" {
		position = "above_question"
	}
	
	caption := c.PostForm("caption")
	altText := c.PostForm("alt_text")
	displayWidth := c.PostForm("display_width")
	if displayWidth == "" {
		displayWidth = "100%"
	}

	file, err := c.FormFile("image")
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_file", "Image file is required"))
		return
	}

	allowedTypes := map[string]bool{
		"image/jpeg": true,
		"image/png":  true,
		"image/gif":  true,
		"image/webp": true,
	}

	if !allowedTypes[file.Header.Get("Content-Type")] {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_type", 
			"Only JPEG, PNG, GIF, and WebP images are allowed"))
		return
	}

	if file.Size > 5*1024*1024 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("file_too_large", 
			"Image must be smaller than 5MB"))
		return
	}

	src, err := file.Open()
	if err != nil {
		logger.Error("Failed to open uploaded file", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to process file"))
		return
	}
	defer src.Close()

	fileData := make([]byte, file.Size)
	if _, err := src.Read(fileData); err != nil {
		logger.Error("Failed to read file data", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to read file"))
		return
	}

	ext := filepath.Ext(file.Filename)
	imageID := uuid.New().String()
	filename := fmt.Sprintf("quizzes/question_%d/%s%s", questionID, imageID, ext)

	storagePath, err := h.storage.Upload(c.Request.Context(), filename, fileData)
	if err != nil {
		logger.Error("Failed to upload to storage", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("upload_failed", "Failed to save file"))
		return
	}

	image := dto.QuestionImage{
		ID:           imageID,
		URL:          fmt.Sprintf("/files/%s", filename),
		FilePath:     storagePath,
		FileName:     file.Filename,
		FileSize:     file.Size,
		MimeType:     file.Header.Get("Content-Type"),
		Position:     position,
		Caption:      caption,
		AltText:      altText,
		DisplayWidth: displayWidth,
		CreatedAt:    time.Now(),
	}

	if err := h.quizService.AddQuestionImage(c.Request.Context(), questionID, &image, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to add image to question", err)
		_ = h.storage.Delete(c.Request.Context(), filename)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(image))
}

// DeleteQuestionImage godoc
// @Summary Delete question image
// @Description Delete an image from a quiz question (teacher/admin only)
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param questionId path int true "Question ID"
// @Param imageId path string true "Image ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Image deleted successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid question or image ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not quiz owner"
// @Failure 404 {object} dto.ErrorResponse "Image not found"
// @Router /questions/{questionId}/images/{imageId} [delete]
func (h *QuizHandler) DeleteQuestionImage(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	questionID, err := strconv.ParseInt(c.Param("questionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_question_id", "Invalid question ID"))
		return
	}

	imageID := c.Param("imageId")
	if imageID == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_image_id", "Image ID is required"))
		return
	}

	image, err := h.quizService.GetQuestionImage(c.Request.Context(), questionID, imageID, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to get question image", err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Image not found"))
		return
	}

	if err := h.quizService.RemoveQuestionImage(c.Request.Context(), questionID, imageID, userID.(int64), userRole.(string)); err != nil {
		logger.Error("Failed to remove image from question", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}

	if err := h.storage.Delete(c.Request.Context(), image.FilePath); err != nil {
		logger.Error("Failed to delete file from storage", err)
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Image deleted successfully"))
}

// ListQuestionImages godoc
// @Summary List question images
// @Description Get all images for a quiz question
// @Tags Quiz
// @Accept json
// @Produce json
// @Param questionId path int true "Question ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.QuestionImage} "List of images"
// @Failure 400 {object} dto.ErrorResponse "Invalid question ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /questions/{questionId}/images [get]
func (h *QuizHandler) ListQuestionImages(c *gin.Context) {
	userID, _ := c.Get("user_id")
	userRole, _ := c.Get("user_role")

	questionID, err := strconv.ParseInt(c.Param("questionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_question_id", "Invalid question ID"))
		return
	}

	images, err := h.quizService.ListQuestionImages(c.Request.Context(), questionID, userID.(int64), userRole.(string))
	if err != nil {
		logger.Error("Failed to list question images", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(images))
}

// GetQuizByContentID godoc
// @Summary Get quiz by content ID
// @Description Get quiz associated with a specific content
// @Tags Quiz - Teacher
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizResponse} "Quiz details"
// @Failure 400 {object} dto.ErrorResponse "Invalid content ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 404 {object} dto.ErrorResponse "Quiz not found"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /content/{contentId}/quiz [get]
func (h *QuizHandler) GetQuizByContentID(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_content_id", "Invalid content ID"))
		return
	}

	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User not authenticated"))
		return
	}

	userRole, _ := c.Get("user_role")

	quiz, err := h.quizService.GetQuizByContentID(c.Request.Context(), contentID, userID.(int64), userRole.(string))
	if err != nil {
		if err.Error() == "quiz not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Quiz not found for this content"))
			return
		}
		if err.Error() == "permission denied" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "You don't have permission to view this quiz"))
			return
		}
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(quiz))
}