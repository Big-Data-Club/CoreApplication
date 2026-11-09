package repository

import (
	"context"
	"database/sql"
	"example/hello/internal/models"
	"fmt"
	"log"
	"time"

	"example/hello/pkg/cache"
	"github.com/lib/pq"
)

type LearningNotice = models.LearningNotice
type NoticeCourse = models.NoticeCourse
type NoticeTarget = models.NoticeTarget
type NotificationFeed = models.NotificationFeed

type NotificationRepository struct {
	db    *sql.DB
	cache *cache.RedisCache
}

func NewNotificationRepository(db *sql.DB, redis *cache.RedisCache) *NotificationRepository {
	return &NotificationRepository{db: db, cache: redis}
}

// One bounded feed query; bulk additions collapse into one chapter notice.
const learningNoticeQuery = `
WITH eligible AS (
 SELECT n.* FROM learning_notification_events n
 JOIN lms_notification_scope($1) c ON c.course_id = n.course_id
 WHERE n.created_at >= now() - interval '30 days'
 AND (c.enrolled OR n.kind = 'course_published')
 AND (n.section_id IS NULL OR n.kind = 'section_removed' OR EXISTS (
     SELECT 1 FROM course_sections s WHERE s.id = n.section_id AND s.course_id=n.course_id AND s.is_published
 ))
 AND (n.content_id IS NULL OR n.kind = 'content_removed' OR EXISTS (
     SELECT 1 FROM section_content sc WHERE sc.id = n.content_id AND sc.section_id=n.section_id AND sc.is_published
 ))
), groups AS (
 SELECT group_key, MAX(id) AS id, GREATEST(COUNT(DISTINCT content_id), 1) AS item_count
 FROM eligible GROUP BY group_key
), selected AS (
 SELECT n.*, g.item_count, ROW_NUMBER() OVER(PARTITION BY (n.kind='course_published') ORDER BY n.created_at DESC,n.id DESC) AS family_rank
 FROM groups g JOIN eligible n ON n.id=g.id
)
SELECT n.id, n.group_key, n.course_id, COALESCE(n.section_id,0) AS section_id, COALESCE(n.content_id,0) AS content_id,
 n.kind, COALESCE(sc.title, CASE WHEN n.content_id IS NULL THEN s.title END, n.entity_title) AS entity_title, c.title, n.item_count, n.created_at,
 COALESCE(s.title,'') AS section_title, c.enrolled
FROM selected n
JOIN lms_notification_scope($1) c ON c.course_id = n.course_id
LEFT JOIN course_sections s ON s.id = n.section_id AND s.course_id=n.course_id
LEFT JOIN section_content sc ON sc.id=n.content_id AND sc.section_id=n.section_id
WHERE n.family_rank <= CASE WHEN n.kind='course_published' THEN 5 ELSE 20 END
ORDER BY n.created_at DESC, n.id DESC LIMIT 25`

func (s *NotificationRepository) Feed(ctx context.Context, userID int64) (*NotificationFeed, error) {
	feed := &NotificationFeed{Alerts: []LearningNotice{}, Courses: []NoticeCourse{}, Targets: []NoticeTarget{}, ReadKeys: []string{}}
	rows, err := s.db.QueryContext(ctx, learningNoticeQuery, userID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var id, count int64
		var notice LearningNotice
		var sectionTitle string
		var enrolled bool
		if err = rows.Scan(&id, &notice.GroupKey, &notice.CourseID, &notice.SectionID, &notice.ContentID, &notice.Type, &notice.EntityTitle, &notice.CourseTitle, &count, &notice.DetectedAt, &sectionTitle, &enrolled); err != nil {
			rows.Close()
			return nil, err
		}
		notice.ID = fmt.Sprintf("learning:%d", id)
		notice.ItemCount = count
		notice.SectionTitle = sectionTitle
		notice.Enrolled = enrolled
		feed.Alerts = append(feed.Alerts, notice)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	rows, err = s.db.QueryContext(ctx, `SELECT course_id,title FROM lms_notification_scope($1) WHERE enrolled ORDER BY course_id`, userID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var c NoticeCourse
		if err = rows.Scan(&c.ID, &c.Title); err != nil {
			rows.Close()
			return nil, err
		}
		feed.Courses = append(feed.Courses, c)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	// Resolve node hints to real, published content within the student's scope.
	rows, err = s.db.QueryContext(ctx, `SELECT DISTINCT ON (m.course_id,m.node_id) m.course_id,m.node_id,sc.id,sc.title
 FROM micro_lessons m JOIN section_content sc ON sc.id = COALESCE(m.published_content_id,m.source_content_id)
 JOIN course_sections sec ON sec.id=sc.section_id AND sec.is_published AND sec.course_id=m.course_id
 JOIN lms_notification_scope($1) c ON c.course_id=m.course_id AND c.enrolled
 WHERE m.node_id IS NOT NULL AND sc.is_published
 ORDER BY m.course_id,m.node_id,m.updated_at DESC LIMIT 200`, userID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var target NoticeTarget
		if err = rows.Scan(&target.CourseID, &target.NodeID, &target.ContentID, &target.Title); err != nil {
			rows.Close()
			return nil, err
		}
		feed.Targets = append(feed.Targets, target)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	rows, err = s.db.QueryContext(ctx, `SELECT notification_key FROM learning_notification_reads WHERE user_id=$1 AND read_at>=now()-interval '30 days' ORDER BY read_at DESC LIMIT 300`, userID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var key string
		if err = rows.Scan(&key); err != nil {
			rows.Close()
			return nil, err
		}
		feed.ReadKeys = append(feed.ReadKeys, key)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	// Deadlines are a single indexed relational query, never one request per chapter.
	rows, err = s.db.QueryContext(ctx, `SELECT q.id,q.title,q.available_until,c.course_id,c.title,sc.id
 FROM quizzes q JOIN section_content sc ON sc.id=q.content_id AND sc.is_published
 JOIN course_sections sec ON sec.id=sc.section_id AND sec.is_published
 JOIN lms_notification_scope($1) c ON c.course_id=sec.course_id AND c.enrolled
 WHERE q.is_published AND q.available_until>now() AND q.available_until<now()+interval '3 days'
 AND NOT EXISTS (SELECT 1 FROM quiz_attempts a WHERE a.quiz_id=q.id AND a.student_id=$1 AND a.submitted_at IS NOT NULL)
 ORDER BY q.available_until LIMIT 5`, userID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var n LearningNotice
		var deadline time.Time
		if err = rows.Scan(&n.QuizID, &n.EntityTitle, &deadline, &n.CourseID, &n.CourseTitle, &n.ContentID); err != nil {
			rows.Close()
			return nil, err
		}
		n.ID = fmt.Sprintf("deadline:%d:%d", n.QuizID, deadline.Unix())
		n.Type = "quiz_deadline"
		n.DetectedAt = deadline
		feed.Alerts = append(feed.Alerts, n)
	}
	err = rows.Err()
	rows.Close()
	return feed, err
}

func (s *NotificationRepository) MarkRead(ctx context.Context, userID int64, keys []string) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO learning_notification_reads(user_id,notification_key)
 SELECT $1, key FROM (SELECT DISTINCT unnest($2::text[]) AS key) keys ON CONFLICT(user_id,notification_key) DO UPDATE SET read_at=now()`, userID, pq.Array(keys))
	if err != nil {
		return err
	}

	if s.cache != nil {
		_ = s.cache.Publish(ctx, fmt.Sprintf("learning:user:%d", userID), "refresh")
	}
	return nil
}

// Scope channels carry a constant invalidation hint, never course titles or IDs.
func (s *NotificationRepository) Channels(ctx context.Context, userID int64) ([]string, error) {
	channels := []string{fmt.Sprintf("learning:user:%d", userID)}
	rows, err := s.db.QueryContext(ctx, `SELECT 'learning:course:'||course_id FROM lms_notification_scope($1) WHERE enrolled
 UNION SELECT 'learning:org:'||org_id FROM organization_members WHERE user_id=$1
 UNION SELECT 'learning:public' WHERE NOT EXISTS(SELECT 1 FROM organization_members m JOIN organizations o ON o.id=m.org_id WHERE m.user_id=$1 AND COALESCE(o.settings->>'allow_cross_org_courses','false')<>'true')`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var c string
		if err = rows.Scan(&c); err != nil {
			return nil, err
		}
		channels = append(channels, c)
	}
	return channels, rows.Err()
}

// Relay only pending outbox rows. SKIP LOCKED makes multiple LMS replicas safe.
func (s *NotificationRepository) Relay(ctx context.Context) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, `SELECT n.id,n.course_id,n.kind,COALESCE(c.org_id,0),COALESCE(c.visibility,'') FROM learning_notification_events n LEFT JOIN courses c ON c.id=n.course_id WHERE delivered_at IS NULL ORDER BY n.id LIMIT 50 FOR UPDATE OF n SKIP LOCKED`)
	if err != nil {
		return err
	}
	type wake struct {
		id, course, org  int64
		kind, visibility string
	}
	var batch []wake
	for rows.Next() {
		var w wake
		if err = rows.Scan(&w.id, &w.course, &w.kind, &w.org, &w.visibility); err != nil {
			rows.Close()
			return err
		}
		batch = append(batch, w)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	channels := make(map[string]struct{})
	ids := make([]int64, 0, len(batch))
	for _, w := range batch {
		ids = append(ids, w.id)
		channels[fmt.Sprintf("learning:course:%d", w.course)] = struct{}{}
		if w.kind == "course_published" {
			channels[fmt.Sprintf("learning:org:%d", w.org)] = struct{}{}
			if w.visibility == "PUBLIC" {
				channels["learning:public"] = struct{}{}
			}
		}
	}
	for channel := range channels {
		if err = s.cache.Publish(ctx, channel, "refresh"); err != nil {
			return err
		}
	}
	if len(ids) > 0 {
		if _, err = tx.ExecContext(ctx, `UPDATE learning_notification_events SET delivered_at=now() WHERE id=ANY($1)`, pq.Array(ids)); err != nil {
			return err
		}
	}

	return tx.Commit()
}

func (s *NotificationRepository) Run(ctx context.Context) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	cleanup := time.NewTicker(time.Hour)
	defer cleanup.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			work, cancel := context.WithTimeout(ctx, 3*time.Second)
			err := s.Relay(work)
			cancel()
			if err != nil {
				log.Printf("learning notification relay retry pending: %v", err)
			}
		case <-cleanup.C:
			work, cancel := context.WithTimeout(ctx, 5*time.Second)
			_, _ = s.db.ExecContext(work, `DELETE FROM learning_notification_events WHERE id IN(SELECT id FROM learning_notification_events WHERE created_at<now()-interval '30 days' LIMIT 1000)`)
			_, _ = s.db.ExecContext(work, `DELETE FROM learning_notification_reads WHERE (user_id,notification_key) IN(SELECT user_id,notification_key FROM learning_notification_reads WHERE read_at<now()-interval '30 days' LIMIT 1000)`)
			cancel()
		}
	}
}
