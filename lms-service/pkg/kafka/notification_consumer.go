package kafka

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"strings"
	"time"

	broker "github.com/segmentio/kafka-go"
)

// Reuse Personalize's existing notification event as an invalidation hint.
// No notification data or email work is duplicated in this consumer.
func StartNotificationHintConsumer(ctx context.Context, onTrigger func(context.Context, int64) error) {
	brokers := strings.Split(os.Getenv("KAFKA_BROKERS"), ",")
	if len(brokers) == 1 && brokers[0] == "" {
		brokers = []string{"kafka:9092"}
	}
	reader := broker.NewReader(broker.ReaderConfig{Brokers: brokers, Topic: "personalize.notification.trigger", GroupID: "lms-notification-hints-v1", StartOffset: broker.LastOffset})
	defer reader.Close()
	retry := func(action func() error) bool {
		for {
			if err := action(); err == nil {
				return true
			}
			select {
			case <-ctx.Done():
				return false
			case <-time.After(time.Second):
			}
		}
	}
	for {
		message, err := reader.FetchMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Printf("notification hint consumer: retry pending")
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
			continue
		}
		var event struct {
			UserID int64 `json:"user_id"`
		}
		if json.Unmarshal(message.Value, &event) == nil && event.UserID > 0 {
			if !retry(func() error { return onTrigger(ctx, event.UserID) }) {
				return
			}
		}
		if !retry(func() error { return reader.CommitMessages(ctx, message) }) {
			return
		}
	}
}
