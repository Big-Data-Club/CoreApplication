package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

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
		Images:       extractImagesFromSettings(q.Settings),
		IsRequired:   q.IsRequired,
		CreatedAt:    q.CreatedAt,
		UpdatedAt:    q.UpdatedAt,
	}

	// Add answer options
	for _, opt := range q.AnswerOptions {
		response.AnswerOptions = append(response.AnswerOptions, dto.AnswerOptionResponse{
			ID:         opt.ID,
			QuestionID: opt.QuestionID,
			OptionText: opt.OptionText,
			OptionHTML: fromNullString(opt.OptionHTML),
			IsCorrect:  opt.IsCorrect,
			OrderIndex: opt.OrderIndex,
			BlankID:    fromNullInt32Ptr(opt.BlankID),
			CreatedAt:  opt.CreatedAt,
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
			ID:         opt.ID,
			QuestionID: opt.QuestionID,
			OptionText: opt.OptionText,
			OptionHTML: fromNullString(opt.OptionHTML),
			OrderIndex: opt.OrderIndex,
			BlankID:    fromNullInt32Ptr(opt.BlankID),
		})
	}

	return response
}

// buildAttemptResponse builds attempt response
func (s *QuizService) buildAttemptResponse(attempt *models.QuizAttempt) *dto.QuizAttemptResponse {
	return &dto.QuizAttemptResponse{
		FocusSummary:     attempt.FocusSummary,
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
		if !quiz.ShowCorrectAnswers {
			questionResp.CorrectAnswers = nil
			questionResp.Explanation = ""
			for i := range questionResp.AnswerOptions {
				questionResp.AnswerOptions[i].IsCorrect = false
			}
		}

		var studentAnswer *dto.StudentAnswerResponse

		if ans, exists := answerMap[q.ID]; exists {
			studentAnswer = s.buildStudentAnswerResponse(ans)
			if !quiz.ShowFeedback {
				studentAnswer.GraderFeedback = ""
			}
		}

		response.QuestionsWithAnswers = append(response.QuestionsWithAnswers, dto.QuestionWithAnswerResponse{
			Question:      *questionResp,
			StudentAnswer: studentAnswer,
		})
	}

	return response, nil
}

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
