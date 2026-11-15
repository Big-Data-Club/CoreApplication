package repository

import "context"

func (r *QuizRepository) QuizAccess(ctx context.Context, quizID, userID int64) (bool, bool, error) {
	var manager, enrolled bool
	err := r.db.QueryRowContext(ctx, `SELECT
  (c.created_by=$2 OR EXISTS(SELECT 1 FROM course_co_teachers ct WHERE ct.course_id=c.id AND ct.user_id=$2)),
  EXISTS(SELECT 1 FROM enrollments e WHERE e.course_id=c.id AND e.student_id=$2 AND e.status='ACCEPTED' AND c.status='PUBLISHED' AND sc.is_published AND cs.is_published)
  FROM quizzes q JOIN section_content sc ON sc.id=q.content_id
  JOIN course_sections cs ON cs.id=sc.section_id JOIN courses c ON c.id=cs.course_id WHERE q.id=$1`, quizID, userID).Scan(&manager, &enrolled)
	return manager, enrolled, err
}
