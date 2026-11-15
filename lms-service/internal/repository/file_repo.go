package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

var ErrFileQuota = errors.New("file storage quota exceeded")

type FileRepository struct {
	db    *sql.DB
	quota int64
}

func NewFileRepository(db *sql.DB, quotas ...int64) *FileRepository {
	quota := int64(1 << 30)
	if len(quotas) > 0 && quotas[0] > 0 {
		quota = quotas[0]
	}
	return &FileRepository{db: db, quota: quota}
}
func (r *FileRepository) Register(ctx context.Context, path string, owner, size int64, public bool) error {
	visibility := "private"
	if public {
		visibility = "public"
	}
	if size < 0 {
		return ErrFileQuota
	}
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, fmt.Sprintf("file-quota:%d", owner)); err != nil {
		return err
	}
	var used int64
	if err := tx.QueryRowContext(ctx, `SELECT COALESCE(SUM(size_bytes),0) FROM lms_file_assets WHERE owner_user_id=$1`, owner).Scan(&used); err != nil {
		return err
	}
	if size > r.quota-used {
		return ErrFileQuota
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO lms_file_assets(file_path,owner_user_id,size_bytes,visibility) VALUES($1,$2,$3,$4)`, path, owner, size, visibility)
	if err != nil {
		return err
	}
	return tx.Commit()

}
func (r *FileRepository) Forget(ctx context.Context, path string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM lms_file_assets WHERE file_path=$1`, path)
	return err
}

// FileAccess resolves legacy course attachments as well as newly registered uploads.
// Unknown legacy objects require administrator recovery instead of guessing an owner.
func (r *FileRepository) Access(ctx context.Context, path string, userID int64) (read, manage bool, err error) {
	err = r.db.QueryRowContext(ctx, `SELECT
 (split_part($1,'/',1)='image' AND NOT EXISTS(SELECT 1 FROM lms_file_assets f WHERE f.file_path=$1)) OR EXISTS(SELECT 1 FROM lms_file_assets f WHERE f.file_path=$1 AND (f.visibility='public' OR f.owner_user_id=$2))
 OR EXISTS(SELECT 1 FROM quiz_questions qq JOIN quizzes q ON q.id=qq.quiz_id JOIN section_content sc ON sc.id=q.content_id JOIN course_sections cs ON cs.id=sc.section_id JOIN courses c ON c.id=cs.course_id
 WHERE split_part($1,'/',1)='quizzes' AND split_part($1,'/',2)='question_'||qq.id::text AND (
 c.created_by=$2 OR EXISTS(SELECT 1 FROM course_co_teachers ct WHERE ct.course_id=c.id AND ct.user_id=$2)
 OR (q.is_published AND c.status='PUBLISHED' AND EXISTS(SELECT 1 FROM enrollments e WHERE e.course_id=c.id AND e.student_id=$2 AND e.status='ACCEPTED'))))
 OR EXISTS(SELECT 1 FROM section_content sc JOIN course_sections cs ON cs.id=sc.section_id JOIN courses c ON c.id=cs.course_id
 WHERE sc.file_path=$1 AND (
 c.created_by=$2 OR EXISTS(SELECT 1 FROM course_co_teachers ct WHERE ct.course_id=c.id AND ct.user_id=$2)
 OR (c.status='PUBLISHED' AND sc.is_published AND cs.is_published AND (
 c.visibility='PUBLIC' OR EXISTS(SELECT 1 FROM enrollments e WHERE e.course_id=c.id AND e.student_id=$2 AND e.status='ACCEPTED'))))),
 EXISTS(SELECT 1 FROM lms_file_assets f WHERE f.file_path=$1 AND f.owner_user_id=$2)
 OR EXISTS(SELECT 1 FROM section_content sc JOIN course_sections cs ON cs.id=sc.section_id JOIN courses c ON c.id=cs.course_id
 WHERE sc.file_path=$1 AND (c.created_by=$2 OR EXISTS(SELECT 1 FROM course_co_teachers ct WHERE ct.course_id=c.id AND ct.user_id=$2)))`, path, userID).Scan(&read, &manage)
	return
}
