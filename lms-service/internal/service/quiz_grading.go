package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/pkg/logger"
)

// GradeAnswer manually grades a student answer
func (s *QuizService) gradeAnswer(ctx context.Context, req *dto.GradeAnswerRequest, graderID int64, userRole string) error {
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

	if attempt.Status == models.AttemptStatusInProgress {
		return fmt.Errorf("attempt is not submitted")
	}
	// Get question to validate points
	question, err := s.quizRepo.GetQuestion(ctx, answer.QuestionID)
	if err != nil {
		return err
	}

	if req.PointsEarned < 0 || req.PointsEarned > question.Points {
		return fmt.Errorf("points earned cannot exceed question points")
	}

	scoreChanged := !answer.PointsEarned.Valid || answer.PointsEarned.Float64 != req.PointsEarned
	if !scoreChanged && answer.GraderFeedback.String == req.GraderFeedback && answer.GradedBy.Valid && answer.GradedBy.Int64 == graderID {
		return nil
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

	if scoreChanged {
		return s.quizRepo.RefreshAttemptEffects(ctx, attempt.ID)
	}
	return nil
}

// BulkGrade grades multiple answers at once
func (s *QuizService) BulkGrade(ctx context.Context, req *dto.BulkGradeRequest, graderID int64, userRole string) *dto.BulkGradeResponse {
	type groupedGrade struct {
		grade     dto.GradeAnswerRequest
		attemptID int64
	}

	grouped := make(map[int64][]dto.GradeAnswerRequest)
	var lookupMu sync.Mutex

	lookupG, lookupCtx := errgroup.WithContext(ctx)
	lookupG.SetLimit(10)

	for i := range req.Grades {
		grade := req.Grades[i]
		lookupG.Go(func() error {
			ans, err := s.quizRepo.GetStudentAnswer(lookupCtx, grade.AnswerID)
			if err != nil {
				return nil
			}
			lookupMu.Lock()
			grouped[ans.AttemptID] = append(grouped[ans.AttemptID], grade)
			lookupMu.Unlock()
			return nil
		})
	}
	lookupG.Wait()

	response := &dto.BulkGradeResponse{
		Succeeded: make([]int64, 0, len(req.Grades)),
		Failed:    make([]dto.GradeError, 0),
	}

	resolvedSet := make(map[int64]struct{})
	for _, grades := range grouped {
		for _, g := range grades {
			resolvedSet[g.AnswerID] = struct{}{}
		}
	}
	for _, g := range req.Grades {
		if _, ok := resolvedSet[g.AnswerID]; !ok {
			response.Failed = append(response.Failed, dto.GradeError{
				AnswerID: g.AnswerID,
				Error:    "answer not found",
			})
		}
	}

	type perAttemptResult struct {
		succeeded []int64
		failed    []dto.GradeError
	}

	attemptIDs := make([]int64, 0, len(grouped))
	for id := range grouped {
		attemptIDs = append(attemptIDs, id)
	}

	results := make([]perAttemptResult, len(attemptIDs))

	gradeG, gradeCtx := errgroup.WithContext(ctx)
	gradeG.SetLimit(5)

	for idx, aID := range attemptIDs {
		idx, aID := idx, aID
		grades := grouped[aID]

		gradeG.Go(func() error {
			var succeeded []int64
			var failed []dto.GradeError

			for i := range grades {
				if err := s.GradeAnswer(gradeCtx, &grades[i], graderID, userRole); err != nil {
					logger.Error(
						fmt.Sprintf("BulkGrade: failed grading answer %d in attempt %d", grades[i].AnswerID, aID),
						err,
					)
					failed = append(failed, dto.GradeError{
						AnswerID: grades[i].AnswerID,
						Error:    err.Error(),
					})
				} else {
					succeeded = append(succeeded, grades[i].AnswerID)
				}
			}

			results[idx] = perAttemptResult{succeeded: succeeded, failed: failed}
			return nil
		})
	}
	gradeG.Wait()

	for _, r := range results {
		response.Succeeded = append(response.Succeeded, r.succeeded...)
		response.Failed = append(response.Failed, r.failed...)
	}

	return response
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
	var selectedID int64
	switch v := answerData["selected_option_id"].(type) {
	case float64:
		selectedID = int64(v)
	case int64:
		selectedID = v
	case int:
		selectedID = int64(v)
	default:
		return false, fmt.Errorf("invalid answer format: selected_option_id type %T", answerData["selected_option_id"])
	}

	options, err := s.gradingOptions(ctx, questionID)
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

	options, err := s.gradingOptions(ctx, questionID)
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

	correctAnswers, err := s.gradingCorrectAnswers(ctx, questionID)
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

	options, err := s.gradingOptions(ctx, questionID)
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

// calculateAttemptScore calculates total score for an attempt
func (s *QuizService) calculateAttemptScore(ctx context.Context, attempt *models.QuizAttempt, quiz *models.Quiz) error {
	answers, err := s.quizRepo.ListAttemptAnswers(ctx, attempt.ID)
	if err != nil {
		return err
	}

	// Calculate actual raw total points of all questions in the quiz
	allQuestions, err := s.quizRepo.ListQuestions(ctx, quiz.ID)
	if err != nil {
		return err
	}
	var quizTotalRawPoints float64 = 0
	for _, q := range allQuestions {
		quizTotalRawPoints += q.Points
	}

	// Collect all question IDs
	questionIDs := make([]int64, 0, len(answers))
	for _, ans := range answers {
		questionIDs = append(questionIDs, ans.QuestionID)
	}

	// Single batch query instead of N queries
	var questions []models.QuizQuestion
	if len(questionIDs) > 0 {
		questions, err = s.quizRepo.GetQuestionsByIDs(ctx, questionIDs)
		if err != nil {
			return err
		}
	}

	// Build lookup map
	questionMap := make(map[int64]*models.QuizQuestion, len(questions))
	for i := range questions {
		questionMap[questions[i].ID] = &questions[i]
	}

	var earnedRawPoints float64 = 0
	allAnswersGraded := true

	for _, ans := range answers {
		question, ok := questionMap[ans.QuestionID]
		if !ok {
			continue
		}

		if ans.PointsEarned.Valid {
			earnedRawPoints += ans.PointsEarned.Float64
		} else {
			// Check if this is a question type that requires manual grading
			if question.QuestionType == models.QuestionTypeEssay ||
				question.QuestionType == models.QuestionTypeFileUpload ||
				question.QuestionType == models.QuestionTypeShortAnswer {
				allAnswersGraded = false
			}
		}
	}

	// Determine final max total points and scale earned points
	finalTotalPoints := quiz.TotalPoints
	if finalTotalPoints <= 0 {
		finalTotalPoints = quizTotalRawPoints
	}

	scaledEarnedPoints := earnedRawPoints
	if quizTotalRawPoints > 0 && quiz.TotalPoints > 0 {
		scaledEarnedPoints = (earnedRawPoints / quizTotalRawPoints) * quiz.TotalPoints
	}

	percentage := 0.0
	if finalTotalPoints > 0 {
		percentage = (scaledEarnedPoints / finalTotalPoints) * 100
	} else if quizTotalRawPoints > 0 {
		percentage = (earnedRawPoints / quizTotalRawPoints) * 100
	}

	isPassed := false
	if quiz.PassingScore.Valid {
		isPassed = percentage >= quiz.PassingScore.Float64
	} else {
		isPassed = percentage > 0.0
	}

	attempt.TotalPoints = sql.NullFloat64{Float64: finalTotalPoints, Valid: true}
	attempt.EarnedPoints = sql.NullFloat64{Float64: scaledEarnedPoints, Valid: true}
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
