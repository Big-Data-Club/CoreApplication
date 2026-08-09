package repository

import (
	"context"
	"database/sql"
	"time"

	"github.com/lib/pq"
)

// ─── Result types ─────────────────────────────────────────────────────────────

type CourseProgressResult struct {
	TotalMandatory      int
	CompletedCount      int
	ProgressPercent     float64
	CompletedContentIDs []int64
	LastActivityAt      *time.Time
	NewContentCount     int
}

type ProgressDetailRow struct {
	ContentID    int64
	ContentTitle string
	ContentType  string
	SectionTitle string
	IsMandatory  bool
	IsCompleted  bool
	CompletedAt  *time.Time
}

// ─── Repository ───────────────────────────────────────────────────────────────

type ProgressRepository struct {
	db *sql.DB
}

func NewProgressRepository(db *sql.DB) *ProgressRepository {
	return &ProgressRepository{db: db}
}

// MarkComplete records that a student completed a content item.
// Duplicate marks are silently ignored (ON CONFLICT DO NOTHING).
func (r *ProgressRepository) MarkComplete(ctx context.Context, contentID, studentID int64) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO content_progress (content_id, student_id)
		VALUES ($1, $2)
		ON CONFLICT (content_id, student_id) DO NOTHING
	`, contentID, studentID)
	return err
}

// IsCompleted checks whether a student already completed a content item.
func (r *ProgressRepository) IsCompleted(ctx context.Context, contentID, studentID int64) (bool, error) {
	var exists bool
	err := r.db.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM content_progress
			WHERE content_id = $1 AND student_id = $2
		)
	`, contentID, studentID).Scan(&exists)
	return exists, err
}

// GetCourseProgress returns progress summary (counts + completed IDs) for a
// student inside a course. Only mandatory content items are counted.
func (r *ProgressRepository) GetCourseProgress(ctx context.Context, courseID, studentID int64) (*CourseProgressResult, error) {
	result := &CourseProgressResult{}

	// 1. Aggregate counts
	err := r.db.QueryRowContext(ctx, `
		SELECT
			COUNT(sc.id) FILTER (WHERE sc.is_mandatory = TRUE)                                        AS total_mandatory,
			COUNT(cp.content_id) FILTER (WHERE sc.is_mandatory = TRUE AND cp.id IS NOT NULL)          AS completed_count
		FROM course_sections cs
		JOIN section_content sc ON sc.section_id = cs.id
		LEFT JOIN content_progress cp
			ON cp.content_id = sc.id
			AND cp.student_id = $2
		WHERE cs.course_id = $1
	`, courseID, studentID).Scan(&result.TotalMandatory, &result.CompletedCount)
	if err != nil {
		return nil, err
	}

	if result.TotalMandatory > 0 {
		result.ProgressPercent = float64(result.CompletedCount) / float64(result.TotalMandatory) * 100
	}

	// 2. Collect completed content IDs
	rows, err := r.db.QueryContext(ctx, `
		SELECT cp.content_id
		FROM content_progress cp
		JOIN section_content sc ON sc.id = cp.content_id
		JOIN course_sections cs ON cs.id = sc.section_id
		WHERE cs.course_id = $1
		  AND cp.student_id = $2
	`, courseID, studentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	ids := make([]int64, 0)
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	result.CompletedContentIDs = ids
	return result, nil
}

// GetBatchCourseProgress returns progress summaries for a student across
// multiple courses in a single query, eliminating the N+1 pattern that
// existed when GetCourseProgress was called inside a loop.
func (r *ProgressRepository) GetBatchCourseProgress(
	ctx context.Context,
	courseIDs []int64,
	studentID int64,
) (map[int64]*CourseProgressResult, error) {
	result := make(map[int64]*CourseProgressResult, len(courseIDs))
	if len(courseIDs) == 0 {
		return result, nil
	}

	// Single query: aggregate progress plus source-grounded freshness signals.
	// "New content" means published content created after the learner's latest
	// completion in that course (or after enrollment when nothing is complete).
	rows, err := r.db.QueryContext(ctx, `
		WITH activity_anchor AS (
			SELECT
				e.course_id,
				COALESCE(MAX(cp.completed_at), MAX(e.accepted_at), MAX(e.enrolled_at)) AS activity_at
			FROM enrollments e
			LEFT JOIN course_sections anchor_cs ON anchor_cs.course_id = e.course_id
			LEFT JOIN section_content anchor_sc ON anchor_sc.section_id = anchor_cs.id
			LEFT JOIN content_progress cp
				ON cp.content_id = anchor_sc.id
				AND cp.student_id = e.student_id
			WHERE e.student_id = $1
			  AND e.course_id = ANY($2)
			GROUP BY e.course_id
		)
		SELECT
			cs.course_id,
			COUNT(sc.id)        FILTER (WHERE sc.is_mandatory)              AS total_mandatory,
			COUNT(cp.content_id) FILTER (WHERE sc.is_mandatory
			                               AND cp.id IS NOT NULL)           AS completed_count,
			aa.activity_at,
			COUNT(sc.id) FILTER (
				WHERE cs.is_published
				  AND sc.is_published
				  AND aa.activity_at IS NOT NULL
				  AND sc.created_at > aa.activity_at
			) AS new_content_count
		FROM course_sections  cs
		JOIN section_content  sc ON sc.section_id = cs.id
		LEFT JOIN activity_anchor aa ON aa.course_id = cs.course_id
		LEFT JOIN content_progress cp
			ON  cp.content_id = sc.id
			AND cp.student_id = $1
		WHERE cs.course_id = ANY($2)
		GROUP BY cs.course_id, aa.activity_at
	`, studentID, pq.Array(courseIDs))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var (
			courseID       int64
			totalMandatory int
			completedCount int
			lastActivity   sql.NullTime
			newContent     int
		)
		if err := rows.Scan(&courseID, &totalMandatory, &completedCount, &lastActivity, &newContent); err != nil {
			return nil, err
		}

		pct := 0.0
		if totalMandatory > 0 {
			pct = float64(completedCount) / float64(totalMandatory) * 100
		}
		progress := &CourseProgressResult{
			TotalMandatory:      totalMandatory,
			CompletedCount:      completedCount,
			ProgressPercent:     pct,
			CompletedContentIDs: nil,
			NewContentCount:     newContent,
		}
		if lastActivity.Valid {
			activityAt := lastActivity.Time
			progress.LastActivityAt = &activityAt
		}
		result[courseID] = progress
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// Ensure every requested courseID has an entry (avoids nil checks in caller)
	for _, id := range courseIDs {
		if _, ok := result[id]; !ok {
			result[id] = &CourseProgressResult{}
		}
	}

	return result, nil
}

// GetCourseProgressDetail returns every content item in a course with its
// completion status for the given student, ordered by section/content index.
func (r *ProgressRepository) GetCourseProgressDetail(ctx context.Context, courseID, studentID int64) ([]ProgressDetailRow, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT
			sc.id                 AS content_id,
			sc.title              AS content_title,
			sc.type               AS content_type,
			cs.title              AS section_title,
			sc.is_mandatory,
			(cp.id IS NOT NULL)   AS is_completed,
			cp.completed_at
		FROM course_sections cs
		JOIN section_content sc ON sc.section_id = cs.id
		LEFT JOIN content_progress cp
			ON cp.content_id = sc.id
			AND cp.student_id = $2
		WHERE cs.course_id = $1
		ORDER BY cs.order_index ASC, sc.order_index ASC
	`, courseID, studentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []ProgressDetailRow
	for rows.Next() {
		var item ProgressDetailRow
		if err := rows.Scan(
			&item.ContentID,
			&item.ContentTitle,
			&item.ContentType,
			&item.SectionTitle,
			&item.IsMandatory,
			&item.IsCompleted,
			&item.CompletedAt,
		); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// GetContentCourseID resolves the course_id for a content item.
// Returns 0, nil when not found.
func (r *ProgressRepository) GetContentCourseID(ctx context.Context, contentID int64) (int64, error) {
	var courseID int64
	err := r.db.QueryRowContext(ctx, `
		SELECT cs.course_id
		FROM section_content sc
		JOIN course_sections cs ON cs.id = sc.section_id
		WHERE sc.id = $1
	`, contentID).Scan(&courseID)
	if err == sql.ErrNoRows {
		return 0, nil
	}
	return courseID, err
}

// GetContentIsMandatory returns whether a content item is mandatory.
// Returns false, nil when not found.
func (r *ProgressRepository) GetContentIsMandatory(ctx context.Context, contentID int64) (bool, error) {
	var mandatory bool
	err := r.db.QueryRowContext(ctx,
		`SELECT is_mandatory FROM section_content WHERE id = $1`, contentID,
	).Scan(&mandatory)
	if err == sql.ErrNoRows {
		return false, nil
	}
	return mandatory, err
}
