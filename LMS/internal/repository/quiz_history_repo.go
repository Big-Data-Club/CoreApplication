package repository

import (
	"context"
	"database/sql"

	"example/hello/internal/models"
)

// GetStudentAttempts retrieves all attempts by a student for a specific quiz
func (r *QuizRepository) GetStudentAttempts(ctx context.Context, quizID, studentID int64) ([]models.QuizAttemptWithDetails, error) {
	query := `
		SELECT 
			qa.id, qa.quiz_id, qa.student_id, qa.attempt_number,
			qa.started_at, qa.submitted_at, qa.time_spent_seconds,
			qa.total_points, qa.earned_points, qa.percentage,
			qa.is_passed, qa.status, qa.auto_graded_at,
			qa.manually_graded_at, qa.graded_by, qa.ip_address,
			qa.user_agent, qa.created_at, qa.updated_at,
			q.title as quiz_title,
			q.total_points as quiz_total_points,
			q.passing_score,
			u.full_name as student_name,
			u.email as student_email,
			COUNT(DISTINCT qsa.id) as answered_questions,
			COUNT(DISTINCT CASE WHEN qsa.is_correct = true THEN qsa.id END) as correct_answers
		FROM quiz_attempts qa
		JOIN quizzes q ON qa.quiz_id = q.id
		JOIN users u ON qa.student_id = u.id
		LEFT JOIN quiz_student_answers qsa ON qa.id = qsa.attempt_id
		WHERE qa.quiz_id = $1 AND qa.student_id = $2
		GROUP BY qa.id, q.id, u.id
		ORDER BY qa.created_at DESC
	`

	rows, err := r.db.QueryContext(ctx, query, quizID, studentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var attempts []models.QuizAttemptWithDetails
	for rows.Next() {
		var attempt models.QuizAttemptWithDetails
		err := rows.Scan(
			&attempt.ID, &attempt.QuizID, &attempt.StudentID, &attempt.AttemptNumber,
			&attempt.StartedAt, &attempt.SubmittedAt, &attempt.TimeSpentSeconds,
			&attempt.TotalPoints, &attempt.EarnedPoints, &attempt.Percentage,
			&attempt.IsPassed, &attempt.Status, &attempt.AutoGradedAt,
			&attempt.ManuallyGradedAt, &attempt.GradedBy, &attempt.IPAddress,
			&attempt.UserAgent, &attempt.CreatedAt, &attempt.UpdatedAt,
			&attempt.QuizTitle, &attempt.QuizTotalPoints, &attempt.PassingScore,
			&attempt.StudentName, &attempt.StudentEmail,
			&attempt.AnsweredQuestions, &attempt.CorrectAnswers,
		)
		if err != nil {
			return nil, err
		}
		attempts = append(attempts, attempt)
	}

	return attempts, nil
}

// GetAttemptWithDetails retrieves a single attempt with full details
func (r *QuizRepository) GetAttemptWithDetails(ctx context.Context, attemptID int64) (*models.QuizAttemptWithDetails, error) {
	query := `
		SELECT 
			qa.id, qa.quiz_id, qa.student_id, qa.attempt_number,
			qa.started_at, qa.submitted_at, qa.time_spent_seconds,
			qa.total_points, qa.earned_points, qa.percentage,
			qa.is_passed, qa.status, qa.auto_graded_at,
			qa.manually_graded_at, qa.graded_by, qa.ip_address,
			qa.user_agent, qa.created_at, qa.updated_at,
			q.title as quiz_title,
			q.total_points as quiz_total_points,
			q.passing_score,
			u.full_name as student_name,
			u.email as student_email,
			COUNT(DISTINCT qsa.id) as answered_questions,
			COUNT(DISTINCT CASE WHEN qsa.is_correct = true THEN qsa.id END) as correct_answers
		FROM quiz_attempts qa
		JOIN quizzes q ON qa.quiz_id = q.id
		JOIN users u ON qa.student_id = u.id
		LEFT JOIN quiz_student_answers qsa ON qa.id = qsa.attempt_id
		WHERE qa.id = $1
		GROUP BY qa.id, q.id, u.id
	`

	var attempt models.QuizAttemptWithDetails
	err := r.db.QueryRowContext(ctx, query, attemptID).Scan(
		&attempt.ID, &attempt.QuizID, &attempt.StudentID, &attempt.AttemptNumber,
		&attempt.StartedAt, &attempt.SubmittedAt, &attempt.TimeSpentSeconds,
		&attempt.TotalPoints, &attempt.EarnedPoints, &attempt.Percentage,
		&attempt.IsPassed, &attempt.Status, &attempt.AutoGradedAt,
		&attempt.ManuallyGradedAt, &attempt.GradedBy, &attempt.IPAddress,
		&attempt.UserAgent, &attempt.CreatedAt, &attempt.UpdatedAt,
		&attempt.QuizTitle, &attempt.QuizTotalPoints, &attempt.PassingScore,
		&attempt.StudentName, &attempt.StudentEmail,
		&attempt.AnsweredQuestions, &attempt.CorrectAnswers,
	)
	
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	return &attempt, nil
}

// GetAttemptAnswers retrieves all answers for a specific attempt
func (r *QuizRepository) GetAttemptAnswers(ctx context.Context, attemptID int64) ([]models.QuizStudentAnswer, error) {
	query := `
		SELECT 
			id, attempt_id, question_id, answer_data,
			points_earned, is_correct, grader_feedback,
			graded_by, graded_at, answered_at,
			time_spent_seconds, created_at, updated_at
		FROM quiz_student_answers
		WHERE attempt_id = $1
		ORDER BY answered_at ASC
	`

	rows, err := r.db.QueryContext(ctx, query, attemptID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var answers []models.QuizStudentAnswer
	for rows.Next() {
		var answer models.QuizStudentAnswer
		err := rows.Scan(
			&answer.ID, &answer.AttemptID, &answer.QuestionID, &answer.AnswerData,
			&answer.PointsEarned, &answer.IsCorrect, &answer.GraderFeedback,
			&answer.GradedBy, &answer.GradedAt, &answer.AnsweredAt,
			&answer.TimeSpentSeconds, &answer.CreatedAt, &answer.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		answers = append(answers, answer)
	}

	return answers, nil
}

// GetAttempt retrieves a single quiz attempt
func (r *QuizRepository) GetAttempt(ctx context.Context, attemptID int64) (*models.QuizAttempt, error) {
	query := `
		SELECT 
			id, quiz_id, student_id, attempt_number,
			started_at, submitted_at, time_spent_seconds,
			total_points, earned_points, percentage,
			is_passed, status, auto_graded_at,
			manually_graded_at, graded_by, ip_address,
			user_agent, created_at, updated_at
		FROM quiz_attempts
		WHERE id = $1
	`

	var attempt models.QuizAttempt
	err := r.db.QueryRowContext(ctx, query, attemptID).Scan(
		&attempt.ID, &attempt.QuizID, &attempt.StudentID, &attempt.AttemptNumber,
		&attempt.StartedAt, &attempt.SubmittedAt, &attempt.TimeSpentSeconds,
		&attempt.TotalPoints, &attempt.EarnedPoints, &attempt.Percentage,
		&attempt.IsPassed, &attempt.Status, &attempt.AutoGradedAt,
		&attempt.ManuallyGradedAt, &attempt.GradedBy, &attempt.IPAddress,
		&attempt.UserAgent, &attempt.CreatedAt, &attempt.UpdatedAt,
	)
	
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	return &attempt, nil
}