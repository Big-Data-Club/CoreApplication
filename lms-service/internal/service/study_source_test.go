package service

import (
	"context"
	"database/sql"
	"example/hello/internal/models"
	"testing"
)

type studyRepo struct {
	content models.SectionContent
	section models.CourseSection
	lesson  models.MicroLesson
}

func (r *studyRepo) GetContentByID(context.Context, int64) (*models.SectionContent, error) {
	return &r.content, nil
}
func (r *studyRepo) GetSectionByID(context.Context, int64) (*models.CourseSection, error) {
	return &r.section, nil
}
func (r *studyRepo) GetLesson(context.Context, int64) (*models.MicroLesson, error) {
	return &r.lesson, nil
}
func TestStudySourceCourseAccessMatchesLearningPage(t *testing.T) {
	r := &studyRepo{content: models.SectionContent{ID: 9, SectionID: 2, IsPublished: true, Type: "TEXT", Title: "CS", Metadata: []byte(`{"content":"Stacks are LIFO","node_id":5}`)}, section: models.CourseSection{CourseID: 7, IsPublished: true}, lesson: models.MicroLesson{ID: 12, CourseID: 7, Status: "published", MarkdownContent: "Lesson text", SectionID: sql.NullInt64{Int64: 2, Valid: true}}}
	s := NewStudySourceService(r, r)
	ctx := context.Background()
	source, err := s.Resolve(ctx, 7, 9, 0)
	if err != nil || source.Text != "Stacks are LIFO" || source.NodeID != 5 {
		t.Fatalf("source: %+v %v", source, err)
	}
	for _, ids := range [][3]int64{{8, 9, 0}, {7, 9, 12}, {7, 0, 0}, {8, 0, 12}} {
		if _, err := s.Resolve(ctx, ids[0], ids[1], ids[2]); err == nil {
			t.Fatalf("accepted invalid scope %v", ids)
		}
	}
	r.section.IsPublished = false
	if _, err := s.Resolve(ctx, 7, 9, 0); err != nil {
		t.Fatalf("enrolled learner can open this section: %v", err)
	}
	if _, err := s.Resolve(ctx, 7, 0, 12); err != nil {
		t.Fatalf("enrolled learner can open this lesson: %v", err)
	}
	r.section.IsPublished = true
	r.content.IsPublished = false
	if _, err := s.Resolve(ctx, 7, 9, 0); err != nil {
		t.Fatalf("enrolled learner can open this content: %v", err)
	}
	r.lesson.Status = "draft"
	if _, err := s.Resolve(ctx, 7, 0, 12); err == nil {
		t.Fatal("accepted draft lesson")
	}
}
