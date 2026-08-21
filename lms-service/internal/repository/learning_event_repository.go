package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strconv"

	"example/hello/internal/models"
	"github.com/jmoiron/sqlx"
)

type LearningEventRepository struct {
	db *sqlx.DB
}

func NewLearningEventRepository(db *sql.DB) *LearningEventRepository {
	return &LearningEventRepository{db: sqlx.NewDb(db, "pgx")}
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENTS
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) CreateEvent(ctx context.Context, event *models.LearningEvent) error {
	query := `
		INSERT INTO learning_events (
			event_id, event_type, student_id, session_id, course_id,
			lesson_id, question_id, skill_id, difficulty, correct,
			attempt_no, response_time_ms, hint_count, metadata
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
		) RETURNING id, created_at`

	err := r.db.QueryRowContext(
		ctx, query,
		event.EventID, event.EventType, event.StudentID, event.SessionID, event.CourseID,
		event.LessonID, event.QuestionID, event.SkillID, event.Difficulty, event.Correct,
		event.AttemptNo, event.ResponseTimeMs, event.HintCount, event.Metadata,
	).Scan(&event.ID, &event.CreatedAt)

	return err
}

func (r *LearningEventRepository) GetEventByID(ctx context.Context, id int64) (*models.LearningEvent, error) {
	var event models.LearningEvent
	query := `SELECT * FROM learning_events WHERE id = $1`
	err := r.db.GetContext(ctx, &event, query, id)
	if err != nil {
		return nil, err
	}
	return &event, nil
}

func (r *LearningEventRepository) GetStudentEvents(ctx context.Context, studentID int64, courseIDStr, limitStr string) ([]models.LearningEvent, error) {
	query := `
		SELECT * FROM learning_events
		WHERE student_id = $1`

	args := []interface{}{studentID}
	argIndex := 2

	if courseIDStr != "" {
		courseID, err := strconv.ParseInt(courseIDStr, 10, 64)
		if err == nil {
			query += fmt.Sprintf(" AND course_id = $%d", argIndex)
			args = append(args, courseID)
			argIndex++
		}
	}

	query += " ORDER BY created_at DESC"

	if limitStr != "" {
		limit, err := strconv.Atoi(limitStr)
		if err == nil && limit > 0 {
			query += fmt.Sprintf(" LIMIT $%d", argIndex)
			args = append(args, limit)
		}
	}

	var events []models.LearningEvent
	err := r.db.SelectContext(ctx, &events, query, args...)
	if err != nil {
		return nil, err
	}
	return events, nil
}

func (r *LearningEventRepository) GetSkillEvents(ctx context.Context, studentID, skillID int64, limit int) ([]models.LearningEvent, error) {
	query := `
		SELECT * FROM learning_events
		WHERE student_id = $1 AND skill_id = $2
		ORDER BY created_at DESC
		LIMIT $3`

	var events []models.LearningEvent
	err := r.db.SelectContext(ctx, &events, query, studentID, skillID, limit)
	if err != nil {
		return nil, err
	}
	return events, nil
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNER SKILL STATES
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) UpsertLearnerSkillState(ctx context.Context, state *models.LearnerSkillState) error {
	query := `
		INSERT INTO learner_skill_states (
			student_id, skill_id, mastery_score, confidence_score,
			attempt_count, accuracy, avg_response_time_ms, hint_dependency,
			last_practiced_at, recommended_difficulty
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10
		)
		ON CONFLICT (student_id, skill_id)
		DO UPDATE SET
			mastery_score = EXCLUDED.mastery_score,
			confidence_score = EXCLUDED.confidence_score,
			attempt_count = EXCLUDED.attempt_count,
			accuracy = EXCLUDED.accuracy,
			avg_response_time_ms = EXCLUDED.avg_response_time_ms,
			hint_dependency = EXCLUDED.hint_dependency,
			last_practiced_at = EXCLUDED.last_practiced_at,
			recommended_difficulty = EXCLUDED.recommended_difficulty,
			updated_at = CURRENT_TIMESTAMP
		RETURNING id, updated_at`

	err := r.db.QueryRowContext(
		ctx, query,
		state.StudentID, state.SkillID, state.MasteryScore, state.ConfidenceScore,
		state.AttemptCount, state.Accuracy, state.AvgResponseTimeMs, state.HintDependency,
		state.LastPracticedAt, state.RecommendedDifficulty,
	).Scan(&state.ID, &state.UpdatedAt)

	return err
}

func (r *LearningEventRepository) GetStudentSkillStates(ctx context.Context, studentID int64, courseIDStr string) ([]models.LearnerSkillStateWithSkill, error) {
	query := `
		SELECT
			lss.*,
			s.name as skill_name,
			s.description as skill_description,
			s.difficulty as skill_difficulty
		FROM learner_skill_states lss
		JOIN skills s ON lss.skill_id = s.id`

	args := []interface{}{studentID}
	argIndex := 2

	if courseIDStr != "" {
		// If filtering by course, join with content_skills to find relevant skills
		query = `
			SELECT DISTINCT
				lss.*,
				s.name as skill_name,
				s.description as skill_description,
				s.difficulty as skill_difficulty
			FROM learner_skill_states lss
			JOIN skills s ON lss.skill_id = s.id
			LEFT JOIN content_skills cs ON s.id = cs.skill_id
			LEFT JOIN section_content sc ON cs.content_id = sc.id
			LEFT JOIN course_sections sect ON sc.section_id = sect.id`

		query += fmt.Sprintf(" WHERE lss.student_id = $1 AND sect.course_id = $%d", argIndex)
		courseID, err := strconv.ParseInt(courseIDStr, 10, 64)
		if err != nil {
			return nil, err
		}
		args = append(args, courseID)
	} else {
		query += " WHERE lss.student_id = $1"
	}

	query += " ORDER BY lss.mastery_score ASC, lss.last_practiced_at DESC"

	var states []models.LearnerSkillStateWithSkill
	err := r.db.SelectContext(ctx, &states, query, args...)
	if err != nil {
		return nil, err
	}
	return states, nil
}

func (r *LearningEventRepository) GetLearnerSkillState(ctx context.Context, studentID, skillID int64) (*models.LearnerSkillState, error) {
	var state models.LearnerSkillState
	query := `SELECT * FROM learner_skill_states WHERE student_id = $1 AND skill_id = $2`
	err := r.db.GetContext(ctx, &state, query, studentID, skillID)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &state, nil
}

// FindPublishedContentForSkill returns one real, published content item close
// to the learner's target difficulty. Recommendations must only point to
// navigable content; never synthesize lesson IDs. Section-level publish state
// is intentionally not filtered: the student learning view serves every
// section of a published course (see CourseRepository.ListSectionsByCourse).
func (r *LearningEventRepository) FindPublishedContentForSkill(ctx context.Context, skillID int64, targetDifficulty float64) (*models.PersonalizedContent, error) {
	var content models.PersonalizedContent
	err := r.db.GetContext(ctx, &content, `
		SELECT sc.id AS content_id, sc.title AS content_title, sc.type AS content_type,
		       c.title AS course_title, COALESCE(cs.difficulty, 0.5) AS difficulty
		FROM content_skills cs
		JOIN section_content sc ON sc.id = cs.content_id AND sc.is_published = true
		JOIN course_sections sec ON sec.id = sc.section_id
		JOIN courses c ON c.id = sec.course_id AND c.status = 'PUBLISHED'
		WHERE cs.skill_id = $1
		ORDER BY ABS(COALESCE(cs.difficulty, 0.5) - $2), sc.order_index
		LIMIT 1`, skillID, targetDifficulty)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &content, nil
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILLS
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) CreateSkill(ctx context.Context, skill *models.Skill) error {
	query := `
		INSERT INTO skills (name, description, parent_skill_id, difficulty)
		VALUES ($1, $2, $3, $4)
		RETURNING id, created_at, updated_at`

	err := r.db.QueryRowContext(
		ctx, query,
		skill.Name, skill.Description, skill.ParentSkillID, skill.Difficulty,
	).Scan(&skill.ID, &skill.CreatedAt, &skill.UpdatedAt)

	return err
}

func (r *LearningEventRepository) GetSkillByID(ctx context.Context, id int64) (*models.Skill, error) {
	var skill models.Skill
	query := `SELECT * FROM skills WHERE id = $1`
	err := r.db.GetContext(ctx, &skill, query, id)
	if err != nil {
		return nil, err
	}
	return &skill, nil
}

func (r *LearningEventRepository) ListSkills(ctx context.Context) ([]models.Skill, error) {
	var skills []models.Skill
	query := `SELECT * FROM skills ORDER BY name`
	err := r.db.SelectContext(ctx, &skills, query)
	if err != nil {
		return nil, err
	}
	return skills, nil
}

func (r *LearningEventRepository) UpdateSkill(ctx context.Context, skill *models.Skill) error {
	query := `
		UPDATE skills
		SET name = $1, description = $2, parent_skill_id = $3, difficulty = $4
		WHERE id = $5
		RETURNING updated_at`

	err := r.db.QueryRowContext(
		ctx, query,
		skill.Name, skill.Description, skill.ParentSkillID, skill.Difficulty, skill.ID,
	).Scan(&skill.UpdatedAt)

	return err
}

func (r *LearningEventRepository) DeleteSkill(ctx context.Context, id int64) error {
	query := `DELETE FROM skills WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL PREREQUISITES
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) AddPrerequisite(ctx context.Context, prereq *models.SkillPrerequisite) error {
	query := `
		INSERT INTO skill_prerequisites (skill_id, prerequisite_skill_id, strength)
		VALUES ($1, $2, $3)
		RETURNING id, created_at`

	err := r.db.QueryRowContext(
		ctx, query,
		prereq.SkillID, prereq.PrerequisiteSkillID, prereq.Strength,
	).Scan(&prereq.ID, &prereq.CreatedAt)

	return err
}

func (r *LearningEventRepository) GetSkillPrerequisites(ctx context.Context, skillID int64) ([]models.SkillPrerequisite, error) {
	var prereqs []models.SkillPrerequisite
	query := `SELECT * FROM skill_prerequisites WHERE skill_id = $1 ORDER BY strength DESC`
	err := r.db.SelectContext(ctx, &prereqs, query, skillID)
	if err != nil {
		return nil, err
	}
	return prereqs, nil
}

func (r *LearningEventRepository) DeletePrerequisite(ctx context.Context, skillID, prerequisiteSkillID int64) error {
	query := `DELETE FROM skill_prerequisites WHERE skill_id = $1 AND prerequisite_skill_id = $2`
	_, err := r.db.ExecContext(ctx, query, skillID, prerequisiteSkillID)
	return err
}

// ══════════════════════════════════════════════════════════════════════════════
// CONTENT SKILLS
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) MapContentToSkill(ctx context.Context, mapping *models.ContentSkill) error {
	query := `
		INSERT INTO content_skills (content_id, skill_id, difficulty, weight)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (content_id, skill_id)
		DO UPDATE SET difficulty = EXCLUDED.difficulty, weight = EXCLUDED.weight
		RETURNING id, created_at`

	err := r.db.QueryRowContext(
		ctx, query,
		mapping.ContentID, mapping.SkillID, mapping.Difficulty, mapping.Weight,
	).Scan(&mapping.ID, &mapping.CreatedAt)

	return err
}

func (r *LearningEventRepository) GetContentSkills(ctx context.Context, contentID int64) ([]models.ContentSkill, error) {
	var mappings []models.ContentSkill
	query := `SELECT * FROM content_skills WHERE content_id = $1`
	err := r.db.SelectContext(ctx, &mappings, query, contentID)
	if err != nil {
		return nil, err
	}
	return mappings, nil
}

func (r *LearningEventRepository) DeleteContentSkill(ctx context.Context, contentID, skillID int64) error {
	query := `DELETE FROM content_skills WHERE content_id = $1 AND skill_id = $2`
	_, err := r.db.ExecContext(ctx, query, contentID, skillID)
	return err
}

// ══════════════════════════════════════════════════════════════════════════════
// QUESTION SKILLS
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) MapQuestionToSkill(ctx context.Context, mapping *models.QuestionSkill) error {
	query := `
		INSERT INTO question_skills (question_id, skill_id, difficulty, weight)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (question_id, skill_id)
		DO UPDATE SET difficulty = EXCLUDED.difficulty, weight = EXCLUDED.weight
		RETURNING id, created_at`

	err := r.db.QueryRowContext(
		ctx, query,
		mapping.QuestionID, mapping.SkillID, mapping.Difficulty, mapping.Weight,
	).Scan(&mapping.ID, &mapping.CreatedAt)

	return err
}

func (r *LearningEventRepository) GetQuestionSkills(ctx context.Context, questionID int64) ([]models.QuestionSkill, error) {
	var mappings []models.QuestionSkill
	query := `SELECT * FROM question_skills WHERE question_id = $1`
	err := r.db.SelectContext(ctx, &mappings, query, questionID)
	if err != nil {
		return nil, err
	}
	return mappings, nil
}

// GetCourseSkillProfile returns the learner's mastery states plus every
// published, skill-mapped content item of the course (with completion flags).
// It is the data foundation for the recommender-service next-best-lesson
// engine and must only be exposed through the internal service API.
func (r *LearningEventRepository) GetCourseSkillProfile(ctx context.Context, studentID, courseID int64) (*models.CourseSkillProfile, error) {
	profile := &models.CourseSkillProfile{
		StudentID:        studentID,
		CourseID:         courseID,
		SkillStates:      []models.LearnerSkillStateWithSkill{},
		AvailableContent: []models.SkillContentCandidate{},
	}

	states, err := r.GetStudentSkillStates(ctx, studentID, strconv.FormatInt(courseID, 10))
	if err != nil {
		return nil, err
	}
	profile.SkillStates = states

	contentQuery := `
		SELECT
			sc.id AS content_id,
			sc.title AS content_title,
			sc.type AS content_type,
			cs.skill_id AS skill_id,
			s.name AS skill_name,
			COALESCE(cs.difficulty, s.difficulty, 0.5) AS difficulty,
			EXISTS (
				SELECT 1 FROM content_progress cp
				WHERE cp.content_id = sc.id AND cp.student_id = $1
			) AS completed
		FROM content_skills cs
		JOIN skills s ON s.id = cs.skill_id
		JOIN section_content sc ON sc.id = cs.content_id AND sc.is_published = true
		JOIN course_sections sec ON sec.id = sc.section_id
		JOIN courses c ON c.id = sec.course_id AND c.status = 'PUBLISHED'
		WHERE sec.course_id = $2
		ORDER BY cs.skill_id, difficulty, sc.order_index`

	if err := r.db.SelectContext(ctx, &profile.AvailableContent, contentQuery, studentID, courseID); err != nil {
		return nil, err
	}
	return profile, nil
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL RECOMMENDATIONS
// ══════════════════════════════════════════════════════════════════════════════

func (r *LearningEventRepository) CreateRecommendation(ctx context.Context, rec *models.SkillRecommendation) error {
	query := `
		INSERT INTO skill_recommendations (
			recommendation_id, student_id, course_id, content_id, skill_id,
			difficulty, reason, recommendation_score
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		RETURNING id, created_at`

	err := r.db.QueryRowContext(
		ctx, query,
		rec.RecommendationID, rec.StudentID, rec.CourseID, rec.ContentID, rec.SkillID,
		rec.Difficulty, rec.Reason, rec.RecommendationScore,
	).Scan(&rec.ID, &rec.CreatedAt)

	return err
}

func (r *LearningEventRepository) UpdateRecommendationClick(ctx context.Context, recommendationID string, studentID int64) error {
	query := `
		UPDATE skill_recommendations
		SET clicked = true, clicked_at = CURRENT_TIMESTAMP
		WHERE recommendation_id = $1 AND student_id = $2`

	_, err := r.db.ExecContext(ctx, query, recommendationID, studentID)
	return err
}

func (r *LearningEventRepository) UpdateRecommendationCompletion(ctx context.Context, recommendationID string, studentID int64) error {
	query := `
		UPDATE skill_recommendations
		SET completed = true, completed_at = CURRENT_TIMESTAMP
		WHERE recommendation_id = $1 AND student_id = $2`

	_, err := r.db.ExecContext(ctx, query, recommendationID, studentID)
	return err
}

func (r *LearningEventRepository) GetStudentRecommendations(ctx context.Context, studentID int64, limit int) ([]models.SkillRecommendationWithDetails, error) {
	query := `
		SELECT
			sr.*,
			sc.title as content_title,
			s.name as skill_name,
			c.title as course_name
		FROM skill_recommendations sr
		LEFT JOIN section_content sc ON sr.content_id = sc.id
		LEFT JOIN skills s ON sr.skill_id = s.id
		LEFT JOIN courses c ON sr.course_id = c.id
		WHERE sr.student_id = $1
		ORDER BY sr.created_at DESC
		LIMIT $2`

	var recommendations []models.SkillRecommendationWithDetails
	err := r.db.SelectContext(ctx, &recommendations, query, studentID, limit)
	if err != nil {
		return nil, err
	}
	return recommendations, nil
}

// ══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ══════════════════════════════════════════════════════════════════════════════

// GetEventMetadata unmarshals the metadata JSON
func GetEventMetadata(event *models.LearningEvent) (map[string]interface{}, error) {
	if event.Metadata == nil {
		return nil, nil
	}
	var metadata map[string]interface{}
	err := json.Unmarshal(event.Metadata, &metadata)
	return metadata, err
}
