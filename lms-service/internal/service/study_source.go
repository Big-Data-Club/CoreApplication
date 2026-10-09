package service

import (
	"context"
	"encoding/json"
	"errors"

	"example/hello/internal/models"
)

type studyContentRepository interface {
	GetContentByID(context.Context, int64) (*models.SectionContent, error)
	GetSectionByID(context.Context, int64) (*models.CourseSection, error)
}
type studyLessonRepository interface {
	GetLesson(context.Context, int64) (*models.MicroLesson, error)
}

// StudySource is a canonical LMS snapshot, never text supplied by the browser.
type StudySource struct {
	ContentID int64  `json:"content_id,omitempty"`
	LessonID  int64  `json:"lesson_id,omitempty"`
	Title     string `json:"title"`
	Text      string `json:"text"`
	NodeID    int64  `json:"node_id,omitempty"`
}

type StudySourceService struct {
	contents studyContentRepository
	lessons  studyLessonRepository
}

func NewStudySourceService(contents studyContentRepository, lessons studyLessonRepository) *StudySourceService {
	return &StudySourceService{contents: contents, lessons: lessons}
}

func (s *StudySourceService) Resolve(ctx context.Context, courseID, contentID, lessonID int64) (*StudySource, error) {
	denied := errors.New("Không tìm thấy bài học trong khóa học này")
	if (contentID > 0) == (lessonID > 0) || contentID < 0 || lessonID < 0 {
		return nil, denied
	}
	if lessonID > 0 {
		lesson, err := s.lessons.GetLesson(ctx, lessonID)
		if err != nil || lesson == nil || lesson.CourseID != courseID || lesson.Status != models.MicroLessonStatusPublished {
			return nil, denied
		}
		if lesson.SectionID.Valid {
			section, err := s.contents.GetSectionByID(ctx, lesson.SectionID.Int64)
			if err != nil || section == nil || section.CourseID != courseID {
				return nil, denied
			}
		}
		// Do not load the whole original document for a short micro lesson.
		return &StudySource{LessonID: lesson.ID, Title: lesson.Title, Text: lesson.MarkdownContent, NodeID: lesson.NodeID.Int64}, nil
	}
	content, err := s.contents.GetContentByID(ctx, contentID)
	if err != nil || content == nil {
		return nil, denied
	}
	section, err := s.contents.GetSectionByID(ctx, content.SectionID)
	if err != nil || section == nil || section.CourseID != courseID {
		return nil, denied
	}
	if content.Type != "TEXT" && content.Type != "DOCUMENT" && content.Type != "VIDEO" {
		return nil, errors.New("Bài học này chưa hỗ trợ tạo câu hỏi")
	}
	var metadata struct {
		Content string `json:"content"`
		NodeID  int64  `json:"node_id"`
	}
	if len(content.Metadata) > 0 {
		if err := json.Unmarshal(content.Metadata, &metadata); err != nil {
			return nil, errors.New("Chưa đọc được nội dung bài học")
		}
	}
	text := ""
	if content.Type == "TEXT" {
		text = metadata.Content
	}
	return &StudySource{ContentID: content.ID, Title: content.Title, Text: text, NodeID: metadata.NodeID}, nil
}
