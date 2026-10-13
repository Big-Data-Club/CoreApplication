package service

import (
	"context"
	"encoding/json"
	"fmt"

	"example/hello/internal/models"
	"example/hello/pkg/ai"
)

// AuthoringScope uses curriculum IDs. Knowledge nodes remain AI-owned details.
type AuthoringScope struct {
	CheckOnly  bool    `json:"check_only,omitempty"`
	SectionIDs []int64 `json:"section_ids" binding:"omitempty,max=100,dive,gt=0"`
	ContentIDs []int64 `json:"content_ids" binding:"omitempty,max=100,dive,gt=0"`
}

func (s *CourseService) AuthoringSources(ctx context.Context, courseID, userID int64, role string, scope AuthoringScope) ([]ai.AuthoringSource, error) {
	// Reuse the bank's course edit policy, including co-teachers.
	gate := QuestionBankService{courseRepo: s.courseRepo}
	if userID <= 0 {
		return nil, fmt.Errorf("permission denied: user required")
	}
	if role == "SERVICE" {
		roles, err := s.userRepo.GetUserRoles(ctx, userID)
		if err != nil {
			return nil, fmt.Errorf("permission denied: roles unavailable")
		}
		role = models.RoleTeacher
		for _, r := range roles {
			if r == models.RoleAdmin {
				role = models.RoleAdmin
			}
		}
	}
	if err := gate.verifyCourseEditAccess(ctx, courseID, userID, role); err != nil {
		return nil, err
	}
	if scope.CheckOnly {
		return []ai.AuthoringSource{}, nil
	}
	return resolveAuthoringSources(ctx, s.courseRepo, courseID, scope)
}

// Read canonical material only after authorization. Never accept browser text
// as a snapshot of a course lesson. Explicit invalid IDs fail the entire scope.
type authoringSourceRepository interface {
	ListSectionsByCourse(context.Context, int64) ([]*models.CourseSection, error)
	ListContentBySection(context.Context, int64) ([]*models.SectionContent, error)
}

func resolveAuthoringSources(ctx context.Context, repo authoringSourceRepository, courseID int64, scope AuthoringScope) ([]ai.AuthoringSource, error) {
	sections, err := repo.ListSectionsByCourse(ctx, courseID)
	if err != nil {
		return nil, err
	}
	wantedSections, wantedContents := map[int64]bool{}, map[int64]bool{}
	for _, id := range scope.SectionIDs {
		wantedSections[id] = true
	}
	for _, id := range scope.ContentIDs {
		wantedContents[id] = true
	}
	foundSections, foundContents := map[int64]bool{}, map[int64]bool{}
	wholeCourse := len(wantedSections) == 0 && len(wantedContents) == 0
	sources := []ai.AuthoringSource{}
	for _, section := range sections {
		if wantedSections[section.ID] {
			foundSections[section.ID] = true
		}
		contents, err := repo.ListContentBySection(ctx, section.ID)
		if err != nil {
			return nil, err
		}
		for _, content := range contents {
			if !wholeCourse && !wantedSections[section.ID] && !wantedContents[content.ID] {
				continue
			}
			if wantedContents[content.ID] {
				foundContents[content.ID] = true
			}
			switch content.Type {
			case models.ContentTypeText, models.ContentTypeDocument, models.ContentTypeVideo, models.ContentTypeImage:
			default:
				if wantedContents[content.ID] {
					return nil, fmt.Errorf("unsupported lesson source")
				}
				continue
			}
			var metadata map[string]interface{}
			if err := json.Unmarshal(content.Metadata, &metadata); err != nil && len(content.Metadata) > 0 {
				return nil, err
			}
			text := ""
			if content.Type == models.ContentTypeText {
				text, _ = metadata["content"].(string)
			}
			sources = append(sources, ai.AuthoringSource{ContentID: content.ID, SectionID: section.ID,
				Title: content.Title, SectionTitle: section.Title, Type: content.Type, Text: text})
		}
	}
	if len(foundSections) != len(wantedSections) || len(foundContents) != len(wantedContents) {
		return nil, fmt.Errorf("selected chapter or lesson does not belong to this course")
	}
	if len(sources) == 0 {
		return nil, fmt.Errorf("selected scope has no learning material")
	}
	if len(sources) > 100 {
		return nil, fmt.Errorf("select fewer chapters: at most 100 lessons per generation")
	}
	return sources, nil
}
