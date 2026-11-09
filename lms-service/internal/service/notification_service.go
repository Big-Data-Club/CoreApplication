package service

import (
	"context"
	"database/sql"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strings"
)

type LearningNotice = models.LearningNotice
type NotificationFeed = models.NotificationFeed

type NotificationService struct {
	repo *repository.NotificationRepository
}

func NewNotificationService(db *sql.DB, redis *cache.RedisCache) *NotificationService {
	return &NotificationService{repo: repository.NewNotificationRepository(db, redis)}
}
func (s *NotificationService) Feed(ctx context.Context, userID int64) (*NotificationFeed, error) {
	feed, err := s.repo.Feed(ctx, userID)
	if err != nil {
		return nil, err
	}
	sort.SliceStable(feed.Alerts, func(i, j int) bool {
		return feed.Alerts[i].Type == "quiz_deadline" && feed.Alerts[j].Type != "quiz_deadline"
	})
	for index := range feed.Alerts {
		n := &feed.Alerts[index]
		if n.Type == "quiz_deadline" {
			n.Category = "learning"
			n.Title = "Sắp đến hạn làm bài"
			n.Message = fmt.Sprintf("Bài kiểm tra “%s” trong khóa “%s” sắp đến hạn.", n.EntityTitle, n.CourseTitle)
			n.Href = fmt.Sprintf("/lms/student/courses/%d/quiz/%d/take", n.CourseID, n.QuizID)
		} else {
			formatLearningNotice(n, n.ItemCount, n.SectionTitle, n.Enrolled)
		}
	}
	return feed, nil
}
func (s *NotificationService) MarkRead(ctx context.Context, userID int64, keys []string) error {
	if !ValidNoticeKeys(keys) {
		return fmt.Errorf("invalid notification keys")
	}
	return s.repo.MarkRead(ctx, userID, keys)
}
func (s *NotificationService) Channels(ctx context.Context, userID int64) ([]string, error) {
	return s.repo.Channels(ctx, userID)
}
func (s *NotificationService) Run(ctx context.Context) { s.repo.Run(ctx) }

func formatLearningNotice(n *LearningNotice, count int64, sectionTitle string, enrolled bool) {
	n.Category = "learning"
	n.Href = fmt.Sprintf("/lms/student/courses/%d/learn", n.CourseID)
	if n.SectionID > 0 && n.Type != "section_removed" {
		n.Href += fmt.Sprintf("?sectionId=%d", n.SectionID)
	}
	switch n.Type {
	case "course_published":
		n.Href = fmt.Sprintf("/lms/student/courses/%d/learn", n.CourseID)
		n.Title = "Khóa học mới ra mắt"
		n.Message = fmt.Sprintf("Khám phá khóa học “%s”.", n.CourseTitle)
		if !enrolled {
			n.Href = fmt.Sprintf("/lms/student/discover/%d", n.CourseID)
		}
	case "course_updated":
		n.Title = "Khóa học đã cập nhật"
		n.Message = fmt.Sprintf("Thông tin khóa “%s” vừa được cập nhật.", n.CourseTitle)
	case "section_added":
		n.Title = "Chương học mới"
		n.Message = fmt.Sprintf("Chương “%s” vừa được mở trong khóa “%s”.", n.EntityTitle, n.CourseTitle)
	case "section_updated":
		n.Title = "Chương học đã cập nhật"
		n.Message = fmt.Sprintf("Chương “%s” trong khóa “%s” vừa thay đổi.", n.EntityTitle, n.CourseTitle)
	case "section_removed":
		n.Title = "Lộ trình khóa học thay đổi"
		n.Message = fmt.Sprintf("Chương “%s” trong khóa “%s” đã được gỡ khỏi lộ trình.", n.EntityTitle, n.CourseTitle)
	case "content_removed":
		n.Title = "Nội dung đã được gỡ"
		n.Message = fmt.Sprintf("Nội dung “%s” trong khóa “%s” đã được gỡ. Xem các bài học còn lại.", n.EntityTitle, n.CourseTitle)
	default:
		n.Title = "Nội dung đã cập nhật"
		if n.Type == "content_added" {
			n.Title = "Có nội dung học mới"
		}
		if n.Type == "content_added" && count > 1 {
			n.Message = fmt.Sprintf("%d nội dung mới trong chương “%s”, khóa “%s”.", count, sectionTitle, n.CourseTitle)
		} else {
			n.Message = fmt.Sprintf("“%s” trong khóa “%s” vừa được cập nhật.", n.EntityTitle, n.CourseTitle)
			n.Href = fmt.Sprintf("/lms/student/courses/%d/learn?contentId=%d", n.CourseID, n.ContentID)
		}
	}
	if n.ID != "" {
		separator := "?"
		if strings.Contains(n.Href, "?") {
			separator = "&"
		}
		n.Href += separator + "notice=" + url.QueryEscape(n.ID)
	}

}

var noticeKeyPattern = regexp.MustCompile(`^(learning:[0-9]+|deadline:[0-9]+:[0-9]+|suggestion:[a-z_]+:[0-9]+:[0-9]*:[0-9]+)$`)

func ValidNoticeKeys(keys []string) bool {
	if len(keys) == 0 || len(keys) > 50 {
		return false
	}
	for _, key := range keys {
		if len(key) > 160 || !noticeKeyPattern.MatchString(key) {
			return false
		}
	}
	return true
}
