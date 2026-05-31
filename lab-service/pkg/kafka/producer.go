package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"lab-service/pkg/logger"

	"github.com/segmentio/kafka-go"
)

var Writer *kafka.Writer

func InitProducer() {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}

	Writer = &kafka.Writer{
		Addr:                   kafka.TCP(brokers),
		Balancer:               &kafka.Hash{},
		MaxAttempts:            5,
		AllowAutoTopicCreation: true,
	}
	logger.Info("Kafka Producer initialized")
}

func CloseProducer() {
	if Writer != nil {
		Writer.Close()
	}
}

func PublishEvent(ctx context.Context, topic string, key []byte, payload interface{}) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	msg := kafka.Message{
		Topic: topic,
		Key:   key,
		Value: data,
	}

	if err := Writer.WriteMessages(ctx, msg); err != nil {
		return fmt.Errorf("failed to publish to kafka topic %s: %w", topic, err)
	}

	logger.Info(fmt.Sprintf("Published event to topic %s with key %s", topic, string(key)))
	return nil
}
