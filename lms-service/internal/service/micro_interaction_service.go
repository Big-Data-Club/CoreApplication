// lms-service/internal/service/micro_interaction_service.go
//
// Owns the business logic for the Quick Action Panel analytics
// pipeline:
//
//   * RecordInteraction  — synchronous: validate, persist raw row,
//                           publish Kafka event for the worker.
//   * ApplyEvent         — asynchronous worker: convert an event into
//                           a MasteryComponentDelta and upsert it.
//   * Heatmap / StudentHeatmap — read-side helpers for the analytics
//                                 endpoint.
package service

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"
)

type MicroInteractionService struct {
	repo            *repository.MicroInteractionRepository
	microLessonRepo *repository.MicroLessonRepository
}

func NewMicroInteractionService(
	repo *repository.MicroInteractionRepository,
	microLessonRepo *repository.MicroLessonRepository,
) *MicroInteractionService {
	return &MicroInteractionService{
		repo:            repo,
		microLessonRepo: microLessonRepo,
	}
}

// validActions guards the action_type CHECK constraint at the Go
// layer so we fail fast with a descriptive error instead of leaking
// a raw Postgres error to the API caller.
var validActions = map[string]struct{}{
	models.MicroActionLessonView:         {},
	models.MicroActionLessonComplete:     {},
	models.MicroActionFlashcardFlip:      {},
	models.MicroActionFlashcardRate:      {},
	models.MicroActionQuickCheckAttempt:  {},
	models.MicroActionQuickCheckCorrect:  {},
	models.MicroActionQuickCheckIncorrec: {},
	models.MicroActionAskAI:              {},
}

// RecordInteraction is the synchronous portion of the pipeline. It
// validates input, writes a raw log row, and publishes a Kafka event
// for the analytics worker. Returns the freshly-assigned interaction
// id so the FE can correlate later events.
func (s *MicroInteractionService) RecordInteraction(
	ctx context.Context,
	userID int64,
	req dto.MicroInteractionRequest,
) (*dto.MicroInteractionResponse, error) {
	if _, ok := validActions[req.ActionType]; !ok {
		return nil, fmt.Errorf("invalid action_type: %s", req.ActionType)
	}
	if req.CourseID == 0 {
		return nil, fmt.Errorf("course_id is required")
	}

	// If the FE supplied a lesson_id but no node_id, look the node up
	// from `micro_lessons` so the heatmap can attribute the interaction.
	nodeID := req.NodeID
	if nodeID == nil && req.LessonID != nil {
		if lesson, err := s.microLessonRepo.GetLesson(ctx, *req.LessonID); err == nil && lesson.NodeID.Valid {
			v := lesson.NodeID.Int64
			nodeID = &v
		}
	}

	row := &models.MicroLessonInteraction{
		UserID:     userID,
		CourseID:   req.CourseID,
		ActionType: req.ActionType,
	}
	if req.LessonID != nil {
		row.LessonID.Valid = true
		row.LessonID.Int64 = *req.LessonID
	}
	if nodeID != nil {
		row.NodeID.Valid = true
		row.NodeID.Int64 = *nodeID
	}
	if req.Score != nil {
		row.Score.Valid = true
		row.Score.Float64 = *req.Score
	}
	if req.Status != "" {
		row.Status.Valid = true
		row.Status.String = req.Status
	}
	if len(req.Payload) > 0 {
		if b, err := json.Marshal(req.Payload); err == nil {
			row.Payload = b
		}
	}

	saved, err := s.repo.Insert(ctx, row)
	if err != nil {
		return nil, err
	}

	// Fan-out async to the analytics worker. We deliberately ignore
	// publish errors here: the raw row is already durable in
	// Postgres, and a separate replay tool can backfill failed
	// publishes. Keeping the endpoint hot-path responsive matters
	// more than per-event delivery guarantees.
	event := kafka.MicroInteractionEvent{
		InteractionID: saved.ID,
		UserID:        userID,
		CourseID:      req.CourseID,
		LessonID:      req.LessonID,
		NodeID:        nodeID,
		ActionType:    req.ActionType,
		Score:         req.Score,
		Status:        req.Status,
		CreatedAt:     saved.CreatedAt,
	}

	go func() {
		bgCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		key := []byte(strconv.FormatInt(req.CourseID, 10))
		if err := kafka.PublishEvent(bgCtx, kafka.TopicMicroInteractions, key, event); err != nil {
			logger.Error(fmt.Sprintf(
				"publish micro-interaction event id=%d", saved.ID), err)
		}
	}()

	return &dto.MicroInteractionResponse{
		InteractionID: saved.ID,
		AcceptedAt:    saved.CreatedAt,
	}, nil
}

// ApplyEvent is what the analytics worker calls for every consumed
// Kafka message. It maps the action type onto a single component
// sample (formal quiz / mini quiz / completion / engagement) and
// upserts the delta.
//
// Events without a node_id are dropped — heatmap is grouped by node,
// and we don't want global noise polluting the table.
func (s *MicroInteractionService) ApplyEvent(ctx context.Context, ev kafka.MicroInteractionEvent) error {
	if ev.NodeID == nil {
		return nil
	}

	delta := repository.MasteryComponentDelta{
		UserID:   ev.UserID,
		CourseID: ev.CourseID,
		NodeID:   *ev.NodeID,
	}

	// Map action_type → component sample. Each sample is a 0.0–1.0
	// value that gets blended into the running average.
	switch ev.ActionType {
	case models.MicroActionQuickCheckAttempt:
		// score is the fractional result of the mini quiz (0.0–1.0).
		// Default 0 if the FE forgot to include a score.
		v := 0.0
		if ev.Score != nil {
			v = clamp01(*ev.Score)
		}
		delta.MiniQuizSample = &v

	case models.MicroActionQuickCheckCorrect:
		v := 1.0
		delta.MiniQuizSample = &v

	case models.MicroActionQuickCheckIncorrec:
		v := 0.0
		delta.MiniQuizSample = &v

	case models.MicroActionLessonComplete:
		v := 1.0
		delta.CompletionSample = &v

	case models.MicroActionLessonView:
		// A lesson view is "half completion" credit — encourages the
		// student even before they hit the explicit complete button.
		v := 0.5
		delta.CompletionSample = &v

	case models.MicroActionFlashcardFlip,
		models.MicroActionFlashcardRate,
		models.MicroActionAskAI:
		// Engagement signals saturate quickly: every interaction
		// counts as 1.0, the running-average smoothing in the
		// repository keeps a single binge from spiking the score.
		v := 1.0
		delta.EngagementSample = &v

	default:
		return nil
	}

	return s.repo.ApplyDelta(ctx, delta)
}

// RecordFormalQuizSample is called by the quiz-grading flow whenever a
// formal Bloom's-taxonomy quiz attempt is graded. Keeps the heatmap
// blended across all four signals.
func (s *MicroInteractionService) RecordFormalQuizSample(
	ctx context.Context,
	userID, courseID, nodeID int64,
	score float64,
) error {
	v := clamp01(score)
	return s.repo.ApplyDelta(ctx, repository.MasteryComponentDelta{
		UserID:           userID,
		CourseID:         courseID,
		NodeID:           nodeID,
		FormalQuizSample: &v,
	})
}

// Heatmap returns the class-wide composite heatmap for a course.
func (s *MicroInteractionService) Heatmap(ctx context.Context, courseID int64) (*dto.HeatmapResponse, error) {
	nodes, err := s.repo.Heatmap(ctx, courseID)
	if err != nil {
		return nil, err
	}
	return &dto.HeatmapResponse{
		CourseID: courseID,
		Weights: dto.HeatmapWeights{
			FormalQuiz: repository.WeightFormalQuiz,
			MiniQuiz:   repository.WeightMiniQuiz,
			Completion: repository.WeightCompletion,
			Engagement: repository.WeightEngagement,
		},
		Nodes: nodes,
	}, nil
}

// StudentHeatmap returns a single student's heatmap.
func (s *MicroInteractionService) StudentHeatmap(ctx context.Context, courseID, userID int64) (*dto.HeatmapResponse, error) {
	nodes, err := s.repo.StudentHeatmap(ctx, courseID, userID)
	if err != nil {
		return nil, err
	}
	return &dto.HeatmapResponse{
		CourseID: courseID,
		Weights: dto.HeatmapWeights{
			FormalQuiz: repository.WeightFormalQuiz,
			MiniQuiz:   repository.WeightMiniQuiz,
			Completion: repository.WeightCompletion,
			Engagement: repository.WeightEngagement,
		},
		Nodes: nodes,
	}, nil
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}
