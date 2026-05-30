package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

// MicroInteractionRepository owns the raw `micro_lesson_interactions`
// log and the materialised `knowledge_node_mastery` table that backs
// the heatmap endpoint.
type MicroInteractionRepository struct {
	db *sql.DB
}

func NewMicroInteractionRepository(db *sql.DB) *MicroInteractionRepository {
	return &MicroInteractionRepository{db: db}
}

// ── Raw log ────────────────────────────────────────────────────────

// Insert appends a raw interaction row and returns the generated id +
// created_at so the producer can include them in the Kafka event.
func (r *MicroInteractionRepository) Insert(ctx context.Context, m *models.MicroLessonInteraction) (*models.MicroLessonInteraction, error) {
	const q = `
		INSERT INTO micro_lesson_interactions
			(user_id, course_id, lesson_id, node_id, action_type, score, status, payload)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		RETURNING id, created_at
	`
	if len(m.Payload) == 0 {
		m.Payload = []byte(`{}`)
	}
	if err := r.db.QueryRowContext(ctx, q,
		m.UserID, m.CourseID, m.LessonID, m.NodeID,
		m.ActionType, m.Score, m.Status, string(m.Payload),
	).Scan(&m.ID, &m.CreatedAt); err != nil {
		return nil, fmt.Errorf("insert micro_lesson_interactions: %w", err)
	}
	return m, nil
}

// ── Mastery aggregation ────────────────────────────────────────────

// MasteryComponentDelta is what the analytics worker passes when it
// processes an interaction. Only the fields that need to move are
// populated; all other components are left untouched.
type MasteryComponentDelta struct {
	UserID   int64
	CourseID int64
	NodeID   int64

	FormalQuizSample *float64
	MiniQuizSample   *float64
	CompletionSample *float64
	EngagementSample *float64
}

// ApplyDelta upserts a row into knowledge_node_mastery, blending the
// new sample into the running average for the appropriate component.
// All four component scores are then weighted into mastery_level.
//
// Weights: formal quiz 60%, mini quiz 20%, completion 10%, engagement 10%.
//
// We use Postgres CTEs to compute the new running averages atomically.
func (r *MicroInteractionRepository) ApplyDelta(ctx context.Context, d MasteryComponentDelta) error {
	const q = `
		INSERT INTO knowledge_node_mastery
			(user_id, course_id, node_id,
			 formal_quiz_score, formal_quiz_count,
			 mini_quiz_score,   mini_quiz_count,
			 completion_score,  completion_count,
			 engagement_score,  engagement_count,
			 mastery_level,
			 last_interaction_at, updated_at)
		VALUES ($1, $2, $3,
			COALESCE($4::double precision, 0.0), CASE WHEN $4 IS NULL THEN 0 ELSE 1 END,
			COALESCE($5::double precision, 0.0), CASE WHEN $5 IS NULL THEN 0 ELSE 1 END,
			COALESCE($6::double precision, 0.0), CASE WHEN $6 IS NULL THEN 0 ELSE 1 END,
			COALESCE($7::double precision, 0.0), CASE WHEN $7 IS NULL THEN 0 ELSE 1 END,
			0,
			CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
		ON CONFLICT (user_id, course_id, node_id) DO UPDATE SET
			formal_quiz_score = CASE
				WHEN $4 IS NULL THEN knowledge_node_mastery.formal_quiz_score
				ELSE (knowledge_node_mastery.formal_quiz_score * knowledge_node_mastery.formal_quiz_count + $4::double precision)
				     / (knowledge_node_mastery.formal_quiz_count + 1)
			END,
			formal_quiz_count = knowledge_node_mastery.formal_quiz_count
			                    + CASE WHEN $4 IS NULL THEN 0 ELSE 1 END,
			mini_quiz_score = CASE
				WHEN $5 IS NULL THEN knowledge_node_mastery.mini_quiz_score
				ELSE (knowledge_node_mastery.mini_quiz_score * knowledge_node_mastery.mini_quiz_count + $5::double precision)
				     / (knowledge_node_mastery.mini_quiz_count + 1)
			END,
			mini_quiz_count = knowledge_node_mastery.mini_quiz_count
			                    + CASE WHEN $5 IS NULL THEN 0 ELSE 1 END,
			completion_score = CASE
				WHEN $6 IS NULL THEN knowledge_node_mastery.completion_score
				ELSE (knowledge_node_mastery.completion_score * knowledge_node_mastery.completion_count + $6::double precision)
				     / (knowledge_node_mastery.completion_count + 1)
			END,
			completion_count = knowledge_node_mastery.completion_count
			                    + CASE WHEN $6 IS NULL THEN 0 ELSE 1 END,
			engagement_score = CASE
				WHEN $7 IS NULL THEN knowledge_node_mastery.engagement_score
				ELSE (knowledge_node_mastery.engagement_score * knowledge_node_mastery.engagement_count + $7::double precision)
				     / (knowledge_node_mastery.engagement_count + 1)
			END,
			engagement_count = knowledge_node_mastery.engagement_count
			                    + CASE WHEN $7 IS NULL THEN 0 ELSE 1 END,
			last_interaction_at = CURRENT_TIMESTAMP,
			updated_at          = CURRENT_TIMESTAMP
	`
	if _, err := r.db.ExecContext(ctx, q,
		d.UserID, d.CourseID, d.NodeID,
		d.FormalQuizSample, d.MiniQuizSample,
		d.CompletionSample, d.EngagementSample,
	); err != nil {
		return fmt.Errorf("apply mastery delta: %w", err)
	}

	// Recompute the weighted mastery_level in a separate, single statement
	// so the math lives next to the weights, not buried in the upsert.
	const recompute = `
		UPDATE knowledge_node_mastery SET
			mastery_level =
				$4 * formal_quiz_score +
				$5 * mini_quiz_score   +
				$6 * completion_score  +
				$7 * engagement_score
		WHERE user_id = $1 AND course_id = $2 AND node_id = $3
	`
	if _, err := r.db.ExecContext(ctx, recompute,
		d.UserID, d.CourseID, d.NodeID,
		WeightFormalQuiz, WeightMiniQuiz, WeightCompletion, WeightEngagement,
	); err != nil {
		return fmt.Errorf("recompute mastery_level: %w", err)
	}
	return nil
}

// Heatmap aggregates per-node averages across all enrolled students for a
// course. The query reads from the materialised mastery table so no
// online recomputation happens — heatmap latency stays O(N nodes).
func (r *MicroInteractionRepository) Heatmap(ctx context.Context, courseID int64) ([]dto.HeatmapNodeMastery, error) {
	const q = `
		SELECT
			node_id,
			COUNT(DISTINCT user_id)        AS user_count,
			AVG(mastery_level)             AS mastery_level,
			AVG(formal_quiz_score)         AS formal_quiz_score,
			AVG(mini_quiz_score)           AS mini_quiz_score,
			AVG(completion_score)          AS completion_score,
			AVG(engagement_score)          AS engagement_score,
			MAX(last_interaction_at)       AS last_interaction_at
		FROM knowledge_node_mastery
		WHERE course_id = $1
		GROUP BY node_id
		ORDER BY mastery_level ASC, node_id ASC
	`
	rows, err := r.db.QueryContext(ctx, q, courseID)
	if err != nil {
		return nil, fmt.Errorf("heatmap query: %w", err)
	}
	defer rows.Close()

	out := make([]dto.HeatmapNodeMastery, 0)
	for rows.Next() {
		var item dto.HeatmapNodeMastery
		if err := rows.Scan(
			&item.NodeID, &item.UserCount,
			&item.MasteryLevel,
			&item.FormalQuizScore, &item.MiniQuizScore,
			&item.CompletionScore, &item.EngagementScore,
			&item.LastInteractionAt,
		); err != nil {
			return nil, fmt.Errorf("heatmap scan: %w", err)
		}
		item.StatusLevel = MasteryStatusLabel(item.MasteryLevel)
		out = append(out, item)
	}
	return out, rows.Err()
}

// StudentHeatmap is the same shape as Heatmap but filtered to a single
// student. Used by the student-side dashboard.
func (r *MicroInteractionRepository) StudentHeatmap(ctx context.Context, courseID, userID int64) ([]dto.HeatmapNodeMastery, error) {
	const q = `
		SELECT
			node_id,
			1                              AS user_count,
			mastery_level,
			formal_quiz_score, mini_quiz_score,
			completion_score,  engagement_score,
			last_interaction_at
		FROM knowledge_node_mastery
		WHERE course_id = $1 AND user_id = $2
		ORDER BY mastery_level ASC, node_id ASC
	`
	rows, err := r.db.QueryContext(ctx, q, courseID, userID)
	if err != nil {
		return nil, fmt.Errorf("student heatmap query: %w", err)
	}
	defer rows.Close()

	out := make([]dto.HeatmapNodeMastery, 0)
	for rows.Next() {
		var item dto.HeatmapNodeMastery
		if err := rows.Scan(
			&item.NodeID, &item.UserCount,
			&item.MasteryLevel,
			&item.FormalQuizScore, &item.MiniQuizScore,
			&item.CompletionScore, &item.EngagementScore,
			&item.LastInteractionAt,
		); err != nil {
			return nil, fmt.Errorf("student heatmap scan: %w", err)
		}
		item.StatusLevel = MasteryStatusLabel(item.MasteryLevel)
		out = append(out, item)
	}
	return out, rows.Err()
}
