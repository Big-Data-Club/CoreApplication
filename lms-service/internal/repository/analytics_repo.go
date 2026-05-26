package repository

import (
	"context"
	"database/sql"
	"time"

	"example/hello/internal/dto"
)

type QuizPerformanceRow struct {
	QuizID         int64
	QuizTitle      string
	ContentID      int64
	TotalAttempts  int
	UniqueStudents int
	AvgScore       sql.NullFloat64
	AvgPercentage  sql.NullFloat64
	PassRate       sql.NullFloat64
	PassingScore   sql.NullFloat64
}

type StudentAttemptRow struct {
	StudentID     int64
	StudentName   string
	StudentEmail  string
	QuizID        int64
	QuizTitle     string
	AttemptNumber int
	EarnedPoints  sql.NullFloat64
	TotalPoints   float64
	Percentage    sql.NullFloat64
	IsPassed      sql.NullBool
	Status        string
	SubmittedAt   sql.NullTime
}

type WrongAnswerRow struct {
	QuestionID   int64
	QuestionText string
	QuestionType string
	TotalAnswers int
	WrongCount   int
	WrongRate    float64
}

type StudentProgressRow struct {
	StudentID        int64
	StudentName      string
	StudentEmail     string
	TotalMandatory   int
	CompletedContent int
	ProgressPercent  float64
	QuizAvgScore     sql.NullFloat64
	LastActivity     sql.NullTime
}

type StudentQuizScoreRow struct {
	QuizID        int64
	QuizTitle     string
	BestPct       sql.NullFloat64
	BestPoints    sql.NullFloat64
	TotalPoints   float64
	AttemptsCount int
	IsPassed      sql.NullBool
	PassingScore  sql.NullFloat64
	LastAttemptAt sql.NullTime
	Status        string
}

type AnalyticsRepository struct {
	db *sql.DB
}

func NewAnalyticsRepository(db *sql.DB) *AnalyticsRepository {
	return &AnalyticsRepository{db: db}
}

// GetCourseQuizAnalytics returns a performance summary per quiz for a course.
// Only SUBMITTED / GRADED attempts are counted.
func (r *AnalyticsRepository) GetCourseQuizAnalytics(ctx context.Context, courseID int64) ([]QuizPerformanceRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			q.id, q.title, q.content_id,
			COUNT(DISTINCT qa.id)                                                       AS total_attempts,
			COUNT(DISTINCT qa.student_id)                                               AS unique_students,
			AVG(qa.earned_points)                                                       AS avg_score,
			AVG(qa.percentage)                                                          AS avg_percentage,
			COALESCE(
				COUNT(DISTINCT qa.id) FILTER (WHERE qa.is_passed = TRUE)::FLOAT
				/ NULLIF(COUNT(DISTINCT qa.student_id), 0) * 100
			, 0)                                                                        AS pass_rate,
			q.passing_score
		FROM quizzes q
		JOIN section_content sc ON q.content_id = sc.id
		JOIN course_sections cs ON sc.section_id = cs.id
		LEFT JOIN quiz_attempts qa
			ON qa.quiz_id = q.id AND qa.status IN ('SUBMITTED', 'GRADED')
		WHERE cs.course_id = $1
		GROUP BY q.id, q.title, q.content_id, q.passing_score
		ORDER BY MIN(cs.order_index) ASC, MIN(sc.order_index) ASC
	`, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []QuizPerformanceRow
	for rows.Next() {
		var row QuizPerformanceRow
		if err := rows.Scan(
			&row.QuizID, &row.QuizTitle, &row.ContentID,
			&row.TotalAttempts, &row.UniqueStudents,
			&row.AvgScore, &row.AvgPercentage, &row.PassRate,
			&row.PassingScore,
		); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// GetQuizAllAttempts returns every SUBMITTED/GRADED attempt for a quiz,
// ordered by student name then attempt number descending.
func (r *AnalyticsRepository) GetQuizAllAttempts(ctx context.Context, quizID int64) ([]StudentAttemptRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			qa.student_id,
			u.full_name, u.email,
			q.id, q.title,
			qa.attempt_number,
			qa.earned_points, q.total_points,
			qa.percentage, qa.is_passed, qa.status, qa.submitted_at
		FROM quiz_attempts qa
		JOIN users   u ON u.id = qa.student_id
		JOIN quizzes q ON q.id = qa.quiz_id
		WHERE qa.quiz_id = $1 AND qa.status IN ('SUBMITTED', 'GRADED')
		ORDER BY u.full_name ASC, qa.attempt_number DESC
	`, quizID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []StudentAttemptRow
	for rows.Next() {
		var row StudentAttemptRow
		if err := rows.Scan(
			&row.StudentID, &row.StudentName, &row.StudentEmail,
			&row.QuizID, &row.QuizTitle,
			&row.AttemptNumber, &row.EarnedPoints, &row.TotalPoints,
			&row.Percentage, &row.IsPassed, &row.Status, &row.SubmittedAt,
		); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// GetQuizWrongAnswerStats returns question-level wrong-answer rates,
// ordered from highest wrong-rate to lowest.
// Questions that cannot be auto-graded (is_correct IS NULL) are excluded.
func (r *AnalyticsRepository) GetQuizWrongAnswerStats(ctx context.Context, quizID int64) ([]WrongAnswerRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			qq.id, qq.question_text, qq.question_type,
			COUNT(*)                                               AS total_answers,
			COUNT(*) FILTER (WHERE qsa.is_correct = FALSE)        AS wrong_count,
			COALESCE(
				COUNT(*) FILTER (WHERE qsa.is_correct = FALSE)::FLOAT
				/ NULLIF(COUNT(*), 0) * 100
			, 0)                                                   AS wrong_rate
		FROM quiz_student_answers qsa
		JOIN quiz_questions qq ON qq.id = qsa.question_id
		JOIN quiz_attempts  qa ON qa.id = qsa.attempt_id
		WHERE qq.quiz_id = $1
		  AND qa.status IN ('SUBMITTED', 'GRADED')
		  AND qsa.is_correct IS NOT NULL
		GROUP BY qq.id, qq.question_text, qq.question_type
		HAVING COUNT(*) > 0
		ORDER BY wrong_rate DESC
	`, quizID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []WrongAnswerRow
	for rows.Next() {
		var row WrongAnswerRow
		if err := rows.Scan(
			&row.QuestionID, &row.QuestionText, &row.QuestionType,
			&row.TotalAnswers, &row.WrongCount, &row.WrongRate,
		); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// GetCourseStudentProgressOverview returns one row per enrolled (ACCEPTED)
// student with their mandatory-content completion % and quiz average.
func (r *AnalyticsRepository) GetCourseStudentProgressOverview(ctx context.Context, courseID int64) ([]StudentProgressRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		WITH course_content AS (
			SELECT sc.id AS content_id, sc.is_mandatory
			FROM   section_content  sc
			JOIN   course_sections  cs ON cs.id = sc.section_id
			WHERE  cs.course_id = $1
		),
		course_quizzes AS (
			SELECT q.id AS quiz_id
			FROM   quizzes          q
			JOIN   section_content  sc ON sc.id = q.content_id
			JOIN   course_sections  cs ON cs.id = sc.section_id
			WHERE  cs.course_id = $1
		),
		student_progress AS (
			SELECT
				cp.student_id,
				COUNT(DISTINCT cp.content_id) FILTER (WHERE cc.is_mandatory) AS completed_content,
				MAX(cp.completed_at) AS last_completed
			FROM content_progress cp
			JOIN course_content cc ON cp.content_id = cc.content_id
			GROUP BY cp.student_id
		),
		student_quizzes AS (
			SELECT
				qa.student_id,
				AVG(qa.percentage) AS quiz_avg_score,
				MAX(qa.submitted_at) AS last_submitted
			FROM quiz_attempts qa
			WHERE qa.quiz_id IN (SELECT quiz_id FROM course_quizzes)
			  AND qa.status IN ('SUBMITTED', 'GRADED')
			GROUP BY qa.student_id
		),
		mandatory_stats AS (
			SELECT
				COUNT(DISTINCT content_id) FILTER (WHERE is_mandatory) AS total_mandatory
			FROM course_content
		)
		SELECT
			e.student_id,
			u.full_name,
			u.email,
			COALESCE(ms.total_mandatory, 0) AS total_mandatory,
			COALESCE(sp.completed_content, 0) AS completed_content,
			CASE
				WHEN COALESCE(ms.total_mandatory, 0) = 0 THEN 0.0
				ELSE COALESCE(sp.completed_content, 0)::FLOAT / ms.total_mandatory * 100
			END AS progress_percent,
			sq.quiz_avg_score,
			GREATEST(sp.last_completed, sq.last_submitted) AS last_activity
		FROM enrollments e
		JOIN users u ON u.id = e.student_id
		LEFT JOIN student_progress sp ON sp.student_id = e.student_id
		LEFT JOIN student_quizzes sq ON sq.student_id = e.student_id
		CROSS JOIN mandatory_stats ms
		WHERE e.course_id = $1
		  AND e.status = 'ACCEPTED'
		GROUP BY e.student_id, u.full_name, u.email, ms.total_mandatory, sp.completed_content, sq.quiz_avg_score, sp.last_completed, sq.last_submitted
		ORDER BY progress_percent DESC, u.full_name ASC
	`, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []StudentProgressRow
	for rows.Next() {
		var row StudentProgressRow
		if err := rows.Scan(
			&row.StudentID, &row.StudentName, &row.StudentEmail,
			&row.TotalMandatory, &row.CompletedContent, &row.ProgressPercent,
			&row.QuizAvgScore, &row.LastActivity,
		); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// GetStudentQuizScores returns best-attempt info per quiz for one student
// in a course, with a computed status string.
func (r *AnalyticsRepository) GetStudentQuizScores(ctx context.Context, courseID, studentID int64) ([]StudentQuizScoreRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			q.id, q.title,
			MAX(qa.percentage)      AS best_pct,
			MAX(qa.earned_points)   AS best_points,
			q.total_points,
			COUNT(qa.id)            AS attempts_count,
			BOOL_OR(COALESCE(qa.is_passed, FALSE)) AS is_passed,
			q.passing_score,
			MAX(qa.submitted_at)    AS last_attempt_at,
			CASE
				WHEN COUNT(qa.id) = 0
					THEN 'not_started'
				WHEN SUM(CASE WHEN qa.status = 'IN_PROGRESS' THEN 1 ELSE 0 END) > 0
					THEN 'in_progress'
				WHEN BOOL_OR(COALESCE(qa.is_passed, FALSE))
					THEN 'passed'
				WHEN COUNT(qa.id) FILTER (WHERE qa.status IN ('SUBMITTED','GRADED')) > 0
					AND NOT BOOL_OR(COALESCE(qa.is_passed, FALSE))
					THEN 'failed'
				ELSE 'submitted'
			END AS status
		FROM quizzes q
		JOIN section_content sc ON sc.id = q.content_id
		JOIN course_sections cs ON cs.id = sc.section_id
		LEFT JOIN quiz_attempts qa
			ON qa.quiz_id = q.id AND qa.student_id = $2
		WHERE cs.course_id = $1
		GROUP BY q.id, q.title, q.total_points, q.passing_score
		ORDER BY MIN(cs.order_index) ASC, MIN(sc.order_index) ASC
	`, courseID, studentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []StudentQuizScoreRow
	for rows.Next() {
		var row StudentQuizScoreRow
		if err := rows.Scan(
			&row.QuizID, &row.QuizTitle,
			&row.BestPct, &row.BestPoints, &row.TotalPoints,
			&row.AttemptsCount, &row.IsPassed, &row.PassingScore,
			&row.LastAttemptAt, &row.Status,
		); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// GetQuizCourseID resolves the course_id for a quiz (used in permission checks).
// Returns 0, nil when not found.
func (r *AnalyticsRepository) GetQuizCourseID(ctx context.Context, quizID int64) (int64, error) {
	var courseID int64
	err := r.db.QueryRowContext(ctx, `
		SELECT cs.course_id
		FROM quizzes q
		JOIN section_content sc ON sc.id = q.content_id
		JOIN course_sections cs ON cs.id = sc.section_id
		WHERE q.id = $1
	`, quizID).Scan(&courseID)
	if err == sql.ErrNoRows {
		return 0, nil
	}
	return courseID, err
}

func (r *AnalyticsRepository) GetStudentWeaknesses(ctx context.Context, studentID, courseID int64) ([]dto.WeakNode, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			skp.node_id,
			kn.name AS node_title,
			skp.wrong_count,
			skp.total_attempts,
			skp.mastery_level,
			CASE
				WHEN skp.mastery_level >= 0.8 THEN 'Rất tốt'
				WHEN skp.mastery_level >= 0.6 THEN 'TB'
				WHEN skp.mastery_level >= 0.4 THEN 'Yếu'
				ELSE 'Cần cải thiện'
			END AS status_level
		FROM student_knowledge_progress skp
		JOIN knowledge_nodes kn ON kn.id = skp.node_id
		WHERE skp.student_id = $1 AND skp.course_id = $2
		ORDER BY skp.mastery_level ASC, skp.wrong_count DESC
	`, studentID, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []dto.WeakNode
	for rows.Next() {
		var node dto.WeakNode
		if err := rows.Scan(
			&node.NodeID, &node.NodeTitle, &node.WrongCount,
			&node.TotalAttempt, &node.MasteryLevel, &node.StatusLevel,
		); err != nil {
			return nil, err
		}
		result = append(result, node)
	}
	return result, rows.Err()
}

// GetFlashcardStats returns Spaced Repetition stats for the student in a course.
func (r *AnalyticsRepository) GetFlashcardStats(ctx context.Context, studentID, courseID int64) (*dto.FlashcardStatsResponse, error) {
	var stats dto.FlashcardStatsResponse
	err := r.db.QueryRowContext(ctx, `
		SELECT
			COUNT(*) FILTER (WHERE next_review_date <= CURRENT_DATE) AS today_due_count,
			COUNT(*) FILTER (WHERE next_review_date > CURRENT_DATE)  AS upcoming_count,
			COUNT(*)                                                  AS learning_count
		FROM flashcard_repetitions
		WHERE student_id = $1 AND course_id = $2
	`, studentID, courseID).Scan(
		&stats.TodayDueCount,
		&stats.UpcomingCount,
		&stats.LearningCount,
	)
	if err != nil && err != sql.ErrNoRows {
		return nil, err
	}
	return &stats, nil
}

// GetStudentLessonProgressSummary aggregates total and completed content count per content type for a course.
func (r *AnalyticsRepository) GetStudentLessonProgressSummary(ctx context.Context, courseID, studentID int64) (dto.LessonProgressSummary, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			sc.type AS content_type,
			COUNT(sc.id) AS total_count,
			COUNT(cp.id) AS completed_count
		FROM section_content sc
		JOIN course_sections cs ON sc.section_id = cs.id
		LEFT JOIN content_progress cp ON cp.content_id = sc.id AND cp.student_id = $2
		WHERE cs.course_id = $1
		GROUP BY sc.type
	`, courseID, studentID)
	if err != nil {
		return dto.LessonProgressSummary{}, err
	}
	defer rows.Close()

	var summary dto.LessonProgressSummary
	var byType []dto.LessonContentTypeCount

	totalCompleted := 0
	totalContent := 0

	for rows.Next() {
		var item dto.LessonContentTypeCount
		if err := rows.Scan(&item.ContentType, &item.Total, &item.Completed); err != nil {
			return dto.LessonProgressSummary{}, err
		}
		totalCompleted += item.Completed
		totalContent += item.Total
		byType = append(byType, item)
	}

	// Query section progress
	rowsSec, err := r.db.QueryContext(ctx, `
		SELECT
			COALESCE(cs.title, 'Chương khác') AS section_title,
			COUNT(sc.id) AS total_count,
			COUNT(cp.id) AS completed_count
		FROM section_content sc
		JOIN course_sections cs ON sc.section_id = cs.id
		LEFT JOIN content_progress cp ON cp.content_id = sc.id AND cp.student_id = $2
		WHERE cs.course_id = $1
		GROUP BY cs.id, cs.title, cs.order_index
		ORDER BY cs.order_index ASC
	`, courseID, studentID)
	
	var bySection []dto.SectionProgressCount
	if err == nil {
		defer rowsSec.Close()
		for rowsSec.Next() {
			var secItem dto.SectionProgressCount
			if err := rowsSec.Scan(&secItem.SectionTitle, &secItem.Total, &secItem.Completed); err == nil {
				if secItem.Total > 0 {
					secItem.Percent = (secItem.Completed * 100) / secItem.Total
				}
				bySection = append(bySection, secItem)
			}
		}
	}

	summary.TotalCompleted = totalCompleted
	summary.TotalContent = totalContent
	summary.ByType = byType
	summary.BySection = bySection
	if totalContent > 0 {
		summary.Percent = (float64(totalCompleted) / float64(totalContent)) * 100.0
	}

	return summary, rows.Err()
}

// GetStudentMicroInteractionSummary calculates stats for student's quick-check questions in a course.
func (r *AnalyticsRepository) GetStudentMicroInteractionSummary(ctx context.Context, courseID, studentID int64) (dto.MicroInteractionSummary, error) {
	var summary dto.MicroInteractionSummary
	err := r.db.QueryRowContext(ctx, `
		SELECT
			COUNT(*) FILTER (WHERE action_type IN ('quick_check_correct', 'quick_check_incorrect', 'quick_check_attempt')) AS total_interactions,
			COUNT(*) FILTER (WHERE action_type = 'quick_check_correct') AS total_correct,
			COUNT(*) FILTER (WHERE action_type = 'quick_check_incorrect') AS total_wrong
		FROM micro_lesson_interactions
		WHERE user_id = $2 AND course_id = $1
	`, courseID, studentID).Scan(
		&summary.TotalInteractions,
		&summary.TotalCorrect,
		&summary.TotalWrong,
	)
	if err != nil && err != sql.ErrNoRows {
		return summary, err
	}
	return summary, nil
}

var _ = time.Time{}