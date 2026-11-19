package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/logger"
)

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

	// Check permission (owner, co-teacher, or admin)
	if userRole != "ADMIN" && course.CreatedBy != createdBy {
		isCoTeacher, err := s.courseRepo.IsCoTeacher(ctx, course.ID, createdBy)
		if err != nil || !isCoTeacher {
			return nil, fmt.Errorf("permission denied: you don't own this course")
		}
	}

	// Create quiz model
	quiz := &models.Quiz{
		ContentID:              req.ContentID,
		Title:                  req.Title,
		Description:            toNullString(req.Description),
		Instructions:           toNullString(req.Instructions),
		TimeLimitMinutes:       toNullInt32(req.TimeLimitMinutes),
		AvailableFrom:          toNullTime(req.AvailableFrom),
		AvailableUntil:         toNullTime(req.AvailableUntil),
		MaxAttempts:            toNullInt32(req.MaxAttempts),
		ShuffleQuestions:       req.ShuffleQuestions,
		ShuffleAnswers:         req.ShuffleAnswers,
		PassingScore:           toNullFloat64(req.PassingScore),
		TotalPoints:            req.TotalPoints,
		AutoGrade:              req.AutoGrade,
		ShowResultsImmediately: req.ShowResultsImmediately,
		ShowCorrectAnswers:     req.ShowCorrectAnswers,
		AllowReview:            req.AllowReview,
		ShowFeedback:           req.ShowFeedback,
		IsPublished:            true, // Learning resources are published immediately.
		CreatedBy:              createdBy,
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
	quiz.IsPublished = true

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

	if _, err := s.authorizeQuizRead(ctx, &quiz.Quiz, userID, userRole); err != nil {
		return nil, err
	}

	response := s.buildQuizResponseWithStats(quiz)
	return response, nil
}

// CreateQuestion creates a new question with options/answers
func (s *QuizService) CreateQuestion(ctx context.Context, req *dto.CreateQuestionRequest, userID int64, userRole string) (*dto.QuestionResponse, error) {
	// Verify quiz ownership
	if err := s.verifyQuizOwnership(ctx, req.QuizID, userID, userRole); err != nil {
		return nil, err
	}

	aggregate, err := s.prepareQuestion(req)
	if err != nil {
		return nil, err
	}
	question := &aggregate.QuizQuestion
	options, answers := aggregate.AnswerOptions, aggregate.CorrectAnswers

	if err := s.quizRepo.CreateQuestionWithAnswers(ctx, question, options, answers); err != nil {
		return nil, err
	}

	// Mirroring remains best-effort but has no unbounded background goroutine.
	if err := s.mirrorQuestionToBank(ctx, req, userID); err != nil {
		logger.Error("Question bank mirror failed", err)
	}

	// Retrieve complete question
	questionWithOptions, err := s.quizRepo.GetQuestionWithOptions(ctx, question.ID)
	if err != nil {
		return nil, err
	}

	return s.buildQuestionResponse(questionWithOptions), nil
}

// prepareQuestion validates and maps input without database work.
func (s *QuizService) prepareQuestion(req *dto.CreateQuestionRequest) (*models.QuestionWithOptions, error) {
	// Validate question type and requirements
	if err := s.validateQuestionRequest(req); err != nil {
		return nil, err
	}

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

	options := make([]models.QuizAnswerOption, 0, len(req.AnswerOptions))
	answers := make([]models.QuizCorrectAnswer, 0, len(req.CorrectAnswers))

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
			options = append(options, *option)
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
			answers = append(answers, *answer)
		}
	}

	return &models.QuestionWithOptions{QuizQuestion: *question, AnswerOptions: options, CorrectAnswers: answers}, nil
}

// mirrorQuestionToBank mirrors a committed question using the caller deadline.
func (s *QuizService) mirrorQuestionToBank(ctx context.Context, req *dto.CreateQuestionRequest, userID int64) error {
	if s.bankRepo == nil {
		return nil
	}
	courseID, err := s.quizRepo.GetQuizCourseID(ctx, req.QuizID)
	if err != nil {
		return err
	}
	return s.mirrorQuestionToBankForCourse(ctx, req, userID, courseID)
}

func (s *QuizService) mirrorQuestionToBankForCourse(ctx context.Context, req *dto.CreateQuestionRequest, userID, courseID int64) error {
	options, err := json.Marshal(req.AnswerOptions)
	if err != nil {
		return err
	}
	answers, err := json.Marshal(req.CorrectAnswers)
	if err != nil {
		return err
	}
	settings := []byte(`{}`)
	if req.Settings != nil {
		settings, err = json.Marshal(req.Settings)
		if err != nil {
			return err
		}
	}
	_, err = s.bankRepo.UpsertFromQuizQuestion(ctx, repository.QuizQuestionSync{CourseID: courseID, QuizID: req.QuizID, QuestionType: string(req.QuestionType), QuestionText: strings.TrimSpace(req.QuestionText), Explanation: toNullString(req.Explanation), Points: req.Points, Settings: settings, OptionsJSON: options, CorrectJSON: answers, CreatedBy: userID})
	return err
}

// BatchCreateQuestions creates multiple questions in a single request
func (s *QuizService) BatchCreateQuestions(ctx context.Context, quizID int64, reqs []dto.CreateQuestionRequest, userID int64, userRole string) ([]*dto.QuestionResponse, error) {
	if len(reqs) == 0 || len(reqs) > 100 {
		return nil, fmt.Errorf("question batch must contain 1 to 100 items")
	}

	// Verify quiz ownership once for the batch
	if err := s.verifyQuizOwnership(ctx, quizID, userID, userRole); err != nil {
		return nil, err
	}

	questions := make([]*models.QuestionWithOptions, len(reqs))
	for i := range reqs {
		reqs[i].QuizID = quizID
		question, err := s.prepareQuestion(&reqs[i])
		if err != nil {
			return nil, fmt.Errorf("invalid question at index %d: %w", i, err)
		}
		questions[i] = question
	}
	if err := s.quizRepo.CreateQuestionsWithAnswers(ctx, questions); err != nil {
		return nil, err
	}

	// Optional mirroring stays best-effort, with one course lookup for the batch.
	if s.bankRepo != nil && ctx.Err() == nil {
		courseID, err := s.quizRepo.GetQuizCourseID(ctx, quizID)
		if err != nil {
			logger.Error("Question bank batch course lookup failed", err)
		} else {
			for i := range reqs {
				if ctx.Err() != nil {
					break
				}
				if err := s.mirrorQuestionToBankForCourse(ctx, &reqs[i], userID, courseID); err != nil {
					logger.Error("Question bank mirror failed", err)
				}
			}
		}
	}
	createdQuestions := make([]*dto.QuestionResponse, len(questions))
	for i, question := range questions {
		createdQuestions[i] = s.buildQuestionResponse(question)
	}
	return createdQuestions, nil
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
	if req.IsRequired != nil {
		question.IsRequired = *req.IsRequired
	}

	if err := s.quizRepo.UpdateQuestionWithAnswers(ctx, question, req.AnswerOptions, req.CorrectAnswers); err != nil {
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

	manager, err := s.authorizeQuizRead(ctx, quiz, userID, userRole)
	if err != nil {
		return nil, err
	}

	questions, err := s.quizRepo.ListQuestionsWithOptions(ctx, quizID)
	if err != nil {
		return nil, err
	}

	// Build response based on role
	var result []interface{}
	for _, q := range questions {
		if !manager || !includeCorrectAnswers {
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

// ListQuestionImages lists all images for a question
func (s *QuizService) ListQuestionImages(ctx context.Context, questionID int64, userID int64, userRole string) ([]dto.QuestionImage, error) {
	question, err := s.quizRepo.GetQuestion(ctx, questionID)
	if err != nil {
		return nil, fmt.Errorf("question not found: %w", err)
	}

	quiz, err := s.quizRepo.GetQuiz(ctx, question.QuizID)
	if err != nil {
		return nil, err
	}
	if _, err := s.authorizeQuizRead(ctx, quiz, userID, userRole); err != nil {
		return nil, err
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

// GetQuizByContentID gets quiz by content ID
func (s *QuizService) GetQuizByContentID(ctx context.Context, contentID int64, userID int64, userRole string) (*dto.QuizResponse, error) {
	// Get quiz
	quiz, err := s.quizRepo.GetQuizByContentID(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows || strings.Contains(err.Error(), "quiz not found") {
			return nil, fmt.Errorf("quiz not found")
		}
		return nil, fmt.Errorf("failed to get quiz: %w", err)
	}

	return s.GetQuiz(ctx, quiz.ID, userID, userRole)
}

// GetFocusReport authorizes the course teacher before returning bounded browser aggregates.
func (s *QuizService) GetFocusReport(ctx context.Context, quizID, userID int64, role string) ([]dto.QuizFocusReportRow, error) {
	if err := s.verifyQuizOwnership(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	return s.quizRepo.GetFocusReport(ctx, quizID)
}

func (s *QuizService) AuthorizeQuestionManagement(ctx context.Context, id, userID int64, role string) error {
	question, err := s.quizRepo.GetQuestion(ctx, id)
	if err != nil {
		return err
	}
	return s.verifyQuizOwnership(ctx, question.QuizID, userID, role)
}
