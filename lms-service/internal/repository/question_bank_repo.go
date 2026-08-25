// lms-service/internal/repository/question_bank_repo.go
package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"example/hello/internal/dto"
	"example/hello/internal/models"

	"github.com/lib/pq"
)

// QuestionBankRepository - data access for the per-course question library.
// Uses database/sql + pgx stdlib (project convention), LIMIT/OFFSET
// pagination consistent with course_repo/organization_repo.
type QuestionBankRepository struct {
	db *sql.DB
}

func NewQuestionBankRepository(db *sql.DB) *QuestionBankRepository {
	return &QuestionBankRepository{db: db}
}

const bankColumns = `
	id, course_id, node_id, source_quiz_id, question_type, question_text,
	explanation, points, bloom_level, difficulty,
	answer_options, correct_answers, settings, tags,
	source, status, created_by, created_at, updated_at
`

func scanBankItem(row interface{ Scan(...interface{}) error }) (*models.QuestionBankItem, error) {
	item := &models.QuestionBankItem{}
	err := row.Scan(
		&item.ID, &item.CourseID, &item.NodeID, &item.SourceQuizID,
		&item.QuestionType, &item.QuestionText, &item.Explanation,
		&item.Points, &item.BloomLevel, &item.Difficulty,
		&item.AnswerOptions, &item.CorrectAnswers, &item.Settings,
		pq.Array(&item.Tags),
		&item.Source, &item.Status, &item.CreatedBy, &item.CreatedAt, &item.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return item, nil
}

// Create inserts one item and returns its ID.
func (r *QuestionBankRepository) Create(ctx context.Context, item *models.QuestionBankItem) (int64, error) {
	var id int64
	err := r.db.QueryRowContext(ctx, `
		INSERT INTO question_bank_items (
			course_id, node_id, source_quiz_id, question_type, question_text,
			explanation, points, bloom_level, difficulty,
			answer_options, correct_answers, settings, tags,
			source, status, created_by
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
		RETURNING id
	`,
		item.CourseID, item.NodeID, item.SourceQuizID, item.QuestionType,
		item.QuestionText, item.Explanation, item.Points, item.BloomLevel,
		item.Difficulty, item.AnswerOptions, item.CorrectAnswers,
		item.Settings, pq.Array(item.Tags), item.Source, item.Status, item.CreatedBy,
	).Scan(&id)
	return id, err
}

// List applies filters + pagination; returns items and total count.
func (r *QuestionBankRepository) List(ctx context.Context, courseID int64, q dto.BankListQuery, limit, offset int) ([]*models.QuestionBankItem, int64, error) {
	where := []string{"course_id = $1"}
	args := []interface{}{courseID}
	argN := 1

	addArg := func(v interface{}) string {
		argN++
		args = append(args, v)
		return fmt.Sprintf("$%d", argN)
	}

	if q.Difficulty != "" {
		where = append(where, "difficulty = "+addArg(q.Difficulty))
	}
	if q.BloomLevel != "" {
		where = append(where, "bloom_level = "+addArg(q.BloomLevel))
	}
	if q.NodeID != nil && !q.Dangling {
		where = append(where, "node_id = "+addArg(*q.NodeID))
	}
	if q.Dangling {
		where = append(where, "node_id IS NULL")
	}
	if q.Source != "" {
		where = append(where, "source = "+addArg(q.Source))
	}
	// Default view hides DISABLED items unless explicitly requested.
	switch q.Status {
	case "":
		where = append(where, "status <> 'DISABLED'")
	default:
		where = append(where, "status = "+addArg(q.Status))
	}
	if q.TimeFrom != "" {
		where = append(where, "created_at >= "+addArg(q.TimeFrom)+"::timestamptz")
	}
	if q.TimeTo != "" {
		where = append(where, "created_at < ("+addArg(q.TimeTo)+"::timestamptz + interval '1 day')")
	}
	if search := strings.TrimSpace(q.Q); search != "" {
		where = append(where, "to_tsvector('simple', question_text) @@ plainto_tsquery('simple', "+addArg(search)+")")
	}

	whereSQL := strings.Join(where, " AND ")

	// Deterministic secondary sort by id keeps pagination stable.
	sortCol := "created_at"
	switch q.Sort {
	case "points":
		sortCol = "points"
	case "difficulty":
		// Semantic order EASY -> MEDIUM -> HARD, not alphabetical.
		sortCol = "CASE difficulty WHEN 'EASY' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END"
	case "bloom":
		sortCol = `CASE bloom_level
			WHEN 'remember' THEN 0 WHEN 'understand' THEN 1 WHEN 'apply' THEN 2
			WHEN 'analyze' THEN 3 WHEN 'evaluate' THEN 4 ELSE 5 END`
	}
	orderDir := "DESC"
	if strings.EqualFold(q.Order, "asc") {
		orderDir = "ASC"
	}

	var total int64
	if err := r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM question_bank_items WHERE "+whereSQL, args...,
	).Scan(&total); err != nil {
		return nil, 0, err
	}

	query := fmt.Sprintf(
		"SELECT %s FROM question_bank_items WHERE %s ORDER BY %s %s, id %s LIMIT $%d OFFSET $%d",
		bankColumns, whereSQL, sortCol, orderDir, orderDir, argN+1, argN+2,
	)
	args = append(args, limit, offset)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	items := make([]*models.QuestionBankItem, 0, limit)
	for rows.Next() {
		item, err := scanBankItem(rows)
		if err != nil {
			return nil, 0, err
		}
		items = append(items, item)
	}
	return items, total, rows.Err()
}

// GetByID fetches a single item (ownership enforced upstream).
func (r *QuestionBankRepository) GetByID(ctx context.Context, itemID int64) (*models.QuestionBankItem, error) {
	row := r.db.QueryRowContext(ctx,
		"SELECT "+bankColumns+" FROM question_bank_items WHERE id = $1", itemID)
	item, err := scanBankItem(row)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("question bank item not found")
	}
	return item, err
}

// GetByIDs preserves caller order for quiz assembly.
func (r *QuestionBankRepository) GetByIDs(ctx context.Context, ids []int64) ([]*models.QuestionBankItem, error) {
	query := "SELECT " + bankColumns + " FROM question_bank_items WHERE id = ANY($1)"
	rows, err := r.db.QueryContext(ctx, query, pq.Array(ids))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	byID := make(map[int64]*models.QuestionBankItem, len(ids))
	for rows.Next() {
		item, err := scanBankItem(rows)
		if err != nil {
			return nil, err
		}
		byID[item.ID] = item
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	out := make([]*models.QuestionBankItem, 0, len(ids))
	for _, id := range ids {
		if item, ok := byID[id]; ok {
			out = append(out, item)
		}
	}
	return out, nil
}

// CountByIDs verifies ownership of every requested id in ONE query.
func (r *QuestionBankRepository) CountByIDsInCourse(ctx context.Context, ids []int64, courseID int64) (int64, error) {
	var n int64
	err := r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM question_bank_items WHERE id = ANY($1) AND course_id = $2",
		pq.Array(ids), courseID,
	).Scan(&n)
	return n, err
}

func (r *QuestionBankRepository) Update(ctx context.Context, itemID int64, req dto.UpdateBankItemRequest) (*models.QuestionBankItem, error) {
	sets := []string{"updated_at = CURRENT_TIMESTAMP"}
	args := []interface{}{}
	argN := 0

	addArg := func(v interface{}) string {
		argN++
		args = append(args, v)
		return fmt.Sprintf("$%d", argN)
	}

	if req.ClearNode {
		sets = append(sets, "node_id = NULL")
	} else if req.NodeID != nil {
		sets = append(sets, "node_id = "+addArg(*req.NodeID))
	}
	if req.Difficulty != "" {
		sets = append(sets, "difficulty = "+addArg(req.Difficulty))
	}
	if req.BloomLevel != nil {
		sets = append(sets, "bloom_level = "+addArg(*req.BloomLevel))
	}
	if req.Points != nil {
		sets = append(sets, "points = "+addArg(*req.Points))
	}
	if req.Status != nil {
		sets = append(sets, "status = "+addArg(*req.Status))
	}
	if req.Tags != nil {
		sets = append(sets, "tags = "+addArg(pq.Array(*req.Tags)))
	}
	if req.Explanation != nil {
		sets = append(sets, "explanation = "+addArg(*req.Explanation))
	}

	args = append(args, itemID)
	query := fmt.Sprintf(
		"UPDATE question_bank_items SET %s WHERE id = $%d RETURNING %s",
		strings.Join(sets, ", "), argN+1, bankColumns,
	)
	row := r.db.QueryRowContext(ctx, query, args...)
	item, err := scanBankItem(row)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("question bank item not found")
	}
	return item, err
}

func (r *QuestionBankRepository) Delete(ctx context.Context, itemID int64) error {
	res, err := r.db.ExecContext(ctx, "DELETE FROM question_bank_items WHERE id = $1", itemID)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return fmt.Errorf("question bank item not found")
	}
	return nil
}

// Stats returns facet counts in 4 grouped queries (all index-backed).
func (r *QuestionBankRepository) Stats(ctx context.Context, courseID int64) (*dto.BankStatsResponse, error) {
	stats := &dto.BankStatsResponse{
		ByDifficulty: map[string]int64{},
		ByBloom:      map[string]int64{},
		BySource:     map[string]int64{},
		ByMonth:      []dto.BankMonthCount{},
	}

	if err := r.db.QueryRowContext(ctx,
		`SELECT COUNT(*),
		        COALESCE(SUM(CASE WHEN node_id IS NULL THEN 1 ELSE 0 END), 0)
		 FROM question_bank_items WHERE course_id = $1 AND status <> 'DISABLED'`,
		courseID,
	).Scan(&stats.Total, &stats.DanglingCount); err != nil {
		return nil, err
	}

	scanGroups := func(query string, dest map[string]int64) error {
		rows, err := r.db.QueryContext(ctx, query, courseID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var k string
			var v int64
			if err := rows.Scan(&k, &v); err != nil {
				return err
			}
			dest[k] = v
		}
		return rows.Err()
	}

	base := "FROM question_bank_items WHERE course_id = $1 AND status <> 'DISABLED'"
	if err := scanGroups("SELECT difficulty, COUNT(*) "+base+" GROUP BY difficulty", stats.ByDifficulty); err != nil {
		return nil, err
	}
	if err := scanGroups(`SELECT COALESCE(bloom_level,'none'), COUNT(*) `+base+` GROUP BY bloom_level`, stats.ByBloom); err != nil {
		return nil, err
	}
	if err := scanGroups("SELECT source, COUNT(*) "+base+" GROUP BY source", stats.BySource); err != nil {
		return nil, err
	}

	rows, err := r.db.QueryContext(ctx, `
		SELECT to_char(created_at, 'YYYY-MM') AS month, COUNT(*) AS cnt
		FROM question_bank_items
		WHERE course_id = $1 AND status <> 'DISABLED'
		  AND created_at >= NOW() - INTERVAL '12 months'
		GROUP BY month ORDER BY month`, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var mc dto.BankMonthCount
		if err := rows.Scan(&mc.Month, &mc.Count); err != nil {
			return nil, err
		}
		stats.ByMonth = append(stats.ByMonth, mc)
	}
	return stats, rows.Err()
}

// MarshalJSONField helper used by the service layer.
func MarshalJSONField(v interface{}) ([]byte, error) {
	if v == nil {
		return []byte("null"), nil
	}
	b, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	return b, nil
}

// RecentTexts returns the newest question texts for anti-duplication context.
func (r *QuestionBankRepository) RecentTexts(ctx context.Context, courseID int64, limit int) ([]string, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT question_text FROM question_bank_items
		WHERE course_id = $1 AND status <> 'DISABLED'
		ORDER BY created_at DESC, id DESC
		LIMIT $2`, courseID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]string, 0, limit)
	for rows.Next() {
		var t string
		if err := rows.Scan(&t); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}
