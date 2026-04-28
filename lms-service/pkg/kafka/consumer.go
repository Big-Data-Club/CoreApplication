package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"example/hello/pkg/logger"

	"github.com/segmentio/kafka-go"
)

type StatusUpdateFunc func(ctx context.Context, event ProcessDocumentStatusEvent) error

func StartConsumer(ctx context.Context, onStatusUpdate StatusUpdateFunc) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	r := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{brokers},
		Topic:   "ai.document.processed.status",
		GroupID: "lms-service-group",
	})

	defer r.Close()
	logger.Info("Kafka Consumer started for ai.document.processed.status")

	for {
		m, err := r.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Error("Failed to read kafka message", err)
			continue
		}

		var event ProcessDocumentStatusEvent
		if err := json.Unmarshal(m.Value, &event); err != nil {
			logger.Error("Failed to unmarshal kafka status event", err)
			continue
		}

		err = onStatusUpdate(ctx, event)
		if err != nil {
			logger.Error(fmt.Sprintf("Failed to process status update for content %d", event.ContentID), err)
		}
	}
}

type NodeMergedFunc func(ctx context.Context, event NodeMergedEvent) error

// StartNodeMergedConsumer subscribes to ai.graph.node_merged and rewires the
// LMS-side node_id references (micro_lessons, quiz_questions). The handler
// receives the parsed event and is responsible for the actual UPDATE.
func StartNodeMergedConsumer(ctx context.Context, onMerged NodeMergedFunc) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	r := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{brokers},
		Topic:   "ai.graph.node_merged",
		GroupID: "lms-service-graph-merged-group",
	})

	defer r.Close()
	logger.Info("Kafka Consumer started for ai.graph.node_merged")

	for {
		m, err := r.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Error("Failed to read kafka message on ai.graph.node_merged", err)
			continue
		}

		var event NodeMergedEvent
		if err := json.Unmarshal(m.Value, &event); err != nil {
			logger.Error("Failed to unmarshal NodeMergedEvent", err)
			continue
		}

		if err := onMerged(ctx, event); err != nil {
			logger.Error(fmt.Sprintf(
				"Failed to apply node-merge cascade (survivor=%d, absorbed=%d)",
				event.SurvivorID, len(event.AbsorbedIDs)), err)
		}
	}
}

type MicroInteractionFunc func(ctx context.Context, event MicroInteractionEvent) error

// StartMicroInteractionConsumer subscribes to lms.analytics.interactions
// and forwards each parsed event to the heatmap aggregator. Runs in
// its own goroutine; cancel ctx to stop.
func StartMicroInteractionConsumer(ctx context.Context, onEvent MicroInteractionFunc) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	r := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{brokers},
		Topic:   TopicMicroInteractions,
		GroupID: "lms-service-micro-interactions-group",
	})

	defer r.Close()
	logger.Info("Kafka Consumer started for " + TopicMicroInteractions)

	for {
		m, err := r.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Error("Failed to read kafka message on "+TopicMicroInteractions, err)
			continue
		}

		var event MicroInteractionEvent
		if err := json.Unmarshal(m.Value, &event); err != nil {
			logger.Error("Failed to unmarshal MicroInteractionEvent", err)
			continue
		}

		if err := onEvent(ctx, event); err != nil {
			logger.Error(fmt.Sprintf(
				"Failed to aggregate interaction id=%d action=%s",
				event.InteractionID, event.ActionType), err)
		}
	}
}

type AIJobStatusUpdateFunc func(ctx context.Context, event AIJobStatusEvent) error

func StartAIJobStatusConsumer(ctx context.Context, onStatusUpdate AIJobStatusUpdateFunc) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	r := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{brokers},
		Topic:   "ai.job.status",
		GroupID: "lms-service-ai-job-status-group",
	})

	defer r.Close()
	logger.Info("Kafka Consumer started for ai.job.status")

	for {
		m, err := r.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Error("Failed to read kafka message on ai.job.status", err)
			continue
		}

		var event AIJobStatusEvent
		if err := json.Unmarshal(m.Value, &event); err != nil {
			logger.Error("Failed to unmarshal kafka AI job status event", err)
			continue
		}

		err = onStatusUpdate(ctx, event)
		if err != nil {
			logger.Error(fmt.Sprintf("Failed to process status update for job %s", event.JobID), err)
		}
	}
}
