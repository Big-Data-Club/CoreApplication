package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"lab-service/pkg/logger"

	"github.com/segmentio/kafka-go"
)

// StartJobStatusConsumer listens for job status updates from lab-worker.
func StartJobStatusConsumer(ctx context.Context, handler func(ctx context.Context, event JobStatusEvent) error) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:  []string{brokers},
		Topic:    TopicJobStatus,
		GroupID:  "lab-service-group",
		MinBytes: 1,
		MaxBytes: 10e6,
	})
	defer reader.Close()

	logger.Info(fmt.Sprintf("Kafka consumer started for topic: %s", TopicJobStatus))

	for {
		select {
		case <-ctx.Done():
			logger.Info("Kafka consumer shutting down")
			return
		default:
			msg, err := reader.ReadMessage(ctx)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				logger.Error("Failed to read Kafka message", err)
				continue
			}

			var event JobStatusEvent
			if err := json.Unmarshal(msg.Value, &event); err != nil {
				logger.Error("Failed to unmarshal job status event", err)
				continue
			}

			if err := handler(ctx, event); err != nil {
				logger.Error("Failed to handle job status event", err)
			}
		}
	}
}
