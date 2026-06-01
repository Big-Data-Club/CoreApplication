package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"lab-service/internal/dto"
)

type LabRepository struct{ db *sql.DB }

func NewLabRepository(db *sql.DB) *LabRepository {
	return &LabRepository{db: db}
}

// ── Lab CRUD ────────────────────────────────────────────────────

func (r *LabRepository) Create(ctx context.Context, req *dto.CreateLabRequest, userID int64) (*dto.LabResponse, error) {
	runtimeJSON, _ := json.Marshal(req.RuntimeConfig)
	gradingJSON, _ := json.Marshal(req.GradingConfig)

	maxSess := req.MaxSessionDurationMin
	if maxSess == 0 {
		maxSess = 120
	}
	maxConc := req.MaxConcurrentSessions
	if maxConc == 0 {
		maxConc = 50
	}

	var resp dto.LabResponse
	var runtimeRaw, gradingRaw []byte

	err := r.db.QueryRowContext(ctx,
		`INSERT INTO labs (title, description, category, level, thumbnail_url,
			lab_type, runtime_config, max_session_duration_min, max_concurrent_sessions,
			max_submissions, auto_grade, grading_config, start_time, deadline,
			allow_late_submission, late_penalty_percent, created_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
		RETURNING id, title, description, category, level, thumbnail_url,
			lab_type, status, runtime_config, max_session_duration_min,
			max_concurrent_sessions, max_submissions, auto_grade, grading_config,
			start_time, deadline, allow_late_submission, late_penalty_percent,
			created_by, published_at, created_at, updated_at`,
		req.Title, req.Description, req.Category, req.Level, req.ThumbnailURL,
		req.LabType, runtimeJSON, maxSess, maxConc,
		req.MaxSubmissions, req.AutoGrade, gradingJSON, req.StartTime, req.Deadline,
		req.AllowLateSubmission, req.LatePenaltyPercent, userID,
	).Scan(
		&resp.ID, &resp.Title, &resp.Description, &resp.Category, &resp.Level,
		&resp.ThumbnailURL, &resp.LabType, &resp.Status, &runtimeRaw,
		&resp.MaxSessionDurationMin, &resp.MaxConcurrentSessions, &resp.MaxSubmissions,
		&resp.AutoGrade, &gradingRaw, &resp.StartTime, &resp.Deadline,
		&resp.AllowLateSubmission, &resp.LatePenaltyPercent, &resp.CreatedBy,
		&resp.PublishedAt, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("create lab: %w", err)
	}

	json.Unmarshal(runtimeRaw, &resp.RuntimeConfig)
	json.Unmarshal(gradingRaw, &resp.GradingConfig)
	return &resp, nil
}

func (r *LabRepository) GetByID(ctx context.Context, labID int64) (*dto.LabResponse, error) {
	var resp dto.LabResponse
	var runtimeRaw, gradingRaw []byte

	err := r.db.QueryRowContext(ctx,
		`SELECT l.id, l.title, l.description, l.category, l.level, l.thumbnail_url,
			l.lab_type, l.status, l.runtime_config, l.max_session_duration_min,
			l.max_concurrent_sessions, l.max_submissions, l.auto_grade, l.grading_config,
			l.start_time, l.deadline, l.allow_late_submission, l.late_penalty_percent,
			l.created_by, u.full_name, u.email, l.published_at, l.created_at, l.updated_at,
			COALESCE((SELECT COUNT(*) FROM lab_enrollments WHERE lab_id = l.id AND status = 'ACCEPTED'), 0)
		FROM labs l
		LEFT JOIN users u ON u.id = l.created_by
		WHERE l.id = $1`, labID,
	).Scan(
		&resp.ID, &resp.Title, &resp.Description, &resp.Category, &resp.Level,
		&resp.ThumbnailURL, &resp.LabType, &resp.Status, &runtimeRaw,
		&resp.MaxSessionDurationMin, &resp.MaxConcurrentSessions, &resp.MaxSubmissions,
		&resp.AutoGrade, &gradingRaw, &resp.StartTime, &resp.Deadline,
		&resp.AllowLateSubmission, &resp.LatePenaltyPercent, &resp.CreatedBy,
		&resp.CreatorName, &resp.CreatorEmail, &resp.PublishedAt,
		&resp.CreatedAt, &resp.UpdatedAt, &resp.EnrollmentCount,
	)
	if err != nil {
		return nil, fmt.Errorf("get lab by id: %w", err)
	}

	json.Unmarshal(runtimeRaw, &resp.RuntimeConfig)
	json.Unmarshal(gradingRaw, &resp.GradingConfig)
	return &resp, nil
}

func (r *LabRepository) ListPublished(ctx context.Context, labType, category, level, search string, limit, offset int) ([]dto.LabResponse, int, error) {
	where := []string{"l.status = 'PUBLISHED'"}
	args := []interface{}{}
	idx := 1

	if labType != "" {
		where = append(where, fmt.Sprintf("l.lab_type = $%d", idx))
		args = append(args, labType)
		idx++
	}
	if category != "" {
		where = append(where, fmt.Sprintf("l.category = $%d", idx))
		args = append(args, category)
		idx++
	}
	if level != "" {
		where = append(where, fmt.Sprintf("l.level = $%d", idx))
		args = append(args, level)
		idx++
	}
	if search != "" {
		where = append(where, fmt.Sprintf("(l.title ILIKE $%d OR l.description ILIKE $%d)", idx, idx))
		args = append(args, "%"+search+"%")
		idx++
	}

	whereClause := strings.Join(where, " AND ")

	// Count total
	var total int
	countQ := "SELECT COUNT(*) FROM labs l WHERE " + whereClause
	r.db.QueryRowContext(ctx, countQ, args...).Scan(&total)

	// Fetch page
	args = append(args, limit, offset)
	query := fmt.Sprintf(
		`SELECT l.id, l.title, l.description, l.category, l.level, l.thumbnail_url,
			l.lab_type, l.status, l.max_session_duration_min, l.auto_grade,
			l.created_by, u.full_name, l.published_at, l.created_at, l.updated_at,
			COALESCE((SELECT COUNT(*) FROM lab_enrollments WHERE lab_id = l.id AND status = 'ACCEPTED'), 0)
		FROM labs l
		LEFT JOIN users u ON u.id = l.created_by
		WHERE %s
		ORDER BY l.published_at DESC NULLS LAST
		LIMIT $%d OFFSET $%d`, whereClause, idx, idx+1)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("list published labs: %w", err)
	}
	defer rows.Close()

	var labs []dto.LabResponse
	for rows.Next() {
		var lab dto.LabResponse
		rows.Scan(
			&lab.ID, &lab.Title, &lab.Description, &lab.Category, &lab.Level,
			&lab.ThumbnailURL, &lab.LabType, &lab.Status, &lab.MaxSessionDurationMin,
			&lab.AutoGrade, &lab.CreatedBy, &lab.CreatorName,
			&lab.PublishedAt, &lab.CreatedAt, &lab.UpdatedAt, &lab.EnrollmentCount,
		)
		labs = append(labs, lab)
	}
	return labs, total, nil
}

func (r *LabRepository) ListByCreator(ctx context.Context, userID int64, status string, limit, offset int) ([]dto.LabResponse, int, error) {
	where := "l.created_by = $1"
	args := []interface{}{userID}
	idx := 2

	if status != "" {
		where += fmt.Sprintf(" AND l.status = $%d", idx)
		args = append(args, status)
		idx++
	}

	var total int
	r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM labs l WHERE "+where, args...).Scan(&total)

	args = append(args, limit, offset)
	query := fmt.Sprintf(
		`SELECT l.id, l.title, l.description, l.category, l.level, l.thumbnail_url,
			l.lab_type, l.status, l.max_session_duration_min, l.auto_grade,
			l.created_by, l.published_at, l.created_at, l.updated_at,
			COALESCE((SELECT COUNT(*) FROM lab_enrollments WHERE lab_id = l.id AND status = 'ACCEPTED'), 0)
		FROM labs l
		WHERE %s
		ORDER BY l.updated_at DESC
		LIMIT $%d OFFSET $%d`, where, idx, idx+1)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("list labs by creator: %w", err)
	}
	defer rows.Close()

	var labs []dto.LabResponse
	for rows.Next() {
		var lab dto.LabResponse
		rows.Scan(
			&lab.ID, &lab.Title, &lab.Description, &lab.Category, &lab.Level,
			&lab.ThumbnailURL, &lab.LabType, &lab.Status, &lab.MaxSessionDurationMin,
			&lab.AutoGrade, &lab.CreatedBy, &lab.PublishedAt,
			&lab.CreatedAt, &lab.UpdatedAt, &lab.EnrollmentCount,
		)
		labs = append(labs, lab)
	}
	return labs, total, nil
}

func (r *LabRepository) Update(ctx context.Context, labID int64, req *dto.UpdateLabRequest) error {
	sets := []string{}
	args := []interface{}{}
	idx := 1

	if req.Title != nil {
		sets = append(sets, fmt.Sprintf("title = $%d", idx))
		args = append(args, *req.Title)
		idx++
	}
	if req.Description != nil {
		sets = append(sets, fmt.Sprintf("description = $%d", idx))
		args = append(args, *req.Description)
		idx++
	}
	if req.Category != nil {
		sets = append(sets, fmt.Sprintf("category = $%d", idx))
		args = append(args, *req.Category)
		idx++
	}
	if req.Level != nil {
		sets = append(sets, fmt.Sprintf("level = $%d", idx))
		args = append(args, *req.Level)
		idx++
	}
	if req.ThumbnailURL != nil {
		sets = append(sets, fmt.Sprintf("thumbnail_url = $%d", idx))
		args = append(args, *req.ThumbnailURL)
		idx++
	}
	if req.RuntimeConfig != nil {
		raw, _ := json.Marshal(*req.RuntimeConfig)
		sets = append(sets, fmt.Sprintf("runtime_config = $%d", idx))
		args = append(args, raw)
		idx++
	}
	if req.MaxSessionDurationMin != nil {
		sets = append(sets, fmt.Sprintf("max_session_duration_min = $%d", idx))
		args = append(args, *req.MaxSessionDurationMin)
		idx++
	}
	if req.MaxConcurrentSessions != nil {
		sets = append(sets, fmt.Sprintf("max_concurrent_sessions = $%d", idx))
		args = append(args, *req.MaxConcurrentSessions)
		idx++
	}
	if req.AutoGrade != nil {
		sets = append(sets, fmt.Sprintf("auto_grade = $%d", idx))
		args = append(args, *req.AutoGrade)
		idx++
	}
	if req.GradingConfig != nil {
		raw, _ := json.Marshal(*req.GradingConfig)
		sets = append(sets, fmt.Sprintf("grading_config = $%d", idx))
		args = append(args, raw)
		idx++
	}
	if req.Deadline != nil {
		sets = append(sets, fmt.Sprintf("deadline = $%d", idx))
		args = append(args, *req.Deadline)
		idx++
	}
	if req.AllowLateSubmission != nil {
		sets = append(sets, fmt.Sprintf("allow_late_submission = $%d", idx))
		args = append(args, *req.AllowLateSubmission)
		idx++
	}
	if req.LatePenaltyPercent != nil {
		sets = append(sets, fmt.Sprintf("late_penalty_percent = $%d", idx))
		args = append(args, *req.LatePenaltyPercent)
		idx++
	}

	if len(sets) == 0 {
		return nil
	}

	sets = append(sets, "updated_at = NOW()")
	args = append(args, labID)

	query := fmt.Sprintf("UPDATE labs SET %s WHERE id = $%d", strings.Join(sets, ", "), idx)
	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *LabRepository) Delete(ctx context.Context, labID int64) error {
	_, err := r.db.ExecContext(ctx, "DELETE FROM labs WHERE id = $1", labID)
	return err
}

func (r *LabRepository) Publish(ctx context.Context, labID int64) error {
	_, err := r.db.ExecContext(ctx,
		"UPDATE labs SET status = 'PUBLISHED', published_at = $1, updated_at = $1 WHERE id = $2",
		time.Now(), labID)
	return err
}

func (r *LabRepository) GetCreatorID(ctx context.Context, labID int64) (int64, error) {
	var creatorID int64
	err := r.db.QueryRowContext(ctx, "SELECT created_by FROM labs WHERE id = $1", labID).Scan(&creatorID)
	return creatorID, err
}

// ── Sections ────────────────────────────────────────────────────

func (r *LabRepository) CreateSection(ctx context.Context, labID int64, req *dto.CreateSectionRequest) (*dto.SectionResponse, error) {
	var resp dto.SectionResponse
	err := r.db.QueryRowContext(ctx,
		`INSERT INTO lab_sections (lab_id, title, description, order_index)
		VALUES ($1, $2, $3, $4)
		RETURNING id, lab_id, title, description, order_index, is_published, created_at, updated_at`,
		labID, req.Title, req.Description, req.OrderIndex,
	).Scan(&resp.ID, &resp.LabID, &resp.Title, &resp.Description, &resp.OrderIndex,
		&resp.IsPublished, &resp.CreatedAt, &resp.UpdatedAt)
	return &resp, err
}

func (r *LabRepository) ListSections(ctx context.Context, labID int64) ([]dto.SectionResponse, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, lab_id, title, description, order_index, is_published, created_at, updated_at
		FROM lab_sections WHERE lab_id = $1 ORDER BY order_index`, labID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var sections []dto.SectionResponse
	for rows.Next() {
		var s dto.SectionResponse
		rows.Scan(&s.ID, &s.LabID, &s.Title, &s.Description, &s.OrderIndex,
			&s.IsPublished, &s.CreatedAt, &s.UpdatedAt)
		sections = append(sections, s)
	}
	return sections, nil
}

func (r *LabRepository) UpdateSection(ctx context.Context, sectionID int64, req *dto.UpdateSectionRequest) error {
	sets := []string{}
	args := []interface{}{}
	idx := 1

	if req.Title != nil {
		sets = append(sets, fmt.Sprintf("title = $%d", idx))
		args = append(args, *req.Title)
		idx++
	}
	if req.Description != nil {
		sets = append(sets, fmt.Sprintf("description = $%d", idx))
		args = append(args, *req.Description)
		idx++
	}
	if req.OrderIndex != nil {
		sets = append(sets, fmt.Sprintf("order_index = $%d", idx))
		args = append(args, *req.OrderIndex)
		idx++
	}
	if req.IsPublished != nil {
		sets = append(sets, fmt.Sprintf("is_published = $%d", idx))
		args = append(args, *req.IsPublished)
		idx++
	}

	if len(sets) == 0 {
		return nil
	}
	sets = append(sets, "updated_at = NOW()")
	args = append(args, sectionID)

	query := fmt.Sprintf("UPDATE lab_sections SET %s WHERE id = $%d", strings.Join(sets, ", "), idx)
	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *LabRepository) DeleteSection(ctx context.Context, sectionID int64) error {
	_, err := r.db.ExecContext(ctx, "DELETE FROM lab_sections WHERE id = $1", sectionID)
	return err
}

// ── Content ─────────────────────────────────────────────────────

func (r *LabRepository) CreateContent(ctx context.Context, sectionID int64, req *dto.CreateContentRequest, userID int64) (*dto.ContentResponse, error) {
	metaJSON, _ := json.Marshal(req.Metadata)
	var resp dto.ContentResponse
	var metaRaw []byte

	err := r.db.QueryRowContext(ctx,
		`INSERT INTO lab_section_content (section_id, type, title, description, order_index, metadata, is_mandatory, created_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING id, section_id, type, title, description, order_index, metadata, is_published, is_mandatory, created_by, created_at, updated_at`,
		sectionID, req.Type, req.Title, req.Description, req.OrderIndex, metaJSON, req.IsMandatory, userID,
	).Scan(&resp.ID, &resp.SectionID, &resp.Type, &resp.Title, &resp.Description,
		&resp.OrderIndex, &metaRaw, &resp.IsPublished, &resp.IsMandatory,
		&resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt)
	if err != nil {
		return nil, err
	}

	json.Unmarshal(metaRaw, &resp.Metadata)
	return &resp, nil
}

func (r *LabRepository) ListContent(ctx context.Context, sectionID int64) ([]dto.ContentResponse, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, section_id, type, title, description, order_index, metadata,
			is_published, is_mandatory, file_path, file_size, file_type, created_by, created_at, updated_at
		FROM lab_section_content WHERE section_id = $1 ORDER BY order_index`, sectionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var contents []dto.ContentResponse
	for rows.Next() {
		var c dto.ContentResponse
		var metaRaw []byte
		rows.Scan(&c.ID, &c.SectionID, &c.Type, &c.Title, &c.Description,
			&c.OrderIndex, &metaRaw, &c.IsPublished, &c.IsMandatory,
			&c.FilePath, &c.FileSize, &c.FileType, &c.CreatedBy, &c.CreatedAt, &c.UpdatedAt)
		json.Unmarshal(metaRaw, &c.Metadata)
		contents = append(contents, c)
	}
	return contents, nil
}

func (r *LabRepository) UpdateContent(ctx context.Context, contentID int64, req *dto.UpdateContentRequest) error {
	query := "UPDATE lab_section_content SET updated_at = NOW()"
	var args []interface{}
	argID := 1

	if req.Title != nil {
		query += fmt.Sprintf(", title = $%d", argID)
		args = append(args, *req.Title)
		argID++
	}
	if req.Description != nil {
		query += fmt.Sprintf(", description = $%d", argID)
		args = append(args, *req.Description)
		argID++
	}
	if req.OrderIndex != nil {
		query += fmt.Sprintf(", order_index = $%d", argID)
		args = append(args, *req.OrderIndex)
		argID++
	}
	if req.Metadata != nil {
		metaRaw, _ := json.Marshal(*req.Metadata)
		query += fmt.Sprintf(", metadata = $%d", argID)
		args = append(args, metaRaw)
		argID++
	}
	if req.IsPublished != nil {
		query += fmt.Sprintf(", is_published = $%d", argID)
		args = append(args, *req.IsPublished)
		argID++
	}
	if req.IsMandatory != nil {
		query += fmt.Sprintf(", is_mandatory = $%d", argID)
		args = append(args, *req.IsMandatory)
		argID++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argID)
	args = append(args, contentID)

	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *LabRepository) DeleteContent(ctx context.Context, contentID int64) error {
	_, err := r.db.ExecContext(ctx, "DELETE FROM lab_section_content WHERE id = $1", contentID)
	return err
}

