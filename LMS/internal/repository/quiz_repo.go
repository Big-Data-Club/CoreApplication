package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"example/hello/internal/models"
)

type QuizRepository struct {
	db *sql.DB
}

func NewQuizRepository(db *sql.DB) *QuizRepository {
	return &QuizRepository{db: db}
}

// ============================================
// QUIZ OPERATIONS
// ============================================

// CreateQuiz creates a new quiz
func (r *QuizRepository) CreateQuiz(ctx context.Context, quiz *models.Quiz) error {
	query := `
		INSERT INTO quizzes (
			content_id, title, description, instructions,
			time_limit_minutes, available_from, available_until,
			max_attempts, shuffle_questions, shuffle_answers,
			passing_score, total_points, auto_grade,
			show_results_immediately, show_correct_answers,
			allow_review, show_feedback, is_published, created_by
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19
		) RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		quiz.ContentID, quiz.Title, quiz.Description, quiz.Instructions,
		quiz.TimeLimitMinutes, quiz.AvailableFrom, quiz.AvailableUntil,
		quiz.MaxAttempts, quiz.ShuffleQuestions, quiz.ShuffleAnswers,
		quiz.PassingScore, quiz.TotalPoints, quiz.AutoGrade,
		quiz.ShowResultsImmediately, quiz.ShowCorrectAnswers,
		quiz.AllowReview, quiz.ShowFeedback, quiz.IsPublished, quiz.CreatedBy,
	).Scan(&quiz.ID, &quiz.CreatedAt, &quiz.UpdatedAt)

	return err
}

// GetQuiz retrieves quiz by ID
func (r *QuizRepository) GetQuiz(ctx context.Context, quizID int64) (*models.Quiz, error) {
	query := `SELECT * FROM quizzes WHERE id = $1`
	
	var quiz models.Quiz
	err := r.db.QueryRowContext(ctx, query, quizID).Scan(
		&quiz.ID,
		&quiz.ContentID,
		&quiz.Title,
		&quiz.Description,
		&quiz.Instructions,
		&quiz.TimeLimitMinutes,
		&quiz.AvailableFrom,
		&quiz.AvailableUntil,
		&quiz.MaxAttempts,
		&quiz.ShuffleQuestions,
		&quiz.ShuffleAnswers,
		&quiz.PassingScore,
		&quiz.TotalPoints,
		&quiz.AutoGrade,
		&quiz.ShowResultsImmediately,
		&quiz.ShowCorrectAnswers,
		&quiz.AllowReview,
		&quiz.ShowFeedback,
		&quiz.IsPublished,
		&quiz.CreatedBy,
		&quiz.CreatedAt,
		&quiz.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("quiz not found")
		}
		return nil, err
	}
	
	return &quiz, nil
}

// GetQuizWithStats retrieves quiz with statistics
func (r *QuizRepository) GetQuizWithStats(ctx context.Context, quizID int64) (*models.QuizWithStats, error) {
	query := `SELECT * FROM quiz_summary_view WHERE id = $1`
	
	var quiz models.QuizWithStats
	err := r.db.QueryRowContext(ctx, query, quizID).Scan(
		&quiz.ID,
		&quiz.ContentID,
		&quiz.Title,
		&quiz.Description,
		&quiz.Instructions,
		&quiz.TimeLimitMinutes,
		&quiz.AvailableFrom,
		&quiz.AvailableUntil,
		&quiz.MaxAttempts,
		&quiz.ShuffleQuestions,
		&quiz.ShuffleAnswers,
		&quiz.PassingScore,
		&quiz.TotalPoints,
		&quiz.AutoGrade,
		&quiz.ShowResultsImmediately,
		&quiz.ShowCorrectAnswers,
		&quiz.AllowReview,
		&quiz.ShowFeedback,
		&quiz.IsPublished,
		&quiz.CreatedBy,
		&quiz.CreatedAt,
		&quiz.UpdatedAt,
		&quiz.CreatorName,
		&quiz.CreatorEmail,
		&quiz.QuestionCount,
		&quiz.AttemptCount,
		&quiz.StudentCount,
		&quiz.AverageScore,
		&quiz.PassedCount,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("quiz not found")
		}
		return nil, err
	}
	
	return &quiz, nil
}

// GetQuizByContentID retrieves quiz by content ID
func (r *QuizRepository) GetQuizByContentID(ctx context.Context, contentID int64) (*models.Quiz, error) {
	query := `SELECT * FROM quizzes WHERE content_id = $1`
	
	var quiz models.Quiz
	err := r.db.QueryRowContext(ctx, query, contentID).Scan(
		&quiz.ID,
		&quiz.ContentID,
		&quiz.Title,
		&quiz.Description,
		&quiz.Instructions,
		&quiz.TimeLimitMinutes,
		&quiz.AvailableFrom,
		&quiz.AvailableUntil,
		&quiz.MaxAttempts,
		&quiz.ShuffleQuestions,
		&quiz.ShuffleAnswers,
		&quiz.PassingScore,
		&quiz.TotalPoints,
		&quiz.AutoGrade,
		&quiz.ShowResultsImmediately,
		&quiz.ShowCorrectAnswers,
		&quiz.AllowReview,
		&quiz.ShowFeedback,
		&quiz.IsPublished,
		&quiz.CreatedBy,
		&quiz.CreatedAt,
		&quiz.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("quiz not found for this content")
		}
		return nil, err
	}
	
	return &quiz, nil
}

// UpdateQuiz updates quiz details
func (r *QuizRepository) UpdateQuiz(ctx context.Context, quiz *models.Quiz) error {
	query := `
		UPDATE quizzes SET
			title = $1, description = $2, instructions = $3,
			time_limit_minutes = $4, available_from = $5, available_until = $6,
			max_attempts = $7, shuffle_questions = $8, shuffle_answers = $9,
			passing_score = $10, total_points = $11, auto_grade = $12,
			show_results_immediately = $13, show_correct_answers = $14,
			allow_review = $15, show_feedback = $16, is_published = $17,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = $18
		RETURNING updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		quiz.Title, quiz.Description, quiz.Instructions,
		quiz.TimeLimitMinutes, quiz.AvailableFrom, quiz.AvailableUntil,
		quiz.MaxAttempts, quiz.ShuffleQuestions, quiz.ShuffleAnswers,
		quiz.PassingScore, quiz.TotalPoints, quiz.AutoGrade,
		quiz.ShowResultsImmediately, quiz.ShowCorrectAnswers,
		quiz.AllowReview, quiz.ShowFeedback, quiz.IsPublished,
		quiz.ID,
	).Scan(&quiz.UpdatedAt)

	return err
}

// DeleteQuiz deletes a quiz
func (r *QuizRepository) DeleteQuiz(ctx context.Context, quizID int64) error {
	query := `DELETE FROM quizzes WHERE id = $1`
	result, err := r.db.ExecContext(ctx, query, quizID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return fmt.Errorf("quiz not found")
	}

	return nil
}

// ListQuizzesByCourse lists all quizzes for a course
func (r *QuizRepository) ListQuizzesByCourse(ctx context.Context, courseID int64, publishedOnly bool) ([]models.QuizWithStats, error) {
	query := `
		SELECT qs.* FROM quiz_summary_view qs
		JOIN section_content sc ON qs.content_id = sc.id
		JOIN course_sections cs ON sc.section_id = cs.id
		WHERE cs.course_id = $1
	`
	
	if publishedOnly {
		query += ` AND qs.is_published = true`
	}
	
	query += ` ORDER BY cs.order_index, sc.order_index`

	rows, err := r.db.QueryContext(ctx, query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var quizzes []models.QuizWithStats
	for rows.Next() {
		var q models.QuizWithStats

		err = rows.Scan(
			&q.ID,
			&q.ContentID,
			&q.Title,
			&q.IsPublished,
			&q.CreatorName,
			&q.CreatorEmail,
			&q.QuestionCount,
			&q.AttemptCount,
			&q.StudentCount,
			&q.PassedCount,
			&q.AverageScore,
			&q.CreatedAt,
			&q.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}

		quizzes = append(quizzes, q)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return quizzes, nil
}

// ============================================
// QUESTION OPERATIONS
// ============================================

// CreateQuestion creates a new question
func (r *QuizRepository) CreateQuestion(ctx context.Context, question *models.QuizQuestion) error {
	query := `
		INSERT INTO quiz_questions (
			quiz_id, question_type, question_text, question_html,
			explanation, points, order_index, settings, is_required
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		question.QuizID, question.QuestionType, question.QuestionText,
		question.QuestionHTML, question.Explanation, question.Points,
		question.OrderIndex, question.Settings, question.IsRequired,
	).Scan(&question.ID, &question.CreatedAt, &question.UpdatedAt)

	return err
}

// GetQuestion retrieves question by ID
func (r *QuizRepository) GetQuestion(ctx context.Context, questionID int64) (*models.QuizQuestion, error) {
	query := `SELECT * FROM quiz_questions WHERE id = $1`
	
	var q models.QuizQuestion
	err := r.db.QueryRowContext(ctx, query, questionID).Scan(
        &q.ID,
        &q.QuizID,
        &q.QuestionType,
        &q.QuestionText,
        &q.QuestionHTML,
        &q.Explanation,
        &q.Points,
		&q.OrderIndex,
		&q.Settings,
        &q.IsRequired,
        &q.CreatedAt,
        &q.UpdatedAt,
    )
    if err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, fmt.Errorf("question not found")
        }
        return nil, err
    }

    return &q, nil
}

// GetQuestionWithOptions retrieves question with answer options and correct answers
func (r *QuizRepository) GetQuestionWithOptions(ctx context.Context, questionID int64) (*models.QuestionWithOptions, error) {
	question, err := r.GetQuestion(ctx, questionID)
	if err != nil {
		return nil, err
	}

	qWithOptions := &models.QuestionWithOptions{
		QuizQuestion: *question,
	}

	// Get answer options
	options, err := r.ListAnswerOptions(ctx, questionID)
	if err != nil {
		return nil, err
	}
	qWithOptions.AnswerOptions = options

	// Get correct answers
	correctAnswers, err := r.ListCorrectAnswers(ctx, questionID)
	if err != nil {
		return nil, err
	}
	qWithOptions.CorrectAnswers = correctAnswers

	return qWithOptions, nil
}

// UpdateQuestion updates question details
func (r *QuizRepository) UpdateQuestion(ctx context.Context, question *models.QuizQuestion) error {
	query := `
		UPDATE quiz_questions SET
			question_text = $1, question_html = $2, explanation = $3,
			points = $4, order_index = $5, settings = $6, is_required = $7,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = $8
		RETURNING updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		question.QuestionText, question.QuestionHTML, question.Explanation,
		question.Points, question.OrderIndex, question.Settings, question.IsRequired,
		question.ID,
	).Scan(&question.UpdatedAt)

	return err
}

// DeleteQuestion deletes a question
func (r *QuizRepository) DeleteQuestion(ctx context.Context, questionID int64) error {
	query := `DELETE FROM quiz_questions WHERE id = $1`
	result, err := r.db.ExecContext(ctx, query, questionID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return fmt.Errorf("question not found")
	}

	return nil
}

// ListQuestions lists all questions for a quiz
func (r *QuizRepository) ListQuestions(ctx context.Context, quizID int64) ([]models.QuizQuestion, error) {
	query := `
		SELECT * FROM quiz_questions
		WHERE quiz_id = $1
		ORDER BY order_index
	`

	rows, err := r.db.QueryContext(ctx, query, quizID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var questions []models.QuizQuestion
	for rows.Next() {
		var q models.QuizQuestion

		err = rows.Scan(
			&q.ID,
			&q.QuizID,
			&q.QuestionType,
			&q.QuestionText,
			&q.QuestionHTML,
			&q.Explanation,
			&q.Points,
			&q.OrderIndex,
			&q.Settings,
			&q.IsRequired,
			&q.CreatedAt,
			&q.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}

		questions = append(questions, q)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return questions, nil
}

// ListQuestionsWithOptions lists all questions with their options
func (r *QuizRepository) ListQuestionsWithOptions(ctx context.Context, quizID int64) ([]models.QuestionWithOptions, error) {
	questions, err := r.ListQuestions(ctx, quizID)
	if err != nil {
		return nil, err
	}

	result := make([]models.QuestionWithOptions, 0, len(questions))
	for _, q := range questions {
		qWithOptions := models.QuestionWithOptions{
			QuizQuestion: q,
		}

		// Get answer options
		options, err := r.ListAnswerOptions(ctx, q.ID)
		if err != nil {
			return nil, err
		}
		qWithOptions.AnswerOptions = options

		// Get correct answers
		correctAnswers, err := r.ListCorrectAnswers(ctx, q.ID)
		if err != nil {
			return nil, err
		}
		qWithOptions.CorrectAnswers = correctAnswers

		result = append(result, qWithOptions)
	}

	return result, nil
}

// ============================================
// ANSWER OPTION OPERATIONS
// ============================================

// CreateAnswerOption creates a new answer option
func (r *QuizRepository) CreateAnswerOption(ctx context.Context, option *models.QuizAnswerOption) error {
	query := `
		INSERT INTO quiz_answer_options (
			question_id, option_text, option_html, is_correct, order_index, blank_id
		) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, created_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		option.QuestionID, option.OptionText, option.OptionHTML,
		option.IsCorrect, option.OrderIndex, option.BlankID,
	).Scan(&option.ID, &option.CreatedAt)

	return err
}

// ListAnswerOptions lists all answer options for a question
func (r *QuizRepository) ListAnswerOptions(ctx context.Context, questionID int64) ([]models.QuizAnswerOption, error) {
	query := `
		SELECT * FROM quiz_answer_options
		WHERE question_id = $1
		ORDER BY order_index
	`
	rows, err := r.db.QueryContext(ctx, query, questionID)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var options []models.QuizAnswerOption
	for rows.Next() {
		var opt models.QuizAnswerOption

		err = rows.Scan(
			&opt.ID,
			&opt.QuestionID,
			&opt.OptionText,
			&opt.OptionHTML,
			&opt.IsCorrect,
			&opt.OrderIndex,
			&opt.BlankID,
			&opt.CreatedAt,
			&opt.Settings,
		)
		if err != nil {
			return nil, err
		}

		options = append(options, opt)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return options, nil
}

// DeleteAnswerOption deletes an answer option
func (r *QuizRepository) DeleteAnswerOption(ctx context.Context, optionID int64) error {
	query := `DELETE FROM quiz_answer_options WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, optionID)
	return err
}

// DeleteAnswerOptionsByQuestion deletes all answer options for a question
func (r *QuizRepository) DeleteAnswerOptionsByQuestion(ctx context.Context, questionID int64) error {
	query := `DELETE FROM quiz_answer_options WHERE question_id = $1`
	_, err := r.db.ExecContext(ctx, query, questionID)
	return err
}

// ============================================
// CORRECT ANSWER OPERATIONS
// ============================================

// CreateCorrectAnswer creates a correct answer entry
func (r *QuizRepository) CreateCorrectAnswer(ctx context.Context, answer *models.QuizCorrectAnswer) error {
	query := `
		INSERT INTO quiz_correct_answers (
			question_id, answer_text, blank_id, blank_position, case_sensitive, exact_match
		) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, created_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		answer.QuestionID, answer.AnswerText, answer.BlankID,
		answer.BlankPosition, answer.CaseSensitive, answer.ExactMatch,
	).Scan(&answer.ID, &answer.CreatedAt)

	return err
}

// ListCorrectAnswers lists all correct answers for a question
func (r *QuizRepository) ListCorrectAnswers(ctx context.Context, questionID int64) ([]models.QuizCorrectAnswer, error) {
	query := `
		SELECT * FROM quiz_correct_answers
		WHERE question_id = $1
		ORDER BY blank_id, blank_position
	`
	rows, err := r.db.QueryContext(ctx, query, questionID)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var answers []models.QuizCorrectAnswer
	for rows.Next() {
		var q models.QuizCorrectAnswer

		err = rows.Scan(
			&q.ID,
			&q.QuestionID,
			&q.AnswerText,
			&q.BlankID,
			&q.BlankPosition,
			&q.CaseSensitive,
			&q.ExactMatch,
			&q.CreatedAt,
		)
		if err != nil {
			return nil, err
		}

		answers = append(answers, q)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return answers, nil
}

// DeleteCorrectAnswersByQuestion deletes all correct answers for a question
func (r *QuizRepository) DeleteCorrectAnswersByQuestion(ctx context.Context, questionID int64) error {
	query := `DELETE FROM quiz_correct_answers WHERE question_id = $1`
	_, err := r.db.ExecContext(ctx, query, questionID)
	return err
}

// ============================================
// QUIZ ATTEMPT OPERATIONS
// ============================================

// CreateAttempt creates a new quiz attempt
func (r *QuizRepository) CreateAttempt(ctx context.Context, attempt *models.QuizAttempt) error {
	query := `
		INSERT INTO quiz_attempts (
			quiz_id, student_id, attempt_number, status, ip_address, user_agent
		) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, started_at, created_at, updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		attempt.QuizID, attempt.StudentID, attempt.AttemptNumber,
		attempt.Status, attempt.IPAddress, attempt.UserAgent,
	).Scan(&attempt.ID, &attempt.StartedAt, &attempt.CreatedAt, &attempt.UpdatedAt)

	return err
}

// GetAttempt retrieves attempt by ID
func (r *QuizRepository) GetAttempt(ctx context.Context, attemptID int64) (*models.QuizAttempt, error) {
	query := `SELECT * FROM quiz_attempts WHERE id = $1`
	
	var attempt models.QuizAttempt
	err := r.db.QueryRowContext(ctx, query, attemptID).Scan(
		&attempt.ID,
		&attempt.QuizID,
		&attempt.StudentID,
		&attempt.AttemptNumber,
		&attempt.StartedAt,
		&attempt.SubmittedAt,
		&attempt.TimeSpentSeconds,
		&attempt.TotalPoints,
		&attempt.EarnedPoints,
		&attempt.Percentage,
		&attempt.IsPassed,
		&attempt.Status,
		&attempt.AutoGradedAt,
		&attempt.ManuallyGradedAt,
		&attempt.GradedBy,
		&attempt.IPAddress,
		&attempt.UserAgent,
		&attempt.CreatedAt,
		&attempt.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}
	
	return &attempt, nil
}

// GetStudentAttemptCount gets the number of attempts a student has made
func (r *QuizRepository) GetStudentAttemptCount(ctx context.Context, quizID, studentID int64) (int, error) {
	query := `
		SELECT COUNT(*) FROM quiz_attempts
		WHERE quiz_id = $1 AND student_id = $2
	`
	
	var count int
	err := r.db.QueryRowContext(ctx, query, quizID, studentID).Scan(&count)
	return count, err
}

// GetStudentLatestAttempt gets the latest attempt for a student
func (r *QuizRepository) GetStudentLatestAttempt(ctx context.Context, quizID, studentID int64) (*models.QuizAttempt, error) {
	query := `
		SELECT * FROM quiz_attempts
		WHERE quiz_id = $1 AND student_id = $2
		ORDER BY attempt_number DESC
		LIMIT 1
	`
	
	var attempt models.QuizAttempt
	err := r.db.QueryRowContext(ctx, query, quizID, studentID).Scan(
		&attempt.ID,
		&attempt.QuizID,
		&attempt.StudentID,
		&attempt.AttemptNumber,
		&attempt.StartedAt,
		&attempt.SubmittedAt,
		&attempt.TimeSpentSeconds,
		&attempt.TotalPoints,
		&attempt.EarnedPoints,
		&attempt.Percentage,
		&attempt.IsPassed,
		&attempt.Status,
		&attempt.AutoGradedAt,
		&attempt.ManuallyGradedAt,
		&attempt.GradedBy,
		&attempt.IPAddress,
		&attempt.UserAgent,
		&attempt.CreatedAt,
		&attempt.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil // No attempts yet
		}
		return nil, err
	}
	
	return &attempt, nil
}

// UpdateAttempt updates attempt details
func (r *QuizRepository) UpdateAttempt(ctx context.Context, attempt *models.QuizAttempt) error {
	query := `
		UPDATE quiz_attempts SET
			submitted_at = $1, time_spent_seconds = $2,
			total_points = $3, earned_points = $4, percentage = $5,
			is_passed = $6, status = $7,
			auto_graded_at = $8, manually_graded_at = $9, graded_by = $10,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = $11
		RETURNING updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		attempt.SubmittedAt, attempt.TimeSpentSeconds,
		attempt.TotalPoints, attempt.EarnedPoints, attempt.Percentage,
		attempt.IsPassed, attempt.Status,
		attempt.AutoGradedAt, attempt.ManuallyGradedAt, attempt.GradedBy,
		attempt.ID,
	).Scan(&attempt.UpdatedAt)

	return err
}

// ListStudentAttempts lists all attempts for a student on a quiz
func (r *QuizRepository) ListStudentAttempts(ctx context.Context, quizID, studentID int64) ([]models.QuizAttempt, error) {
	query := `
		SELECT * FROM quiz_attempts
		WHERE quiz_id = $1 AND student_id = $2
		ORDER BY attempt_number DESC
	`
	
	rows, err := r.db.QueryContext(ctx, query, quizID, studentID)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var attempts []models.QuizAttempt
	for rows.Next() {
		var attempt models.QuizAttempt

		err = rows.Scan(
			&attempt.ID,
			&attempt.QuizID,
			&attempt.StudentID,
			&attempt.AttemptNumber,
			&attempt.StartedAt,
			&attempt.SubmittedAt,
			&attempt.TimeSpentSeconds,
			&attempt.TotalPoints,
			&attempt.EarnedPoints,
			&attempt.Percentage,
			&attempt.IsPassed,
			&attempt.Status,
			&attempt.AutoGradedAt,
			&attempt.ManuallyGradedAt,
			&attempt.GradedBy,
			&attempt.IPAddress,
			&attempt.UserAgent,
			&attempt.CreatedAt,
			&attempt.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}

		attempts = append(attempts, attempt)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return attempts, nil
}

// ListQuizAttempts lists all attempts for a quiz
func (r *QuizRepository) ListQuizAttempts(ctx context.Context, quizID int64, status string) ([]models.QuizAttemptWithDetails, error) {
	query := `
		SELECT * FROM student_quiz_attempts_view
		WHERE quiz_id = $1
	`
	
	args := []interface{}{quizID}
	if status != "" {
		query += ` AND status = $2`
		args = append(args, status)
	}
	
	query += ` ORDER BY started_at DESC`

	rows, err := r.db.QueryContext(ctx, query, args...)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var attempts []models.QuizAttemptWithDetails
	for rows.Next() {
		var attempt models.QuizAttemptWithDetails

		err = rows.Scan(
			&attempt.ID,
			&attempt.QuizID,
			&attempt.StudentID,
			&attempt.AttemptNumber,
			&attempt.StartedAt,
			&attempt.SubmittedAt,
			&attempt.TimeSpentSeconds,
			&attempt.TotalPoints,
			&attempt.EarnedPoints,
			&attempt.Percentage,
			&attempt.IsPassed,
			&attempt.Status,
			&attempt.AutoGradedAt,
			&attempt.ManuallyGradedAt,
			&attempt.GradedBy,
			&attempt.IPAddress,
			&attempt.UserAgent,
			&attempt.CreatedAt,
			&attempt.UpdatedAt,
			&attempt.QuizTitle,
			&attempt.QuizTotalPoints,
			&attempt.PassingScore,
			&attempt.StudentName,
			&attempt.StudentEmail,
			&attempt.AnsweredQuestions,
			&attempt.CorrectAnswers,
		)
		if err != nil {
			return nil, err
		}

		attempts = append(attempts, attempt)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return attempts, nil
}

// ============================================
// STUDENT ANSWER OPERATIONS
// ============================================

// CreateStudentAnswer creates a student answer
func (r *QuizRepository) CreateStudentAnswer(ctx context.Context, answer *models.QuizStudentAnswer) error {
	query := `
		INSERT INTO quiz_student_answers (
			attempt_id, question_id, answer_data, time_spent_seconds
		) VALUES ($1, $2, $3, $4)
		RETURNING id, answered_at, created_at, updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		answer.AttemptID, answer.QuestionID, answer.AnswerData, answer.TimeSpentSeconds,
	).Scan(&answer.ID, &answer.AnsweredAt, &answer.CreatedAt, &answer.UpdatedAt)

	return err
}

// GetStudentAnswer retrieves a student answer
func (r *QuizRepository) GetStudentAnswer(ctx context.Context, answerID int64) (*models.QuizStudentAnswer, error) {
	query := `SELECT * FROM quiz_student_answers WHERE id = $1`
	
	var answer models.QuizStudentAnswer
	err := r.db.QueryRowContext(ctx, query, answerID).Scan(
		&answer.ID,
		&answer.AttemptID,
		&answer.QuestionID,
		&answer.AnswerData,
		&answer.PointsEarned,
		&answer.IsCorrect,
		&answer.GraderFeedback,
		&answer.GradedBy,
		&answer.GradedAt,
		&answer.AnsweredAt,
		&answer.TimeSpentSeconds,
		&answer.CreatedAt,
		&answer.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("answer not found")
		}
		return nil, err
	}
	
	return &answer, nil
}

// GetStudentAnswerByQuestion retrieves student answer for a specific question in an attempt
func (r *QuizRepository) GetStudentAnswerByQuestion(ctx context.Context, attemptID, questionID int64) (*models.QuizStudentAnswer, error) {
	query := `
		SELECT * FROM quiz_student_answers
		WHERE attempt_id = $1 AND question_id = $2
	`
	
	var answer models.QuizStudentAnswer
	err := r.db.QueryRowContext(ctx, query, attemptID, questionID).Scan(
		&answer.ID,
		&answer.AttemptID,
		&answer.QuestionID,
		&answer.AnswerData,
		&answer.PointsEarned,
		&answer.IsCorrect,
		&answer.GraderFeedback,
		&answer.GradedBy,
		&answer.GradedAt,
		&answer.AnsweredAt,
		&answer.TimeSpentSeconds,
		&answer.CreatedAt,
		&answer.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	
	return &answer, nil
}

// UpdateStudentAnswer updates a student answer
func (r *QuizRepository) UpdateStudentAnswer(ctx context.Context, answer *models.QuizStudentAnswer) error {
	query := `
		UPDATE quiz_student_answers SET
			answer_data = $1, points_earned = $2, is_correct = $3,
			grader_feedback = $4, graded_by = $5, graded_at = $6,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = $7
		RETURNING updated_at
	`

	err := r.db.QueryRowContext(
		ctx, query,
		answer.AnswerData, answer.PointsEarned, answer.IsCorrect,
		answer.GraderFeedback, answer.GradedBy, answer.GradedAt,
		answer.ID,
	).Scan(&answer.UpdatedAt)

	return err
}

// ListAttemptAnswers lists all answers for an attempt
func (r *QuizRepository) ListAttemptAnswers(ctx context.Context, attemptID int64) ([]models.QuizStudentAnswer, error) {
	query := `
		SELECT * FROM quiz_student_answers
		WHERE attempt_id = $1
		ORDER BY answered_at
	`

	
	rows, err := r.db.QueryContext(ctx, query, attemptID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var answers []models.QuizStudentAnswer
	for rows.Next() {
		var answer models.QuizStudentAnswer

		err = rows.Scan(
			&answer.ID,
			&answer.AttemptID,
			&answer.QuestionID,
			&answer.AnswerData,
			&answer.PointsEarned,
			&answer.IsCorrect,
			&answer.GraderFeedback,
			&answer.GradedBy,
			&answer.GradedAt,
			&answer.AnsweredAt,
			&answer.TimeSpentSeconds,
			&answer.CreatedAt,
			&answer.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}

		answers = append(answers, answer)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return answers, nil
}

// CountAnsweredQuestions counts how many questions have been answered in an attempt
func (r *QuizRepository) CountAnsweredQuestions(ctx context.Context, attemptID int64) (int, error) {
	query := `SELECT COUNT(*) FROM quiz_student_answers WHERE attempt_id = $1`
	
	var count int
	err := r.db.QueryRowContext(ctx, query, attemptID).Scan(&count)
	return count, err
}

// ============================================
// ANALYTICS OPERATIONS
// ============================================

// UpdateQuizAnalytics updates analytics for a quiz
func (r *QuizRepository) UpdateQuizAnalytics(ctx context.Context, quizID int64) error {
	// This would be called after each submission to update analytics
	query := `
		INSERT INTO quiz_analytics (quiz_id, total_attempts, correct_count, incorrect_count, average_score)
		SELECT 
			$1,
			COUNT(*) as total_attempts,
			COUNT(*) FILTER (WHERE is_correct = true) as correct_count,
			COUNT(*) FILTER (WHERE is_correct = false) as incorrect_count,
			AVG(COALESCE(points_earned, 0)) as average_score
		FROM quiz_student_answers qsa
		JOIN quiz_attempts qa ON qsa.attempt_id = qa.id
		WHERE qa.quiz_id = $1
		ON CONFLICT (quiz_id, question_id) DO UPDATE SET
			total_attempts = EXCLUDED.total_attempts,
			correct_count = EXCLUDED.correct_count,
			incorrect_count = EXCLUDED.incorrect_count,
			average_score = EXCLUDED.average_score,
			updated_at = CURRENT_TIMESTAMP
	`
	
	_, err := r.db.ExecContext(ctx, query, quizID)
	return err
}

// GetQuizAnalytics retrieves analytics for a quiz
func (r *QuizRepository) GetQuizAnalytics(ctx context.Context, quizID int64) ([]models.QuizAnalytics, error) {
	query := `
		SELECT * FROM quiz_analytics
		WHERE quiz_id = $1
		ORDER BY question_id
	`

	rows, err := r.db.QueryContext(ctx, query, quizID)

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var analytics []models.QuizAnalytics
	for rows.Next() {
		var analytic models.QuizAnalytics

		err = rows.Scan(
			&analytic.ID,
			&analytic.QuizID,
			&analytic.QuestionID,
			&analytic.TotalAttempts,
			&analytic.CorrectCount,
			&analytic.IncorrectCount,
			&analytic.AverageScore,
			&analytic.DifficultyRating,
			&analytic.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}

		analytics = append(analytics, analytic)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return analytics, nil
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

// BeginTx starts a transaction
func (r *QuizRepository) BeginTx(ctx context.Context) (*sql.Tx, error) {
	return r.db.BeginTx(ctx, nil)
}

// CheckQuizOwnership verifies if a user owns a quiz
func (r *QuizRepository) CheckQuizOwnership(ctx context.Context, quizID, userID int64) (bool, error) {
	query := `SELECT EXISTS(SELECT 1 FROM quizzes WHERE id = $1 AND created_by = $2)`
	
	var exists bool
	err := r.db.QueryRowContext(ctx, query, quizID, userID).Scan(&exists)
	return exists, err
}

// CheckAttemptOwnership verifies if a student owns an attempt
func (r *QuizRepository) CheckAttemptOwnership(ctx context.Context, attemptID, studentID int64) (bool, error) {
	query := `SELECT EXISTS(SELECT 1 FROM quiz_attempts WHERE id = $1 AND student_id = $2)`
	
	var exists bool
	err := r.db.QueryRowContext(ctx, query, attemptID, studentID).Scan(&exists)
	return exists, err
}

// AnswerForGrading represents an answer that needs grading with full context
type AnswerForGrading struct {
	AnswerID       int64
	AttemptID      int64
	AttemptNumber  int
	StudentID      int64
	StudentName    string
	StudentEmail   string
	QuestionID     int64
	QuestionText   string
	QuestionType   string
	Points         float64
	AnswerData     []byte
	PointsEarned   sql.NullFloat64
	GraderFeedback sql.NullString
	GradedAt       sql.NullTime
	AnsweredAt     time.Time
}

// GetAnswersForGrading retrieves all answers that need manual grading for a quiz
func (r *QuizRepository) GetAnswersForGrading(ctx context.Context, quizID int64) ([]AnswerForGrading, error) {
	query := `
		SELECT 
			qsa.id as answer_id,
			qsa.attempt_id,
			qa.attempt_number,
			qa.student_id,
			u.full_name as student_name,
			u.email as student_email,
			qq.id as question_id,
			qq.question_text,
			qq.question_type,
			qq.points,
			qsa.answer_data,
			qsa.points_earned,
			qsa.grader_feedback,
			qsa.graded_at,
			qsa.answered_at
		FROM quiz_student_answers qsa
		JOIN quiz_attempts qa ON qsa.attempt_id = qa.id
		JOIN users u ON qa.student_id = u.id
		JOIN quiz_questions qq ON qsa.question_id = qq.id
		WHERE qq.quiz_id = $1
		  AND qa.status = 'SUBMITTED'
		  AND qq.question_type IN ('ESSAY', 'FILE_UPLOAD', 'SHORT_ANSWER')
		ORDER BY qsa.graded_at NULLS FIRST, qsa.answered_at DESC
	`

	rows, err := r.db.QueryContext(ctx, query, quizID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var answers []AnswerForGrading
	for rows.Next() {
		var answer AnswerForGrading
		err := rows.Scan(
			&answer.AnswerID,
			&answer.AttemptID,
			&answer.AttemptNumber,
			&answer.StudentID,
			&answer.StudentName,
			&answer.StudentEmail,
			&answer.QuestionID,
			&answer.QuestionText,
			&answer.QuestionType,
			&answer.Points,
			&answer.AnswerData,
			&answer.PointsEarned,
			&answer.GraderFeedback,
			&answer.GradedAt,
			&answer.AnsweredAt,
		)
		if err != nil {
			return nil, err
		}
		answers = append(answers, answer)
	}

	return answers, rows.Err()
}