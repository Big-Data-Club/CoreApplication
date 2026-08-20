package service

import (
	"context"
	"encoding/json"
	"fmt"

	"example/hello/internal/models"
	"example/hello/pkg/kafka"
)

// KafkaService wraps Kafka publishing for learning events
type KafkaService struct{}

func NewKafkaService() *KafkaService {
	return &KafkaService{}
}

// LearningEventMessage represents the Kafka message format
type LearningEventMessage struct {
	EventID        string                 `json:"event_id"`
	EventType      string                 `json:"event_type"`
	StudentID      int64                  `json:"student_id"`
	SessionID      string                 `json:"session_id,omitempty"`
	CourseID       *int64                 `json:"course_id,omitempty"`
	LessonID       *int64                 `json:"lesson_id,omitempty"`
	QuestionID     *int64                 `json:"question_id,omitempty"`
	SkillID        *int64                 `json:"skill_id,omitempty"`
	Difficulty     *float64               `json:"difficulty,omitempty"`
	Correct        *bool                  `json:"correct,omitempty"`
	AttemptNo      *int                   `json:"attempt_no,omitempty"`
	ResponseTimeMs *int64                 `json:"response_time_ms,omitempty"`
	HintCount      *int                   `json:"hint_count,omitempty"`
	Metadata       map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt      string                 `json:"created_at"`
}

// PublishLearningEvent publishes a learning event to Kafka
func (s *KafkaService) PublishLearningEvent(event *models.LearningEvent) error {
	ctx := context.Background()

	// Convert to Kafka message format
	msg := LearningEventMessage{
		EventID:   event.EventID,
		EventType: event.EventType,
		StudentID: event.StudentID,
		CreatedAt: event.CreatedAt.Format("2006-01-02T15:04:05.000Z"),
	}

	// Convert nullable fields
	if event.SessionID.Valid {
		msg.SessionID = event.SessionID.String
	}
	if event.CourseID.Valid {
		courseID := event.CourseID.Int64
		msg.CourseID = &courseID
	}
	if event.LessonID.Valid {
		lessonID := event.LessonID.Int64
		msg.LessonID = &lessonID
	}
	if event.QuestionID.Valid {
		questionID := event.QuestionID.Int64
		msg.QuestionID = &questionID
	}
	if event.SkillID.Valid {
		skillID := event.SkillID.Int64
		msg.SkillID = &skillID
	}
	if event.Difficulty.Valid {
		difficulty := event.Difficulty.Float64
		msg.Difficulty = &difficulty
	}
	if event.Correct.Valid {
		correct := event.Correct.Bool
		msg.Correct = &correct
	}
	if event.AttemptNo.Valid {
		attemptNo := int(event.AttemptNo.Int32)
		msg.AttemptNo = &attemptNo
	}
	if event.ResponseTimeMs.Valid {
		responseTimeMs := event.ResponseTimeMs.Int64
		msg.ResponseTimeMs = &responseTimeMs
	}
	if event.HintCount.Valid {
		hintCount := int(event.HintCount.Int32)
		msg.HintCount = &hintCount
	}

	// Parse metadata if present
	if event.Metadata != nil {
		var metadata map[string]interface{}
		if err := json.Unmarshal(event.Metadata, &metadata); err == nil {
			msg.Metadata = metadata
		}
	}

	// Kafka key: student_id for partitioning
	key := []byte(fmt.Sprintf("%d", event.StudentID))

	// Publish to Kafka topic
	topic := "learning-events"
	if err := kafka.PublishEvent(ctx, topic, key, msg); err != nil {
		return fmt.Errorf("failed to publish learning event: %w", err)
	}

	return nil
}
