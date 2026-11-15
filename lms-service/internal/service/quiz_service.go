package service

import (
	"context"
	"encoding/json"
	"fmt"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
)

type QuizService struct {
	quizRepo     *repository.QuizRepository
	courseRepo   *repository.CourseRepository
	userRepo     *repository.UserRepository
	progressRepo *repository.ProgressRepository
	aiClient     *ai.Client
	// Optional: mirrors created questions into the course question bank.
	bankRepo    *repository.QuestionBankRepository
	gradingData map[int64]models.QuestionWithOptions
}

func NewQuizService(
	quizRepo *repository.QuizRepository,
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
	progressRepo *repository.ProgressRepository,
	aiClient *ai.Client,
	bankRepo *repository.QuestionBankRepository,
) *QuizService {
	return &QuizService{
		quizRepo:     quizRepo,
		courseRepo:   courseRepo,
		userRepo:     userRepo,
		progressRepo: progressRepo,
		aiClient:     aiClient,
		bankRepo:     bankRepo,
	}
}

// GetQuestionImage gets a specific image from a question
func (s *QuizService) GetQuestionImage(ctx context.Context, questionID int64, imageID string, userID int64, userRole string) (*dto.QuestionImage, error) {
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

// verifyQuizOwnership verifies user owns the quiz, is a co-teacher, or is admin
func (s *QuizService) verifyQuizOwnership(ctx context.Context, quizID, userID int64, role string) error {
	manager, err := (QuizPolicy{s.quizRepo}).Check(ctx, quizID, userID, role)
	if err != nil {
		return err
	}
	if !manager {
		return ErrQuizAccess
	}
	return nil
}

// ============================================
// UTILITY FUNCTIONS
// ============================================
