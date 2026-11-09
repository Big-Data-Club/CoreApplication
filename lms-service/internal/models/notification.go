package models

import "time"

type LearningNotice struct {
	ItemCount    int64     `json:"-"`
	SectionTitle string    `json:"-"`
	Enrolled     bool      `json:"-"`
	ID           string    `json:"id"`
	GroupKey     string    `json:"group_key,omitempty"`
	Category     string    `json:"category"`
	Type         string    `json:"alert_type"`
	Title        string    `json:"title"`
	Message      string    `json:"alert_message"`
	CourseID     int64     `json:"course_id"`
	CourseTitle  string    `json:"course_title"`
	SectionID    int64     `json:"section_id,omitempty"`
	ContentID    int64     `json:"content_id,omitempty"`
	EntityTitle  string    `json:"entity_title,omitempty"`
	Href         string    `json:"href"`
	DetectedAt   time.Time `json:"detected_at"`
	QuizID       int64     `json:"quiz_id,omitempty"`
}

type NoticeCourse struct {
	ID    int64  `json:"course_id"`
	Title string `json:"course_title"`
}

type NoticeTarget struct {
	CourseID  int64  `json:"course_id"`
	NodeID    int64  `json:"node_id"`
	ContentID int64  `json:"content_id"`
	Title     string `json:"content_title"`
}

type NotificationFeed struct {
	Alerts   []LearningNotice `json:"alerts"`
	Courses  []NoticeCourse   `json:"courses"`
	Targets  []NoticeTarget   `json:"targets"`
	ReadKeys []string         `json:"read_keys"`
}
