package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/logger"
)

type QuizService struct {
	quizRepo   *repository.QuizRepository
	courseRepo *repository.CourseRepository
	userRepo   *repository.UserRepository
}

func NewQuizService(
	quizRepo *repository.QuizRepository,
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
) *QuizService {
	return &QuizService{
		quizRepo:   quizRepo,
		courseRepo: courseRepo,
		userRepo:   userRepo,
	}
}

// ============================================
// QUIZ MANAGEMENT (Teacher)
// ============================================

// CreateQuiz creates a new quiz
func (s *QuizService) CreateQuiz(ctx context.Context, req *dto.CreateQuizRequest, createdBy int64, userRole string) (*dto.QuizResponse, error) {
	// Verify content exists and user has permission
	content, err := s.courseRepo.GetContentByID(ctx, req.ContentID)
	if err != nil {
		return nil, fmt.Errorf("content not found")
	}

	// Check if quiz already exists for this content
	existingQuiz, _ := s.quizRepo.GetQuizByContentID(ctx, req.ContentID)
	if existingQuiz != nil {
		return nil, fmt.Errorf("quiz already exists for this content")
	}

	// Get section and course to verify ownership
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return nil, fmt.Errorf("section not found")
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("course not found")
	}

	// Check permission (owner or admin)
	if userRole != "ADMIN" && course.CreatedBy != createdBy {
		return nil, fmt.Errorf("permission denied: you don't own this course")
	}

	// Create quiz model
	quiz := &models.Quiz{
		ContentID:            req.ContentID,
		Title:                req.Title,
		Description:          toNullString(req.Description),
		Instructions:         toNullString(req.Instructions),
		TimeLimitMinutes:     toNullInt32(req.TimeLimitMinutes),
		AvailableFrom:        toNullTime(req.AvailableFrom),
		AvailableUntil:       toNullTime(req.AvailableUntil),
		MaxAttempts:          toNullInt32(req.MaxAttempts),
		ShuffleQuestions:     req.ShuffleQuestions,
		ShuffleAnswers:       req.ShuffleAnswers,
		PassingScore:         toNullFloat64(req.PassingScore),
		TotalPoints:          req.TotalPoints,
		AutoGrade:            req.AutoGrade,
		ShowResultsImmediately: req.ShowResultsImmediately,
		ShowCorrectAnswers:   req.ShowCorrectAnswers,
		AllowReview:          req.AllowReview,
		ShowFeedback:         req.ShowFeedback,
		IsPublished:          false, // Always start as draft
		CreatedBy:            createdBy,
	}

	if err := s.quizRepo.CreateQuiz(ctx, quiz); err != nil {
		return nil, fmt.Errorf("failed to create quiz: %w", err)
	}

	return s.buildQuizResponse(quiz), nil
}

// UpdateQuiz updates quiz details
func (s *QuizService) UpdateQuiz(ctx context.Context, quizID int64, req *dto.UpdateQuizRequest, userID int64, userRole string) (*dto.QuizResponse, error) {
	// Get existing quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return nil, err
	}

	// Verify ownership
	if err := s.verifyQuizOwnership(ctx, quizID, userID, userRole); err != nil {
		return nil, err
	}

	// Update fields
	if req.Title != nil {
		quiz.Title = *req.Title
	}
	if req.Description != nil {
		quiz.Description = toNullString(*req.Description)
	}
	if req.Instructions != nil {
		quiz.Instructions = toNullString(*req.Instructions)
	}
	if req.TimeLimitMinutes != nil {
		quiz.TimeLimitMinutes = toNullInt32(req.TimeLimitMinutes)
	}
	if req.AvailableFrom != nil {
		quiz.AvailableFrom = toNullTime(req.AvailableFrom)
	}
	if req.AvailableUntil != nil {
		quiz.AvailableUntil = toNullTime(req.AvailableUntil)
	}
	if req.MaxAttempts != nil {
		quiz.MaxAttempts = toNullInt32(req.MaxAttempts)
	}
	if req.ShuffleQuestions != nil {
		quiz.ShuffleQuestions = *req.ShuffleQuestions
	}
	if req.ShuffleAnswers != nil {
		quiz.ShuffleAnswers = *req.ShuffleAnswers
	}
	if req.PassingScore != nil {
		quiz.PassingScore = toNullFloat64(req.PassingScore)
	}
	if req.TotalPoints != nil {
		quiz.TotalPoints = *req.TotalPoints
	}
	if req.AutoGrade != nil {
		quiz.AutoGrade = *req.AutoGrade
	}
	if req.ShowResultsImmediately != nil {
		quiz.ShowResultsImmediately = *req.ShowResultsImmediately
	}
	if req.ShowCorrectAnswers != nil {
		quiz.ShowCorrectAnswers = *req.ShowCorrectAnswers
	}
	if req.AllowReview != nil {
		quiz.AllowReview = *req.AllowReview
	}
	if req.ShowFeedback != nil {
		quiz.ShowFeedback = *req.ShowFeedback
	}
	if req.IsPublished != nil {
		quiz.IsPublished = *req.IsPublished
	}

	if err := s.quizRepo.UpdateQuiz(ctx, quiz); err != nil {
		return nil, fmt.Errorf("failed to update quiz: %w", err)
	}

	return s.buildQuizResponse(quiz), nil
}

// DeleteQuiz deletes a quiz
func (s *QuizService) DeleteQuiz(ctx context.Context, quizID int64, userID int64, userRole string) error {
	// Verify ownership
	if err := s.verifyQuizOwnership(ctx, quizID, userID, userRole); err != nil {
		return err
	}

	// Check if there are any attempts
	attempts, err := s.quizRepo.ListQuizAttempts(ctx, quizID, "")
	if err != nil {
		return err
	}

	if len(attempts) > 0 {
		return fmt.Errorf("cannot delete quiz with existing student attempts")
	}

	return s.quizRepo.DeleteQuiz(ctx, quizID)
}

// GetQuiz retrieves quiz details
func (s *QuizService) GetQuiz(ctx context.Context, quizID int64, userID int64, userRole string) (*dto.QuizResponse, error) {
	quiz, err := s.quizRepo.GetQuizWithStats(ctx, quizID)
	if err != nil {
		return nil, err
	}

	// Check permission
	if !quiz.IsPublished && userRole == "STUDENT" {
		// Students can only see published quizzes unless they've started an attempt
		hasAttempt, err := s.quizRepo.GetStudentLatestAttempt(ctx, quizID, userID)
		if err != nil || hasAttempt == nil {
			return nil, fmt.Errorf("quiz not available")
		}
	}

	response := s.buildQuizResponseWithStats(quiz)
	return response, nil
}

// ============================================
// QUESTION MANAGEMENT (Teacher)
// ============================================

// CreateQuestion creates a new question with options/answers
func (s *QuizService) CreateQuestion(ctx context.Context, req *dto.CreateQuestionRequest, userID int64, userRole string) (*dto.QuestionResponse, error) {
	// Verify quiz ownership
	if err := s.verifyQuizOwnership(ctx, req.QuizID, userID, userRole); err != nil {
		return nil, err
	}

	// Validate question type and requirements
	if err := s.validateQuestionRequest(req); err != nil {
		return nil, err
	}

	// Begin transaction
	tx, err := s.quizRepo.BeginTx(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()

	// Marshal settings
	var settingsJSON []byte
	if req.Settings == nil {
		settingsJSON = []byte(`{}`)
	} else {
		var err error
		settingsJSON, err = json.Marshal(req.Settings)
		if err != nil {
			return nil, fmt.Errorf("invalid settings: %w", err)
		}
	}
	logger.Info(string(settingsJSON))

	// Create question
	question := &models.QuizQuestion{
		QuizID:       req.QuizID,
		QuestionType: string(req.QuestionType),
		QuestionText: req.QuestionText,
		QuestionHTML: toNullString(req.QuestionHTML),
		Explanation:  toNullString(req.Explanation),
		Points:       req.Points,
		OrderIndex:   req.OrderIndex,
		Settings:     settingsJSON,
		IsRequired:   req.IsRequired,
	}

	if err := s.quizRepo.CreateQuestion(ctx, question); err != nil {
		return nil, fmt.Errorf("failed to create question: %w", err)
	}

	// Create answer options (for choice questions)
	if len(req.AnswerOptions) > 0 {
		for _, optReq := range req.AnswerOptions {
			option := &models.QuizAnswerOption{
				QuestionID: question.ID,
				OptionText: optReq.OptionText,
				OptionHTML: toNullString(optReq.OptionHTML),
				IsCorrect:  optReq.IsCorrect,
				OrderIndex: optReq.OrderIndex,
				BlankID:    toNullInt32(optReq.BlankID),
			}
			if err := s.quizRepo.CreateAnswerOption(ctx, option); err != nil {
				return nil, fmt.Errorf("failed to create answer option: %w", err)
			}
		}
	}

	// Create correct answers (for text/fill-blank questions)
	if len(req.CorrectAnswers) > 0 {
		for _, ansReq := range req.CorrectAnswers {
			answer := &models.QuizCorrectAnswer{
				QuestionID:    question.ID,
				AnswerText:    toNullString(ansReq.AnswerText),
				BlankID:       toNullInt32(ansReq.BlankID),
				BlankPosition: toNullInt32(ansReq.BlankPosition),
				CaseSensitive: ansReq.CaseSensitive,
				ExactMatch:    ansReq.ExactMatch,
			}
			if err := s.quizRepo.CreateCorrectAnswer(ctx, answer); err != nil {
				return nil, fmt.Errorf("failed to create correct answer: %w", err)
			}
		}
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit transaction: %w", err)
	}

	// Retrieve complete question
	questionWithOptions, err := s.quizRepo.GetQuestionWithOptions(ctx, question.ID)
	if err != nil {
		return nil, err
	}

	return s.buildQuestionResponse(questionWithOptions), nil
}

// UpdateQuestion updates question details
func (s *QuizService) UpdateQuestion(ctx context.Context, questionID int64, req *dto.UpdateQuestionRequest, userID int64, userRole string) (*dto.QuestionResponse, error) {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return nil, err
	}

	// Verify quiz ownership
	if err := s.verifyQuizOwnership(ctx, question.QuizID, userID, userRole); err != nil {
		return nil, err
	}

	// Update fields
	if req.QuestionText != nil {
		question.QuestionText = *req.QuestionText
	}
	if req.QuestionHTML != nil {
		question.QuestionHTML = toNullString(*req.QuestionHTML)
	}
	if req.Explanation != nil {
		question.Explanation = toNullString(*req.Explanation)
	}
	if req.Points != nil {
		question.Points = *req.Points
	}
	if req.OrderIndex != nil {
		question.OrderIndex = *req.OrderIndex
	}
	if req.Settings != nil {
		settingsJSON, err := json.Marshal(*req.Settings)
		if err != nil {
			return nil, fmt.Errorf("invalid settings: %w", err)
		}
		question.Settings = settingsJSON
	}
	logger.Info(string(question.Settings))
	if req.IsRequired != nil {
		question.IsRequired = *req.IsRequired
	}

	if err := s.quizRepo.UpdateQuestion(ctx, question); err != nil {
		return nil, fmt.Errorf("failed to update question: %w", err)
	}

	questionWithOptions, err := s.quizRepo.GetQuestionWithOptions(ctx, questionID)
	if err != nil {
		return nil, err
	}

	return s.buildQuestionResponse(questionWithOptions), nil
}

// DeleteQuestion deletes a question
func (s *QuizService) DeleteQuestion(ctx context.Context, questionID int64, userID int64, userRole string) error {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return err
	}

	// Verify quiz ownership
	if err := s.verifyQuizOwnership(ctx, question.QuizID, userID, userRole); err != nil {
		return err
	}

	return s.quizRepo.DeleteQuestion(ctx, questionID)
}

// ListQuestions lists all questions for a quiz
func (s *QuizService) ListQuestions(ctx context.Context, quizID int64, userID int64, userRole string, includeCorrectAnswers bool) ([]interface{}, error) {
	// Verify permission to view quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return nil, err
	}

	if !quiz.IsPublished && userRole == "STUDENT" {
		return nil, fmt.Errorf("quiz not available")
	}

	questions, err := s.quizRepo.ListQuestionsWithOptions(ctx, quizID)
	if err != nil {
		return nil, err
	}

	// Build response based on role
	var result []interface{}
	for _, q := range questions {
		if userRole == "STUDENT" && !includeCorrectAnswers {
			// Hide correct answers for students
			result = append(result, s.buildStudentQuestionResponse(&q))
		} else {
			// Show everything for teachers
			result = append(result, s.buildQuestionResponse(&q))
		}
	}

	return result, nil
}

// AddQuestionImage adds an image to a question's settings
func (s *QuizService) AddQuestionImage(ctx context.Context, questionID int64, image *dto.QuestionImage, userID int64, userRole string) error {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return fmt.Errorf("question not found: %w", err)
	}

	if err := s.verifyQuizOwnership(ctx, question.QuizID, userID, userRole); err != nil {
		return err
	}

	var settings map[string]interface{}
	if len(question.Settings) > 0 {
		raw := question.Settings
		logger.Info(string(raw))

		if len(raw) > 0 && raw[0] == '"' {
			var inner string
			if err := json.Unmarshal(raw, &inner); err == nil {
				raw = []byte(inner)
			}
		}

		if err := json.Unmarshal(question.Settings, &settings); err != nil {
			return fmt.Errorf("failed to parse settings: %w", err)
		}
	} else {
		settings = make(map[string]interface{})
	}

	var images []dto.QuestionImage
	if imagesData, ok := settings["images"]; ok {
		jsonData, _ := json.Marshal(imagesData)
		_ = json.Unmarshal(jsonData, &images)
	}

	if len(images) >= 5 {
		return fmt.Errorf("maximum 5 images per question")
	}

	images = append(images, *image)
	settings["images"] = images

	settingsJSON, err := json.Marshal(settings)
	if err != nil {
		return fmt.Errorf("failed to marshal settings: %w", err)
	}

	question.Settings = settingsJSON

	return s.quizRepo.UpdateQuestion(ctx, question)
}

// RemoveQuestionImage removes an image from a question's settings
func (s *QuizService) RemoveQuestionImage(ctx context.Context, questionID int64, imageID string, userID int64, userRole string) error {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return fmt.Errorf("question not found: %w", err)
	}

	if err := s.verifyQuizOwnership(ctx, question.QuizID, userID, userRole); err != nil {
		return err
	}

	var settings map[string]interface{}
	if len(question.Settings) > 0 {
		if err := json.Unmarshal(question.Settings, &settings); err != nil {
			return fmt.Errorf("failed to parse settings: %w", err)
		}
	} else {
		return fmt.Errorf("no images found")
	}

	var images []dto.QuestionImage
	if imagesData, ok := settings["images"]; ok {
		jsonData, _ := json.Marshal(imagesData)
		_ = json.Unmarshal(jsonData, &images)
	}

	found := false
	var newImages []dto.QuestionImage
	for _, img := range images {
		if img.ID != imageID {
			newImages = append(newImages, img)
		} else {
			found = true
		}
	}

	if !found {
		return fmt.Errorf("image not found")
	}

	settings["images"] = newImages

	settingsJSON, err := json.Marshal(settings)
	if err != nil {
		return fmt.Errorf("failed to marshal settings: %w", err)
	}

	question.Settings = settingsJSON

	return s.quizRepo.UpdateQuestion(ctx, question)
}

// GetQuestionImage gets a specific image from a question
func (s *QuizService) GetQuestionImage(ctx context.Context, questionID int64, imageID string, userID int64, userRole string) (*dto.QuestionImage, error) {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return nil, fmt.Errorf("question not found: %w", err)
	}

	var settings map[string]interface{}
	if len(question.Settings) > 0 {
		if err := json.Unmarshal(question.Settings, &settings); err != nil {
			return nil, fmt.Errorf("failed to parse settings: %w", err)
		}
	}

	var images []dto.QuestionImage
	if imagesData, ok := settings["images"]; ok {
		jsonData, _ := json.Marshal(imagesData)
		_ = json.Unmarshal(jsonData, &images)
	}

	for _, img := range images {
		if img.ID == imageID {
			return &img, nil
		}
	}

	return nil, fmt.Errorf("image not found")
}

// ListQuestionImages lists all images for a question
func (s *QuizService) ListQuestionImages(ctx context.Context, questionID int64, userID int64, userRole string) ([]dto.QuestionImage, error) {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return nil, fmt.Errorf("question not found: %w", err)
	}

	var settings map[string]interface{}
	if len(question.Settings) > 0 {
		if err := json.Unmarshal(question.Settings, &settings); err != nil {
			return []dto.QuestionImage{}, nil
		}
	}

	var images []dto.QuestionImage
	if imagesData, ok := settings["images"]; ok {
		jsonData, _ := json.Marshal(imagesData)
		_ = json.Unmarshal(jsonData, &images)
	}

	return images, nil
}

// extractImagesFromSettings helper to extract images from JSONB settings
func extractImagesFromSettings(settings []byte) []dto.QuestionImage {
	if len(settings) == 0 {
		return []dto.QuestionImage{}
	}

	var settingsMap map[string]interface{}
	if err := json.Unmarshal(settings, &settingsMap); err != nil {
		return []dto.QuestionImage{}
	}

	if imagesData, ok := settingsMap["images"]; ok {
		jsonData, _ := json.Marshal(imagesData)
		var images []dto.QuestionImage
		if err := json.Unmarshal(jsonData, &images); err == nil {
			return images
		}
	}

	return []dto.QuestionImage{}
}

// StartQuizAttempt starts a new quiz attempt for a student
func (s *QuizService) StartQuizAttempt(ctx context.Context, quizID, studentID int64, ipAddress, userAgent string) (*dto.QuizAttemptResponse, error) {
	// Get quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return nil, err
	}

	// Check if quiz is available
	if !quiz.IsPublished {
		return nil, fmt.Errorf("quiz is not published")
	}

	// Check availability window
	now := time.Now()
	if quiz.AvailableFrom.Valid && now.Before(quiz.AvailableFrom.Time) {
		return nil, fmt.Errorf("quiz not available yet")
	}
	if quiz.AvailableUntil.Valid && now.After(quiz.AvailableUntil.Time) {
		return nil, fmt.Errorf("quiz is no longer available")
	}

	// Check max attempts
	if quiz.MaxAttempts.Valid {
		count, err := s.quizRepo.GetStudentAttemptCount(ctx, quizID, studentID)
		if err != nil {
			return nil, err
		}
		if count >= int(quiz.MaxAttempts.Int32) {
			return nil, fmt.Errorf("maximum attempts reached")
		}
	}

	// Check for in-progress attempt
	latestAttempt, err := s.quizRepo.GetStudentLatestAttempt(ctx, quizID, studentID)
	if err != nil {
		return nil, err
	}
	if latestAttempt != nil && latestAttempt.Status == models.AttemptStatusInProgress {
		// Return existing attempt
		return s.buildAttemptResponse(latestAttempt), nil
	}

	// Create new attempt
	attemptNumber := 1
	if latestAttempt != nil {
		attemptNumber = latestAttempt.AttemptNumber + 1
	}

	attempt := &models.QuizAttempt{
		QuizID:        quizID,
		StudentID:     studentID,
		AttemptNumber: attemptNumber,
		Status:        models.AttemptStatusInProgress,
		IPAddress:     toNullString(ipAddress),
		UserAgent:     toNullString(userAgent),
	}

	if err := s.quizRepo.CreateAttempt(ctx, attempt); err != nil {
		return nil, fmt.Errorf("failed to create attempt: %w", err)
	}

	return s.buildAttemptResponse(attempt), nil
}

// SubmitAnswer submits or updates an answer for a question
func (s *QuizService) SubmitAnswer(ctx context.Context, req *dto.SubmitAnswerRequest, studentID int64) (*dto.StudentAnswerResponse, error) {
	// Verify attempt ownership
	attempt, err := s.quizRepo.GetAttempt(ctx, req.AttemptID)
	if err != nil {
		return nil, err
	}

	if attempt.StudentID != studentID {
		return nil, fmt.Errorf("permission denied")
	}

	if attempt.Status != models.AttemptStatusInProgress {
		return nil, fmt.Errorf("attempt is not in progress")
	}

	// Check time limit
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if quiz.TimeLimitMinutes.Valid {
		elapsed := time.Since(attempt.StartedAt)
		if elapsed.Minutes() > float64(quiz.TimeLimitMinutes.Int32) {
			return nil, fmt.Errorf("time limit exceeded")
		}
	}

	// Verify question belongs to quiz
	question, err := s.quizRepo.GetQuestion(ctx, req.QuestionID)
	if err != nil {
		return nil, err
	}

	if question.QuizID != attempt.QuizID {
		return nil, fmt.Errorf("question does not belong to this quiz")
	}

	// Validate answer data format
	if err := s.validateAnswerData(question.QuestionType, req.AnswerData); err != nil {
		return nil, err
	}

	// Marshal answer data
	answerDataJSON, err := json.Marshal(req.AnswerData)
	if err != nil {
		return nil, fmt.Errorf("invalid answer data: %w", err)
	}

	// Check if answer already exists
	existingAnswer, err := s.quizRepo.GetStudentAnswerByQuestion(ctx, req.AttemptID, req.QuestionID)
	if err != nil {
		return nil, err
	}

	var answer *models.QuizStudentAnswer

	if existingAnswer != nil {
		// Update existing answer
		existingAnswer.AnswerData = answerDataJSON
		if err := s.quizRepo.UpdateStudentAnswer(ctx, existingAnswer); err != nil {
			return nil, fmt.Errorf("failed to update answer: %w", err)
		}
		answer = existingAnswer
	} else {
		// Create new answer
		answer = &models.QuizStudentAnswer{
			AttemptID:  req.AttemptID,
			QuestionID: req.QuestionID,
			AnswerData: answerDataJSON,
		}
		if err := s.quizRepo.CreateStudentAnswer(ctx, answer); err != nil {
			return nil, fmt.Errorf("failed to create answer: %w", err)
		}
	}

	// Auto-grade if possible
	if quiz.AutoGrade && s.canAutoGrade(question.QuestionType) {
		if err := s.autoGradeAnswer(ctx, answer, question); err != nil {
			// Log error but don't fail the submission
			fmt.Printf("Auto-grading failed: %v\n", err)
		}
	}

	return s.buildStudentAnswerResponse(answer), nil
}

// SubmitQuiz submits the entire quiz attempt
func (s *QuizService) SubmitQuiz(ctx context.Context, attemptID, studentID int64) (*dto.QuizResultResponse, error) {
	// Verify attempt ownership
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt.StudentID != studentID {
		return nil, fmt.Errorf("permission denied")
	}

	if attempt.Status != models.AttemptStatusInProgress {
		return nil, fmt.Errorf("attempt already submitted")
	}

	// Get quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	// Calculate time spent
	timeSpent := int32(time.Since(attempt.StartedAt).Seconds())
	now := time.Now()

	// Update attempt status
	attempt.SubmittedAt = sql.NullTime{Time: now, Valid: true}
	attempt.TimeSpentSeconds = sql.NullInt32{Int32: timeSpent, Valid: true}
	attempt.Status = models.AttemptStatusSubmitted

	// Auto-grade all objective questions
	if quiz.AutoGrade {
		answers, err := s.quizRepo.ListAttemptAnswers(ctx, attemptID)
		if err != nil {
			return nil, err
		}

		for _, ans := range answers {
			question, err := s.quizRepo.GetQuestion(ctx, ans.QuestionID)
			if err != nil {
				continue
			}

			if s.canAutoGrade(question.QuestionType) {
				_ = s.autoGradeAnswer(ctx, &ans, question)
			}
		}

		attempt.AutoGradedAt = sql.NullTime{Time: now, Valid: true}
	}

	// Calculate total score
	if err := s.calculateAttemptScore(ctx, attempt, quiz); err != nil {
		return nil, fmt.Errorf("failed to calculate score: %w", err)
	}

	if err := s.quizRepo.UpdateAttempt(ctx, attempt); err != nil {
		return nil, fmt.Errorf("failed to submit quiz: %w", err)
	}

	// Update analytics
	_ = s.quizRepo.UpdateQuizAnalytics(ctx, quiz.ID)

	// Build result response
	return s.buildQuizResultResponse(ctx, attempt, quiz)
}

// GetQuizResult retrieves quiz results
func (s *QuizService) GetQuizResult(ctx context.Context, attemptID, studentID int64) (*dto.QuizResultResponse, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt.StudentID != studentID {
		return nil, fmt.Errorf("permission denied")
	}

	if attempt.Status == models.AttemptStatusInProgress {
		return nil, fmt.Errorf("quiz not submitted yet")
	}

	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if !quiz.ShowResultsImmediately {
		return nil, fmt.Errorf("results not available yet")
	}

	return s.buildQuizResultResponse(ctx, attempt, quiz)
}

// ReviewQuiz allows student to review their submission
func (s *QuizService) ReviewQuiz(ctx context.Context, attemptID, studentID int64) (*dto.QuizReviewResponse, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt.StudentID != studentID {
		return nil, fmt.Errorf("permission denied")
	}

	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if !quiz.AllowReview {
		return nil, fmt.Errorf("review not allowed for this quiz")
	}

	return s.buildQuizReviewResponse(ctx, attempt, quiz)
}

// ============================================
// GRADING OPERATIONS (Teacher)
// ============================================

// GradeAnswer manually grades a student answer
func (s *QuizService) GradeAnswer(ctx context.Context, req *dto.GradeAnswerRequest, graderID int64, userRole string) error {
	// Get answer
	answer, err := s.quizRepo.GetStudentAnswer(ctx, req.AnswerID)
	if err != nil {
		return err
	}

	// Get attempt and quiz to verify permission
	attempt, err := s.quizRepo.GetAttempt(ctx, answer.AttemptID)
	if err != nil {
		return err
	}

	// Verify grader has permission
	if err := s.verifyQuizOwnership(ctx, attempt.QuizID, graderID, userRole); err != nil {
		return err
	}

	// Get question to validate points
	question, err := s.quizRepo.GetQuestion(ctx, answer.QuestionID)
	if err != nil {
		return err
	}

	if req.PointsEarned > question.Points {
		return fmt.Errorf("points earned cannot exceed question points")
	}

	// Update answer
	now := time.Now()
	answer.PointsEarned = sql.NullFloat64{Float64: req.PointsEarned, Valid: true}
	answer.GraderFeedback = toNullString(req.GraderFeedback)
	answer.GradedBy = sql.NullInt64{Int64: graderID, Valid: true}
	answer.GradedAt = sql.NullTime{Time: now, Valid: true}
	answer.IsCorrect = sql.NullBool{Bool: req.PointsEarned == question.Points, Valid: true}

	if err := s.quizRepo.UpdateStudentAnswer(ctx, answer); err != nil {
		return fmt.Errorf("failed to grade answer: %w", err)
	}

	// Always recalculate attempt score after grading
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return err
	}

	// Check if all answers are graded
	_, err = s.checkAllAnswersGraded(ctx, attempt.ID)
	if err != nil {
		return err
	}

	// Update manually graded timestamp if this is the first manual grading
	if !attempt.ManuallyGradedAt.Valid {
		attempt.ManuallyGradedAt = sql.NullTime{Time: now, Valid: true}
		attempt.GradedBy = sql.NullInt64{Int64: graderID, Valid: true}
	}
	
	// Recalculate score (this will set status to GRADED if all answers are graded)
	if err := s.calculateAttemptScore(ctx, attempt, quiz); err != nil {
		return err
	}

	if err := s.quizRepo.UpdateAttempt(ctx, attempt); err != nil {
		return err
	}

	return nil
}

// BulkGrade grades multiple answers at once
func (s *QuizService) BulkGrade(ctx context.Context, req *dto.BulkGradeRequest, graderID int64, userRole string) error {
	for _, gradeReq := range req.Grades {
		if err := s.GradeAnswer(ctx, &gradeReq, graderID, userRole); err != nil {
			return fmt.Errorf("failed to grade answer %d: %w", gradeReq.AnswerID, err)
		}
	}
	return nil
}

// ListStudentAnswersForGrading lists answers that need grading
func (s *QuizService) ListStudentAnswersForGrading(ctx context.Context, quizID int64, userID int64, userRole string) ([]dto.StudentAnswerForGrading, error) {
	// Verify permission
	if err := s.verifyQuizOwnership(ctx, quizID, userID, userRole); err != nil {
		return nil, err
	}

	// Get answers that need grading from repo
	repoAnswers, err := s.quizRepo.GetAnswersForGrading(ctx, quizID)
	if err != nil {
		return nil, fmt.Errorf("failed to get answers for grading: %w", err)
	}

	// Convert to DTO
	dtoAnswers := make([]dto.StudentAnswerForGrading, 0, len(repoAnswers))
	for _, ans := range repoAnswers {
		// Parse answer data
		var answerData map[string]interface{}
		if err := json.Unmarshal(ans.AnswerData, &answerData); err != nil {
			logger.Error("Failed to parse answer data", err)
			continue
		}

		dtoAnswer := dto.StudentAnswerForGrading{
			ID:           ans.AnswerID,
			AttemptID:    ans.AttemptID,
			StudentID:    ans.StudentID,
			StudentName:  ans.StudentName,
			StudentEmail: ans.StudentEmail,
			QuestionID:   ans.QuestionID,
			QuestionText: ans.QuestionText,
			QuestionType: ans.QuestionType,
			Points:       ans.Points,
			AnswerData:   answerData,
			AnsweredAt:   ans.AnsweredAt,
		}

		if ans.PointsEarned.Valid {
			dtoAnswer.PointsEarned = &ans.PointsEarned.Float64
		}
		if ans.GraderFeedback.Valid {
			dtoAnswer.Feedback = ans.GraderFeedback.String
		}

		dtoAnswers = append(dtoAnswers, dtoAnswer)
	}

	return dtoAnswers, nil
}

// canAutoGrade checks if a question type can be auto-graded
func (s *QuizService) canAutoGrade(questionType string) bool {
	autoGradableTypes := []string{
		models.QuestionTypeSingleChoice,
		models.QuestionTypeMultipleChoice,
		models.QuestionTypeFillBlankText,
		models.QuestionTypeFillBlankDropdown,
	}

	for _, t := range autoGradableTypes {
		if t == questionType {
			return true
		}
	}
	return false
}

// autoGradeAnswer automatically grades an answer
func (s *QuizService) autoGradeAnswer(ctx context.Context, answer *models.QuizStudentAnswer, question *models.QuizQuestion) error {
	var answerData map[string]interface{}
	if err := json.Unmarshal(answer.AnswerData, &answerData); err != nil {
		return err
	}

	var isCorrect bool
	var err error

	switch question.QuestionType {
	case models.QuestionTypeSingleChoice:
		isCorrect, err = s.gradeSingleChoice(ctx, answerData, question.ID)
	case models.QuestionTypeMultipleChoice:
		isCorrect, err = s.gradeMultipleChoice(ctx, answerData, question.ID)
	case models.QuestionTypeFillBlankText:
		isCorrect, err = s.gradeFillBlankText(ctx, answerData, question.ID)
	case models.QuestionTypeFillBlankDropdown:
		isCorrect, err = s.gradeFillBlankDropdown(ctx, answerData, question.ID)
	default:
		return fmt.Errorf("cannot auto-grade question type: %s", question.QuestionType)
	}

	if err != nil {
		return err
	}

	// Update answer with grading result
	pointsEarned := 0.0
	if isCorrect {
		pointsEarned = question.Points
	}

	now := time.Now()
	answer.IsCorrect = sql.NullBool{Bool: isCorrect, Valid: true}
	answer.PointsEarned = sql.NullFloat64{Float64: pointsEarned, Valid: true}
	answer.GradedAt = sql.NullTime{Time: now, Valid: true}

	return s.quizRepo.UpdateStudentAnswer(ctx, answer)
}

// gradeSingleChoice grades a single choice question
func (s *QuizService) gradeSingleChoice(ctx context.Context, answerData map[string]interface{}, questionID int64) (bool, error) {
	selectedID, ok := answerData["selected_option_id"].(float64) // JSON numbers are float64
	if !ok {
		return false, fmt.Errorf("invalid answer format")
	}

	options, err := s.quizRepo.ListAnswerOptions(ctx, questionID)
	if err != nil {
		return false, err
	}

	for _, opt := range options {
		if opt.ID == int64(selectedID) {
			return opt.IsCorrect, nil
		}
	}

	return false, nil
}

// gradeMultipleChoice grades a multiple choice question
func (s *QuizService) gradeMultipleChoice(ctx context.Context, answerData map[string]interface{}, questionID int64) (bool, error) {
	selectedIDs, ok := answerData["selected_option_ids"].([]interface{})
	if !ok {
		return false, fmt.Errorf("invalid answer format")
	}

	// Convert to map for easier lookup
	selectedMap := make(map[int64]bool)
	for _, id := range selectedIDs {
		if idFloat, ok := id.(float64); ok {
			selectedMap[int64(idFloat)] = true
		}
	}

	options, err := s.quizRepo.ListAnswerOptions(ctx, questionID)
	if err != nil {
		return false, err
	}

	correctCount := 0
	selectedCorrectCount := 0

	for _, opt := range options {
		if opt.IsCorrect {
			correctCount++
			if selectedMap[opt.ID] {
				selectedCorrectCount++
			}
		} else if selectedMap[opt.ID] {
			// Selected incorrect option
			return false, nil
		}
	}

	return correctCount == selectedCorrectCount && len(selectedMap) == correctCount, nil
}

// gradeFillBlankText grades fill-in-the-blank text questions
func (s *QuizService) gradeFillBlankText(ctx context.Context, answerData map[string]interface{}, questionID int64) (bool, error) {
	blanksData, ok := answerData["blanks"].([]interface{})
	if !ok {
		return false, fmt.Errorf("invalid answer format")
	}

	correctAnswers, err := s.quizRepo.ListCorrectAnswers(ctx, questionID)
	if err != nil {
		return false, err
	}

	// Build map of correct answers by blank_id
	correctMap := make(map[int][]models.QuizCorrectAnswer)
	for _, ca := range correctAnswers {
		if ca.BlankID.Valid {
			blankID := int(ca.BlankID.Int32)
			correctMap[blankID] = append(correctMap[blankID], ca)
		}
	}

	// Check each student answer
	for _, blank := range blanksData {
		blankMap, ok := blank.(map[string]interface{})
		if !ok {
			continue
		}

		blankID := int(blankMap["blank_id"].(float64))
		studentAnswer := strings.TrimSpace(blankMap["answer"].(string))

		correctOptions := correctMap[blankID]
		if len(correctOptions) == 0 {
			return false, nil
		}

		// Check if answer matches any correct option
		matched := false
		for _, correct := range correctOptions {
			if !correct.AnswerText.Valid {
				continue
			}

			correctText := correct.AnswerText.String
			if !correct.CaseSensitive {
				correctText = strings.ToLower(correctText)
				studentAnswer = strings.ToLower(studentAnswer)
			}

			if correct.ExactMatch {
				if studentAnswer == correctText {
					matched = true
					break
				}
			} else {
				// Partial match - contains the correct answer
				if strings.Contains(studentAnswer, correctText) {
					matched = true
					break
				}
			}
		}

		if !matched {
			return false, nil
		}
	}

	return true, nil
}

// gradeFillBlankDropdown grades fill-in-the-blank dropdown questions
func (s *QuizService) gradeFillBlankDropdown(ctx context.Context, answerData map[string]interface{}, questionID int64) (bool, error) {
	blanksData, ok := answerData["blanks"].([]interface{})
	if !ok {
		return false, fmt.Errorf("invalid answer format")
	}

	options, err := s.quizRepo.ListAnswerOptions(ctx, questionID)
	if err != nil {
		return false, err
	}

	// Build map of correct options by blank_id
	correctMap := make(map[int]int64) // blank_id -> correct option_id
	for _, opt := range options {
		if opt.IsCorrect && opt.BlankID.Valid {
			correctMap[int(opt.BlankID.Int32)] = opt.ID
		}
	}

	// Check each student selection
	for _, blank := range blanksData {
		blankMap, ok := blank.(map[string]interface{})
		if !ok {
			continue
		}

		blankID := int(blankMap["blank_id"].(float64))
		selectedOptionID := int64(blankMap["selected_option_id"].(float64))

		correctOptionID, exists := correctMap[blankID]
		if !exists || correctOptionID != selectedOptionID {
			return false, nil
		}
	}

	return true, nil
}

// ============================================
// SCORE CALCULATION
// ============================================

// calculateAttemptScore calculates total score for an attempt
func (s *QuizService) calculateAttemptScore(ctx context.Context, attempt *models.QuizAttempt, quiz *models.Quiz) error {
	answers, err := s.quizRepo.ListAttemptAnswers(ctx, attempt.ID)
	if err != nil {
		return err
	}

	var totalPoints float64 = 0
	var earnedPoints float64 = 0
	allAnswersGraded := true

	for _, ans := range answers {
		question, err := s.quizRepo.GetQuestion(ctx, ans.QuestionID)
		if err != nil {
			continue
		}

		totalPoints += question.Points

		if ans.PointsEarned.Valid {
			earnedPoints += ans.PointsEarned.Float64
		} else {
			// Check if this is a question type that requires manual grading
			if question.QuestionType == models.QuestionTypeEssay ||
				question.QuestionType == models.QuestionTypeFileUpload ||
				question.QuestionType == models.QuestionTypeShortAnswer {
				allAnswersGraded = false
			}
		}
	}

	percentage := 0.0
	if totalPoints > 0 {
		percentage = (earnedPoints / totalPoints) * 100
	}

	isPassed := false
	if quiz.PassingScore.Valid {
		isPassed = percentage >= quiz.PassingScore.Float64
	}

	attempt.TotalPoints = sql.NullFloat64{Float64: totalPoints, Valid: true}
	attempt.EarnedPoints = sql.NullFloat64{Float64: earnedPoints, Valid: true}
	attempt.Percentage = sql.NullFloat64{Float64: percentage, Valid: true}
	attempt.IsPassed = sql.NullBool{Bool: isPassed, Valid: true}
	
	// Only mark as GRADED if all manual-grading questions have been graded
	if allAnswersGraded {
		attempt.Status = models.AttemptStatusGraded
	} else {
		attempt.Status = models.AttemptStatusSubmitted
	}

	return nil
}

// checkAllAnswersGraded checks if all answers for an attempt are graded
func (s *QuizService) checkAllAnswersGraded(ctx context.Context, attemptID int64) (bool, error) {
	answers, err := s.quizRepo.ListAttemptAnswers(ctx, attemptID)
	if err != nil {
		return false, err
	}

	for _, ans := range answers {
		if !ans.PointsEarned.Valid {
			return false, nil
		}
	}

	return true, nil
}

// ============================================
// VALIDATION FUNCTIONS
// ============================================

// validateQuestionRequest validates question creation request
func (s *QuizService) validateQuestionRequest(req *dto.CreateQuestionRequest) error {
	switch req.QuestionType {
	case dto.QuestionTypeSingleChoice, dto.QuestionTypeMultipleChoice:
		if len(req.AnswerOptions) < 2 {
			return fmt.Errorf("choice questions must have at least 2 options")
		}
		hasCorrect := false
		for _, opt := range req.AnswerOptions {
			if opt.IsCorrect {
				hasCorrect = true
				break
			}
		}
		if !hasCorrect {
			return fmt.Errorf("choice questions must have at least one correct answer")
		}

	case dto.QuestionTypeFillBlankText, dto.QuestionTypeFillBlankDropdown:
		if len(req.CorrectAnswers) == 0 && len(req.AnswerOptions) == 0 {
			return fmt.Errorf("fill-in-the-blank questions must have correct answers or options")
		}

	case dto.QuestionTypeShortAnswer:
		if settings, ok := req.Settings["max_words"]; ok {
			if maxWords, ok := settings.(float64); ok && maxWords <= 0 {
				return fmt.Errorf("max_words must be positive")
			}
		}

	case dto.QuestionTypeFileUpload:
		if settings, ok := req.Settings["max_size_mb"]; ok {
			if maxSize, ok := settings.(float64); ok && maxSize <= 0 {
				return fmt.Errorf("max_size_mb must be positive")
			}
		}
	}

	return nil
}

// validateAnswerData validates answer data format
func (s *QuizService) validateAnswerData(questionType string, answerData map[string]interface{}) error {
	switch questionType {
	case models.QuestionTypeSingleChoice:
		if _, ok := answerData["selected_option_id"]; !ok {
			return fmt.Errorf("single choice answer must have selected_option_id")
		}

	case models.QuestionTypeMultipleChoice:
		if _, ok := answerData["selected_option_ids"]; !ok {
			return fmt.Errorf("multiple choice answer must have selected_option_ids")
		}

	case models.QuestionTypeShortAnswer, models.QuestionTypeEssay:
		if _, ok := answerData["answer_text"]; !ok {
			return fmt.Errorf("text answer must have text field")
		}

	case models.QuestionTypeFileUpload:
		if _, ok := answerData["file_path"]; !ok {
			return fmt.Errorf("file upload answer must have file_path")
		}

	case models.QuestionTypeFillBlankText, models.QuestionTypeFillBlankDropdown:
		if _, ok := answerData["blanks"]; !ok {
			return fmt.Errorf("fill-in-the-blank answer must have blanks field")
		}
	}

	return nil
}

// verifyQuizOwnership verifies user owns the quiz (or is admin)
func (s *QuizService) verifyQuizOwnership(ctx context.Context, quizID, userID int64, userRole string) error {
	if userRole == "ADMIN" {
		return nil
	}

	// Get quiz to find content
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return err
	}

	// Get content to find section
	content, err := s.courseRepo.GetContentByID(ctx, quiz.ContentID)
	if err != nil {
		return err
	}

	// Get section to find course
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return err
	}

	// Get course to check owner
	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return err
	}

	if course.CreatedBy != userID {
		return fmt.Errorf("permission denied: you don't own this quiz")
	}

	return nil
}

// buildQuizResponse builds quiz response from model
func (s *QuizService) buildQuizResponse(quiz *models.Quiz) *dto.QuizResponse {
	return &dto.QuizResponse{
		ID:                     quiz.ID,
		ContentID:              quiz.ContentID,
		Title:                  quiz.Title,
		Description:            fromNullString(quiz.Description),
		Instructions:           fromNullString(quiz.Instructions),
		TimeLimitMinutes:       fromNullInt32Ptr(quiz.TimeLimitMinutes),
		AvailableFrom:          fromNullTimePtr(quiz.AvailableFrom),
		AvailableUntil:         fromNullTimePtr(quiz.AvailableUntil),
		MaxAttempts:            fromNullInt32Ptr(quiz.MaxAttempts),
		ShuffleQuestions:       quiz.ShuffleQuestions,
		ShuffleAnswers:         quiz.ShuffleAnswers,
		PassingScore:           fromNullFloat64Ptr(quiz.PassingScore),
		TotalPoints:            quiz.TotalPoints,
		AutoGrade:              quiz.AutoGrade,
		ShowResultsImmediately: quiz.ShowResultsImmediately,
		ShowCorrectAnswers:     quiz.ShowCorrectAnswers,
		AllowReview:            quiz.AllowReview,
		ShowFeedback:           quiz.ShowFeedback,
		IsPublished:            quiz.IsPublished,
		CreatedBy:              quiz.CreatedBy,
		CreatedAt:              quiz.CreatedAt,
		UpdatedAt:              quiz.UpdatedAt,
	}
}

// buildQuizResponseWithStats builds quiz response with statistics
func (s *QuizService) buildQuizResponseWithStats(quiz *models.QuizWithStats) *dto.QuizResponse {
	response := s.buildQuizResponse(&quiz.Quiz)
	response.CreatorName = quiz.CreatorName
	response.CreatorEmail = quiz.CreatorEmail
	response.QuestionCount = quiz.QuestionCount
	response.AttemptCount = quiz.AttemptCount
	response.StudentCount = quiz.StudentCount
	if quiz.AverageScore.Valid {
		avgScore := quiz.AverageScore.Float64
		response.AverageScore = &avgScore
	}
	return response
}

// buildQuestionResponse builds question response for teachers
func (s *QuizService) buildQuestionResponse(q *models.QuestionWithOptions) *dto.QuestionResponse {
	var settings map[string]interface{}
	_ = json.Unmarshal(q.Settings, &settings)

	response := &dto.QuestionResponse{
		ID:           q.ID,
		QuizID:       q.QuizID,
		QuestionType: dto.QuestionType(q.QuestionType),
		QuestionText: q.QuestionText,
		QuestionHTML: fromNullString(q.QuestionHTML),
		Explanation:  fromNullString(q.Explanation),
		Points:       q.Points,
		OrderIndex:   q.OrderIndex,
		Settings:     settings,
		Images:        extractImagesFromSettings(q.Settings),
		IsRequired:   q.IsRequired,
		CreatedAt:    q.CreatedAt,
		UpdatedAt:    q.UpdatedAt,
	}

	// Add answer options
	for _, opt := range q.AnswerOptions {
		response.AnswerOptions = append(response.AnswerOptions, dto.AnswerOptionResponse{
			ID:          opt.ID,
			QuestionID:  opt.QuestionID,
			OptionText:  opt.OptionText,
			OptionHTML:  fromNullString(opt.OptionHTML),
			IsCorrect:   opt.IsCorrect,
			OrderIndex:  opt.OrderIndex,
			BlankID:     fromNullInt32Ptr(opt.BlankID),
			CreatedAt:   opt.CreatedAt,
		})
	}

	// Add correct answers
	for _, ca := range q.CorrectAnswers {
		response.CorrectAnswers = append(response.CorrectAnswers, dto.CorrectAnswerResponse{
			ID:            ca.ID,
			QuestionID:    ca.QuestionID,
			AnswerText:    fromNullString(ca.AnswerText),
			BlankID:       fromNullInt32Ptr(ca.BlankID),
			BlankPosition: fromNullInt32Ptr(ca.BlankPosition),
			CaseSensitive: ca.CaseSensitive,
			ExactMatch:    ca.ExactMatch,
			CreatedAt:     ca.CreatedAt,
		})
	}

	return response
}

// buildStudentQuestionResponse builds question response for students (hides correct answers)
func (s *QuizService) buildStudentQuestionResponse(q *models.QuestionWithOptions) *dto.StudentQuestionResponse {
	var settings map[string]interface{}
	_ = json.Unmarshal(q.Settings, &settings)

	response := &dto.StudentQuestionResponse{
		ID:           q.ID,
		QuizID:       q.QuizID,
		QuestionType: dto.QuestionType(q.QuestionType),
		QuestionText: q.QuestionText,
		QuestionHTML: fromNullString(q.QuestionHTML),
		Points:       q.Points,
		OrderIndex:   q.OrderIndex,
		Settings:     settings,
		Images:       extractImagesFromSettings(q.Settings),
		IsRequired:   q.IsRequired,
	}

	// Add answer options without correct flag
	for _, opt := range q.AnswerOptions {
		response.AnswerOptions = append(response.AnswerOptions, dto.StudentAnswerOptionResponse{
			ID:          opt.ID,
			QuestionID:  opt.QuestionID,
			OptionText:  opt.OptionText,
			OptionHTML:  fromNullString(opt.OptionHTML),
			OrderIndex:  opt.OrderIndex,
			BlankID:     fromNullInt32Ptr(opt.BlankID),
		})
	}

	return response
}

// buildAttemptResponse builds attempt response
func (s *QuizService) buildAttemptResponse(attempt *models.QuizAttempt) *dto.QuizAttemptResponse {
	return &dto.QuizAttemptResponse{
		ID:               attempt.ID,
		QuizID:           attempt.QuizID,
		StudentID:        attempt.StudentID,
		AttemptNumber:    attempt.AttemptNumber,
		StartedAt:        attempt.StartedAt,
		SubmittedAt:      fromNullTimePtr(attempt.SubmittedAt),
		TimeSpentSeconds: fromNullInt32Ptr(attempt.TimeSpentSeconds),
		TotalPoints:      fromNullFloat64Ptr(attempt.TotalPoints),
		EarnedPoints:     fromNullFloat64Ptr(attempt.EarnedPoints),
		Percentage:       fromNullFloat64Ptr(attempt.Percentage),
		IsPassed:         fromNullBoolPtr(attempt.IsPassed),
		Status:           attempt.Status,
		CreatedAt:        attempt.CreatedAt,
		UpdatedAt:        attempt.UpdatedAt,
	}
}

// buildStudentAnswerResponse builds student answer response
func (s *QuizService) buildStudentAnswerResponse(answer *models.QuizStudentAnswer) *dto.StudentAnswerResponse {
	var answerData map[string]interface{}
	_ = json.Unmarshal(answer.AnswerData, &answerData)

	return &dto.StudentAnswerResponse{
		ID:               answer.ID,
		AttemptID:        answer.AttemptID,
		QuestionID:       answer.QuestionID,
		AnswerData:       answerData,
		PointsEarned:     fromNullFloat64Ptr(answer.PointsEarned),
		IsCorrect:        fromNullBoolPtr(answer.IsCorrect),
		GraderFeedback:   fromNullString(answer.GraderFeedback),
		GradedBy:         fromNullInt64Ptr(answer.GradedBy),
		GradedAt:         fromNullTimePtr(answer.GradedAt),
		AnsweredAt:       answer.AnsweredAt,
		TimeSpentSeconds: fromNullInt32Ptr(answer.TimeSpentSeconds),
	}
}

// buildQuizResultResponse builds complete quiz result
func (s *QuizService) buildQuizResultResponse(ctx context.Context, attempt *models.QuizAttempt, quiz *models.Quiz) (*dto.QuizResultResponse, error) {
	// Get questions
	questions, err := s.quizRepo.ListQuestionsWithOptions(ctx, quiz.ID)
	if err != nil {
		return nil, err
	}

	// Get student answers
	answers, err := s.quizRepo.ListAttemptAnswers(ctx, attempt.ID)
	if err != nil {
		return nil, err
	}

	response := &dto.QuizResultResponse{
		Attempt:            *s.buildAttemptResponse(attempt),
		Quiz:               *s.buildQuizResponse(quiz),
		ShowCorrectAnswers: quiz.ShowCorrectAnswers,
		AllowReview:        quiz.AllowReview,
	}

	// Add questions (with or without correct answers based on settings)
	if quiz.ShowCorrectAnswers {
		for _, q := range questions {
			response.Questions = append(response.Questions, *s.buildQuestionResponse(&q))
		}
	}

	// Add student answers
	for _, ans := range answers {
		response.StudentAnswers = append(response.StudentAnswers, *s.buildStudentAnswerResponse(&ans))
	}

	return response, nil
}

// buildQuizReviewResponse builds quiz review response
func (s *QuizService) buildQuizReviewResponse(ctx context.Context, attempt *models.QuizAttempt, quiz *models.Quiz) (*dto.QuizReviewResponse, error) {
	questions, err := s.quizRepo.ListQuestionsWithOptions(ctx, quiz.ID)
	if err != nil {
		return nil, err
	}

	answers, err := s.quizRepo.ListAttemptAnswers(ctx, attempt.ID)
	if err != nil {
		return nil, err
	}

	// Build answer map for quick lookup
	answerMap := make(map[int64]*models.QuizStudentAnswer)
	for i := range answers {
		answerMap[answers[i].QuestionID] = &answers[i]
	}

	response := &dto.QuizReviewResponse{
		Attempt:            *s.buildAttemptResponse(attempt),
		Quiz:               *s.buildQuizResponse(quiz),
		ShowCorrectAnswers: quiz.ShowCorrectAnswers,
		ShowFeedback:       quiz.ShowFeedback,
	}

	// Combine questions with student answers
	for _, q := range questions {
		questionResp := s.buildQuestionResponse(&q)
		var studentAnswer *dto.StudentAnswerResponse
		
		if ans, exists := answerMap[q.ID]; exists {
			studentAnswer = s.buildStudentAnswerResponse(ans)
		}

		response.QuestionsWithAnswers = append(response.QuestionsWithAnswers, dto.QuestionWithAnswerResponse{
			Question:      *questionResp,
			StudentAnswer: studentAnswer,
		})
	}

	return response, nil
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

// Null type conversion helpers
func toNullString(s string) sql.NullString {
	return sql.NullString{String: s, Valid: s != ""}
}

func fromNullString(ns sql.NullString) string {
	if ns.Valid {
		return ns.String
	}
	return ""
}

func toNullInt32(i *int) sql.NullInt32 {
	if i == nil {
		return sql.NullInt32{Valid: false}
	}
	return sql.NullInt32{Int32: int32(*i), Valid: true}
}

func fromNullInt32Ptr(ni sql.NullInt32) *int {
	if ni.Valid {
		val := int(ni.Int32)
		return &val
	}
	return nil
}

func toNullInt64(i *int64) sql.NullInt64 {
	if i == nil {
		return sql.NullInt64{Valid: false}
	}
	return sql.NullInt64{Int64: *i, Valid: true}
}

func fromNullInt64Ptr(ni sql.NullInt64) *int64 {
	if ni.Valid {
		return &ni.Int64
	}
	return nil
}

func toNullFloat64(f *float64) sql.NullFloat64 {
	if f == nil {
		return sql.NullFloat64{Valid: false}
	}
	return sql.NullFloat64{Float64: *f, Valid: true}
}

func fromNullFloat64Ptr(nf sql.NullFloat64) *float64 {
	if nf.Valid {
		return &nf.Float64
	}
	return nil
}

func toNullTime(t *time.Time) sql.NullTime {
	if t == nil {
		return sql.NullTime{Valid: false}
	}
	return sql.NullTime{Time: *t, Valid: true}
}

func fromNullTimePtr(nt sql.NullTime) *time.Time {
	if nt.Valid {
		return &nt.Time
	}
	return nil
}

func fromNullBoolPtr(nb sql.NullBool) *bool {
	if nb.Valid {
		return &nb.Bool
	}
	return nil
}

// GetQuizByContentID gets quiz by content ID
func (s *QuizService) GetQuizByContentID(ctx context.Context, contentID int64, userID int64, userRole string) (*dto.QuizResponse, error) {
	// Get the content first to verify access
	content, err := s.courseRepo.GetContentByID(ctx, contentID)
	if err != nil {
		return nil, fmt.Errorf("content not found")
	}

	// Get section and course to verify ownership
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return nil, fmt.Errorf("section not found")
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("course not found")
	}

	// Check permission (owner or admin)
	// For students: they can view quiz if it's published and they're enrolled
	// But we'll let the handler/frontend handle enrollment checks for simplicity
	if userRole != "ADMIN" && course.CreatedBy != userID {
		// Could add enrollment check here if needed, but requires adding enrollmentRepo to QuizService
		// For now, assume if quiz is published, anyone can view the basic info
		// The actual quiz taking will be restricted by enrollment in other endpoints
	}

	// Get quiz
	quiz, err := s.quizRepo.GetQuizByContentID(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("quiz not found")
		}
		return nil, fmt.Errorf("failed to get quiz: %w", err)
	}

	// Get quiz with stats
	quizWithStats, err := s.quizRepo.GetQuizWithStats(ctx, quiz.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get quiz stats: %w", err)
	}

	return s.buildQuizResponseWithStats(quizWithStats), nil
}