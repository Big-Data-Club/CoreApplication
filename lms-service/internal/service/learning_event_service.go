package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"time"

	"example/hello/internal/models"
	"example/hello/internal/repository"
)

type LearningEventService struct {
	repo         *repository.LearningEventRepository
	kafkaService *KafkaService
}

func NewLearningEventService(repo *repository.LearningEventRepository, kafkaService *KafkaService) *LearningEventService {
	return &LearningEventService{
		repo:         repo,
		kafkaService: kafkaService,
	}
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENTS
// ══════════════════════════════════════════════════════════════════════════════

type TrackEventRequest struct {
	EventType      string                 `json:"event_type" binding:"required"`
	SessionID      string                 `json:"session_id"`
	CourseID       *int64                 `json:"course_id"`
	LessonID       *int64                 `json:"lesson_id"`
	QuestionID     *int64                 `json:"question_id"`
	SkillID        *int64                 `json:"skill_id"`
	Difficulty     *float64               `json:"difficulty"`
	Correct        *bool                  `json:"correct"`
	AttemptNo      *int                   `json:"attempt_no"`
	ResponseTimeMs *int64                 `json:"response_time_ms"`
	HintCount      *int                   `json:"hint_count"`
	Metadata       map[string]interface{} `json:"metadata"`
}

func (s *LearningEventService) TrackEvent(ctx context.Context, studentID int64, eventID string, req *TrackEventRequest) (*models.LearningEvent, error) {
	// Convert metadata to JSON
	var metadataJSON []byte
	var err error
	if req.Metadata != nil {
		metadataJSON, err = json.Marshal(req.Metadata)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal metadata: %w", err)
		}
	}

	event := &models.LearningEvent{
		EventID:        eventID,
		EventType:      req.EventType,
		StudentID:      studentID,
		SessionID:      toNullString(req.SessionID),
		CourseID:       toNullInt64(req.CourseID),
		LessonID:       toNullInt64(req.LessonID),
		QuestionID:     toNullInt64(req.QuestionID),
		SkillID:        toNullInt64(req.SkillID),
		Difficulty:     toNullFloat64(req.Difficulty),
		Correct:        toNullBool(req.Correct),
		AttemptNo:      toNullInt32(req.AttemptNo),
		ResponseTimeMs: toNullInt64(req.ResponseTimeMs),
		HintCount:      toNullInt32(req.HintCount),
		Metadata:       metadataJSON,
	}

	// If skill_id is not provided but question_id is, try to infer skill from question
	if req.SkillID == nil && req.QuestionID != nil {
		skills, err := s.repo.GetQuestionSkills(ctx, *req.QuestionID)
		if err == nil && len(skills) > 0 {
			event.SkillID = sql.NullInt64{Int64: skills[0].SkillID, Valid: true}
			if skills[0].Difficulty.Valid {
				event.Difficulty = skills[0].Difficulty
			}
		}
	}

	// Save to database
	if err := s.repo.CreateEvent(ctx, event); err != nil {
		return nil, fmt.Errorf("failed to create event: %w", err)
	}

	// The student-facing APIs read learner_skill_states from PostgreSQL. Keep
	// that projection current in the same durable system as the event log;
	// Kafka consumers are used for analytics and must not be a prerequisite for
	// displaying a student's progress.
	if event.SkillID.Valid && event.Correct.Valid {
		if err := s.refreshLearnerSkillState(ctx, studentID, event.SkillID.Int64); err != nil {
			return nil, fmt.Errorf("failed to update learner skill state: %w", err)
		}
	}

	// Kafka is an optional downstream projection. The event itself is already
	// committed above, so a transient broker outage must not lose student work.
	if s.kafkaService != nil {
		go func(event *models.LearningEvent) {
			if err := s.kafkaService.PublishLearningEvent(event); err != nil {
				// Log error but don't fail the request
				fmt.Printf("Failed to publish learning event to Kafka: %v\n", err)
			}
		}(event)
	}

	return event, nil
}

// refreshLearnerSkillState derives a bounded, explainable mastery projection
// from the most recent answer events for one student and skill.
func (s *LearningEventService) refreshLearnerSkillState(ctx context.Context, studentID, skillID int64) error {
	events, err := s.repo.GetSkillEvents(ctx, studentID, skillID, 50)
	if err != nil {
		return err
	}

	correct, attempts, hints := 0, 0, 0
	var responseTotal int64
	responseCount := 0
	difficultyTotal := 0.0
	difficultyCount := 0
	var lastPracticed time.Time

	for _, event := range events {
		if event.CreatedAt.After(lastPracticed) {
			lastPracticed = event.CreatedAt
		}
		if event.Correct.Valid {
			attempts++
			if event.Correct.Bool {
				correct++
			}
		}
		if event.HintCount.Valid {
			hints += int(event.HintCount.Int32)
		}
		if event.ResponseTimeMs.Valid {
			responseTotal += event.ResponseTimeMs.Int64
			responseCount++
		}
		if event.Difficulty.Valid {
			difficultyTotal += event.Difficulty.Float64
			difficultyCount++
		}
	}
	if attempts == 0 {
		return nil
	}

	accuracy := float64(correct) / float64(attempts)
	avgDifficulty := 0.5
	if difficultyCount > 0 {
		avgDifficulty = difficultyTotal / float64(difficultyCount)
	}
	hintDependency := math.Min(1, float64(hints)/float64(attempts))
	mastery := accuracy*(1+(avgDifficulty-0.5)*0.3) - hintDependency*0.2
	mastery = math.Max(0, math.Min(1, mastery))
	recommendedDifficulty := math.Max(0.1, math.Min(1, avgDifficulty+masteryAdjustment(mastery, accuracy, hintDependency)))

	state := &models.LearnerSkillState{
		StudentID: studentID, SkillID: skillID, MasteryScore: mastery,
		ConfidenceScore: math.Min(1, float64(attempts)/10), AttemptCount: attempts,
		Accuracy: accuracy, HintDependency: hintDependency,
		LastPracticedAt:       sql.NullTime{Time: lastPracticed, Valid: !lastPracticed.IsZero()},
		RecommendedDifficulty: sql.NullFloat64{Float64: recommendedDifficulty, Valid: true},
	}
	if responseCount > 0 {
		state.AvgResponseTimeMs = sql.NullInt64{Int64: responseTotal / int64(responseCount), Valid: true}
	}
	return s.repo.UpsertLearnerSkillState(ctx, state)
}

func masteryAdjustment(mastery, accuracy, hintDependency float64) float64 {
	switch {
	case mastery < 0.3:
		return -0.2
	case mastery < 0.6:
		return 0
	case mastery < 0.8:
		if accuracy > 0.8 && hintDependency < 0.2 {
			return 0.15
		}
		return 0.1
	default:
		return 0.2
	}
}

func (s *LearningEventService) GetStudentEvents(ctx context.Context, studentID int64, courseID, limit string) ([]models.LearningEvent, error) {
	return s.repo.GetStudentEvents(ctx, studentID, courseID, limit)
}

func (s *LearningEventService) GetStudentSkills(ctx context.Context, studentID int64, courseID string) ([]models.LearnerSkillStateWithSkill, error) {
	return s.repo.GetStudentSkillStates(ctx, studentID, courseID)
}

// GetCourseSkillProfile exposes mastery states + eligible content for the
// internal next-best-lesson API consumed by recommender-service.
func (s *LearningEventService) GetCourseSkillProfile(ctx context.Context, studentID, courseID int64) (*models.CourseSkillProfile, error) {
	return s.repo.GetCourseSkillProfile(ctx, studentID, courseID)
}

func (s *LearningEventService) FindPublishedContentForSkill(ctx context.Context, skillID int64, targetDifficulty float64) (*models.PersonalizedContent, error) {
	return s.repo.FindPublishedContentForSkill(ctx, skillID, targetDifficulty)
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILLS MANAGEMENT
// ══════════════════════════════════════════════════════════════════════════════

type CreateSkillRequest struct {
	Name          string   `json:"name" binding:"required"`
	Description   string   `json:"description"`
	ParentSkillID *int64   `json:"parent_skill_id"`
	Difficulty    *float64 `json:"difficulty"`
}

func (s *LearningEventService) CreateSkill(ctx context.Context, req *CreateSkillRequest) (*models.Skill, error) {
	skill := &models.Skill{
		Name:          req.Name,
		Description:   toNullString(req.Description),
		ParentSkillID: toNullInt64(req.ParentSkillID),
		Difficulty:    toNullFloat64(req.Difficulty),
	}

	if err := s.repo.CreateSkill(ctx, skill); err != nil {
		return nil, fmt.Errorf("failed to create skill: %w", err)
	}

	return skill, nil
}

func (s *LearningEventService) GetSkill(ctx context.Context, id int64) (*models.Skill, error) {
	return s.repo.GetSkillByID(ctx, id)
}

func (s *LearningEventService) ListSkills(ctx context.Context) ([]models.Skill, error) {
	return s.repo.ListSkills(ctx)
}

func (s *LearningEventService) UpdateSkill(ctx context.Context, id int64, req *CreateSkillRequest) (*models.Skill, error) {
	skill := &models.Skill{
		ID:            id,
		Name:          req.Name,
		Description:   toNullString(req.Description),
		ParentSkillID: toNullInt64(req.ParentSkillID),
		Difficulty:    toNullFloat64(req.Difficulty),
	}

	if err := s.repo.UpdateSkill(ctx, skill); err != nil {
		return nil, fmt.Errorf("failed to update skill: %w", err)
	}

	return skill, nil
}

func (s *LearningEventService) DeleteSkill(ctx context.Context, id int64) error {
	return s.repo.DeleteSkill(ctx, id)
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL PREREQUISITES
// ══════════════════════════════════════════════════════════════════════════════

type AddPrerequisiteRequest struct {
	PrerequisiteSkillID int64    `json:"prerequisite_skill_id" binding:"required"`
	Strength            *float64 `json:"strength"`
}

func (s *LearningEventService) AddPrerequisite(ctx context.Context, skillID int64, req *AddPrerequisiteRequest) (*models.SkillPrerequisite, error) {
	strength := 1.0
	if req.Strength != nil {
		strength = *req.Strength
	}

	prereq := &models.SkillPrerequisite{
		SkillID:             skillID,
		PrerequisiteSkillID: req.PrerequisiteSkillID,
		Strength:            strength,
	}

	if err := s.repo.AddPrerequisite(ctx, prereq); err != nil {
		return nil, fmt.Errorf("failed to add prerequisite: %w", err)
	}

	return prereq, nil
}

func (s *LearningEventService) GetSkillPrerequisites(ctx context.Context, skillID int64) ([]models.SkillPrerequisite, error) {
	return s.repo.GetSkillPrerequisites(ctx, skillID)
}

func (s *LearningEventService) DeletePrerequisite(ctx context.Context, skillID, prerequisiteSkillID int64) error {
	return s.repo.DeletePrerequisite(ctx, skillID, prerequisiteSkillID)
}

// ══════════════════════════════════════════════════════════════════════════════
// CONTENT SKILLS MAPPING
// ══════════════════════════════════════════════════════════════════════════════

type MapSkillRequest struct {
	SkillID    int64    `json:"skill_id" binding:"required"`
	Difficulty *float64 `json:"difficulty"`
	Weight     *float64 `json:"weight"`
}

func (s *LearningEventService) MapContentToSkill(ctx context.Context, contentID int64, req *MapSkillRequest) (*models.ContentSkill, error) {
	weight := 1.0
	if req.Weight != nil {
		weight = *req.Weight
	}

	mapping := &models.ContentSkill{
		ContentID:  contentID,
		SkillID:    req.SkillID,
		Difficulty: toNullFloat64(req.Difficulty),
		Weight:     weight,
	}

	if err := s.repo.MapContentToSkill(ctx, mapping); err != nil {
		return nil, fmt.Errorf("failed to map content to skill: %w", err)
	}

	return mapping, nil
}

func (s *LearningEventService) GetContentSkills(ctx context.Context, contentID int64) ([]models.ContentSkill, error) {
	return s.repo.GetContentSkills(ctx, contentID)
}

func (s *LearningEventService) DeleteContentSkill(ctx context.Context, contentID, skillID int64) error {
	return s.repo.DeleteContentSkill(ctx, contentID, skillID)
}

func (s *LearningEventService) MapQuestionToSkill(ctx context.Context, questionID int64, req *MapSkillRequest) (*models.QuestionSkill, error) {
	weight := 1.0
	if req.Weight != nil {
		weight = *req.Weight
	}

	mapping := &models.QuestionSkill{
		QuestionID: questionID,
		SkillID:    req.SkillID,
		Difficulty: toNullFloat64(req.Difficulty),
		Weight:     weight,
	}

	if err := s.repo.MapQuestionToSkill(ctx, mapping); err != nil {
		return nil, fmt.Errorf("failed to map question to skill: %w", err)
	}

	return mapping, nil
}

func (s *LearningEventService) GetQuestionSkills(ctx context.Context, questionID int64) ([]models.QuestionSkill, error) {
	return s.repo.GetQuestionSkills(ctx, questionID)
}

// ══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ══════════════════════════════════════════════════════════════════════════════

func toNullBool(b *bool) sql.NullBool {
	if b == nil {
		return sql.NullBool{Valid: false}
	}
	return sql.NullBool{Bool: *b, Valid: true}
}
