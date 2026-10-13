package service

import (
	"context"
	"example/hello/internal/models"
	"testing"
)

type authoringRepo struct{}

func (authoringRepo) ListSectionsByCourse(context.Context, int64) ([]*models.CourseSection, error) {
	return []*models.CourseSection{{ID: 11, Title: "Foundations"}, {ID: 12, Title: "Applications"}}, nil
}
func (authoringRepo) ListContentBySection(_ context.Context, sectionID int64) ([]*models.SectionContent, error) {
	if sectionID == 11 {
		return []*models.SectionContent{
			{ID: 21, SectionID: 11, Title: "Text lesson", Type: "TEXT", Metadata: []byte(`{"content":"Canonical explanation"}`)},
			{ID: 22, SectionID: 11, Title: "Video lesson", Type: "VIDEO"},
			{ID: 23, SectionID: 11, Title: "Forum", Type: "FORUM"},
		}, nil
	}
	return []*models.SectionContent{{ID: 24, SectionID: 12, Title: "PDF lesson", Type: "DOCUMENT"}}, nil
}

func TestAuthoringSourcesUnionAndCanonicalText(t *testing.T) {
	sources, err := resolveAuthoringSources(context.Background(), authoringRepo{}, 7,
		AuthoringScope{SectionIDs: []int64{11, 11}, ContentIDs: []int64{21, 24}})
	if err != nil || len(sources) != 3 {
		t.Fatalf("sources=%+v err=%v", sources, err)
	}
	if sources[0].Text != "Canonical explanation" || sources[1].Text != "" || sources[2].ContentID != 24 {
		t.Fatalf("wrong canonical scope: %+v", sources)
	}
}

func TestAuthoringSourcesRejectsForeignOrUnsupportedSelections(t *testing.T) {
	for _, scope := range []AuthoringScope{
		{SectionIDs: []int64{99}}, {ContentIDs: []int64{99}},
		{SectionIDs: []int64{11}, ContentIDs: []int64{99}}, {ContentIDs: []int64{23}},
	} {
		if _, err := resolveAuthoringSources(context.Background(), authoringRepo{}, 7, scope); err == nil {
			t.Fatalf("accepted invalid scope: %+v", scope)
		}
	}
}

func TestAuthoringWholeCourseIncludesEveryLearningSource(t *testing.T) {
	sources, err := resolveAuthoringSources(context.Background(), authoringRepo{}, 7, AuthoringScope{})
	if err != nil || len(sources) != 3 {
		t.Fatalf("sources=%+v err=%v", sources, err)
	}
}
