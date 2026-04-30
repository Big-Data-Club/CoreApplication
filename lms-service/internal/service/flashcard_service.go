package service

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/cache"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"

	"github.com/google/uuid"
)

type FlashcardService struct {
	flashcardRepo *repository.FlashcardRepository // Kept for compilation compatibility, but unused
	aiClient      *ai.Client
	redisCache    *cache.RedisCache
}

func NewFlashcardService(flashcardRepo *repository.FlashcardRepository, aiClient *ai.Client, redisCache *cache.RedisCache) *FlashcardService {
	return &FlashcardService{
		flashcardRepo: flashcardRepo,
		aiClient:      aiClient,
		redisCache:    redisCache,
	}
}

func (s *FlashcardService) GenerateFlashcards(ctx context.Context, studentID, courseID int64, nodeID *int64, req dto.GenerateFlashcardsRequest) (map[string]interface{}, error) {
	jobID := uuid.New().String()

	aiReq := ai.GenerateFlashcardsRequest{
		StudentID: studentID,
		CourseID:  courseID,
		NodeID:    nodeID,
		LessonID:  req.LessonID,
		ContentID: req.ContentID,
		TextChunk: req.TextChunk,
		Count:     req.Count,
	}

	payloadBytes, _ := json.Marshal(aiReq)

	event := kafka.AICommandEvent{
		JobID:       jobID,
		CommandType: "GENERATE_FLASHCARD",
		CourseID:    courseID,
		Payload:     json.RawMessage(payloadBytes),
		CreatedAt:   time.Now(),
	}

	redisPayload := map[string]interface{}{
		"job_id": jobID,
		"status": "processing",
	}
	redisData, _ := json.Marshal(redisPayload)
	err := s.redisCache.Set(ctx, "ai_job:"+jobID, redisData, 24*time.Hour)
	if err != nil {
		logger.Error("Failed to track Flashcard generation job in Redis", err)
	}

	err = kafka.PublishEvent(ctx, "lms.ai.command", []byte(jobID), event)
	if err != nil {
		logger.Error("Flashcard generation command publish failed", err)
		return nil, fmt.Errorf("failed to queue flashcard generation: %w", err)
	}

	return redisPayload, nil
}

// ListDueFlashcards calls AI service to get flashcards due today
func (s *FlashcardService) ListDueFlashcards(ctx context.Context, studentID, courseID int64) ([]dto.FlashcardResponse, error) {
	rows, err := s.aiClient.GetDueFlashcards(ctx, studentID, courseID)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch due flashcards from AI: %w", err)
	}

	return s.mapAIResultToDTO(rows), nil
}

// ReviewFlashcard processes a SM-2 quality score (0-5) via AI service
func (s *FlashcardService) ReviewFlashcard(ctx context.Context, studentID, flashcardID int64, req dto.ReviewFlashcardRequest) (*dto.ReviewFlashcardResponse, error) {
	aiReq := ai.ReviewFlashcardRequest{
		StudentID:   studentID,
		FlashcardID: flashcardID,
		Quality:     req.Quality,
	}
	resp, err := s.aiClient.ReviewFlashcard(ctx, aiReq)
	if err != nil {
		return nil, fmt.Errorf("failed to review flashcard via AI: %w", err)
	}

	result := &dto.ReviewFlashcardResponse{
		FlashcardID: flashcardID,
	}

	if v, ok := resp["easiness_factor"].(float64); ok {
		result.EasinessFactor = v
	}
	if v, ok := resp["interval_days"].(float64); ok {
		result.IntervalDays = int(v)
	}
	if v, ok := resp["repetitions"].(float64); ok {
		result.Repetitions = int(v)
	}
	if v, ok := resp["next_review_date"].(string); ok {
		if t, err := time.Parse(time.RFC3339, v); err == nil {
			result.NextReviewDate = t
		}
	}

	return result, nil
}

// BulkSaveFlashcards saves pre-generated flashcards directly without using Kafka/async
func (s *FlashcardService) BulkSaveFlashcards(ctx context.Context, studentID, courseID int64, req dto.BulkSaveFlashcardsRequest) ([]dto.FlashcardResponse, error) {
	aiReq := ai.BulkSaveFlashcardsRequest{
		StudentID:  studentID,
		CourseID:   courseID,
		NodeID:     req.NodeID,
		LessonID:   req.LessonID,
		ContentID:  req.ContentID,
		Flashcards: req.Flashcards,
	}

	resp, err := s.aiClient.BulkSaveFlashcards(ctx, aiReq)
	if err != nil {
		return nil, fmt.Errorf("failed to bulk save flashcards via AI: %w", err)
	}

	var results []dto.FlashcardResponse
	for _, fc := range resp.Flashcards {
		results = append(results, dto.FlashcardResponse{
			ID:        fc.ID,
			CourseID:  fc.CourseID,
			NodeID:    fc.NodeID,
			LessonID:  fc.LessonID,
			ContentID: fc.ContentID,
			FrontText: fc.FrontText,
			BackText:  fc.BackText,
			Status:    fc.Status,
			CreatedAt: fc.CreatedAt,
		})
	}
	return results, nil
}

// ListFlashcards returns ALL flashcards for a student+course+target via AI
func (s *FlashcardService) ListFlashcards(ctx context.Context, studentID, courseID int64, nodeID, lessonID, contentID *int64) ([]dto.FlashcardResponse, error) {
	resp, err := s.aiClient.ListFlashcards(ctx, studentID, courseID, nodeID, lessonID, contentID)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch flashcards from AI: %w", err)
	}

	var results []dto.FlashcardResponse
	for _, fc := range resp.Flashcards {
		results = append(results, dto.FlashcardResponse{
			ID:        fc.ID,
			CourseID:  fc.CourseID,
			NodeID:    fc.NodeID,
			LessonID:  fc.LessonID,
			ContentID: fc.ContentID,
			FrontText: fc.FrontText,
			BackText:  fc.BackText,
			Status:    fc.Status,
			CreatedAt: fc.CreatedAt,
		})
	}
	return results, nil
}

// Helper to map map[string]interface{} rows to dto.FlashcardResponse
func (s *FlashcardService) mapAIResultToDTO(rows []map[string]interface{}) []dto.FlashcardResponse {
	var results []dto.FlashcardResponse
	for _, r := range rows {
		item := dto.FlashcardResponse{}
		
		if v, ok := r["id"].(float64); ok {
			item.ID = int64(v)
		}
		if v, ok := r["course_id"].(float64); ok {
			item.CourseID = int64(v)
		}
		if v, ok := r["node_id"].(float64); ok {
			val := int64(v)
			item.NodeID = &val
		}
		if v, ok := r["lesson_id"].(float64); ok {
			val := int64(v)
			item.LessonID = &val
		}
		if v, ok := r["front_text"].(string); ok {
			item.FrontText = v
		}
		if v, ok := r["back_text"].(string); ok {
			item.BackText = v
		}
		if v, ok := r["status"].(string); ok {
			item.Status = v
		}
		if v, ok := r["created_at"].(string); ok {
			if t, err := time.Parse("2006-01-02T15:04:05.999999", v); err == nil {
				item.CreatedAt = t
			} else if t, err := time.Parse(time.RFC3339, v); err == nil {
				item.CreatedAt = t
			} else if t, err := time.Parse("2006-01-02T15:04:05", v); err == nil {
				item.CreatedAt = t
			}
		}
		if v, ok := r["next_review_date"].(string); ok {
			if t, err := time.Parse("2006-01-02", v); err == nil {
				item.NextReviewDate = &t
			}
		}
		if v, ok := r["easiness_factor"].(float64); ok {
			item.EasinessFactor = &v
		}
		if v, ok := r["interval_days"].(float64); ok {
			val := int(v)
			item.IntervalDays = &val
		}
		if v, ok := r["repetitions"].(float64); ok {
			val := int(v)
			item.Repetitions = &val
		}
		if v, ok := r["last_reviewed_at"].(string); ok {
			if t, err := time.Parse(time.RFC3339, v); err == nil {
				item.LastReviewedAt = &t
			}
		}

		results = append(results, item)
	}
	return results
}
