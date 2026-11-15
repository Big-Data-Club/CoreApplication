package kafka

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	kafkago "github.com/segmentio/kafka-go"

	"example/hello/pkg/logger"
)

var ErrInvalidEvent = errors.New("invalid event")

type messageReader interface {
	FetchMessage(context.Context) (kafkago.Message, error)
	CommitMessages(context.Context, ...kafkago.Message) error
}
type deadLetterPublisher func(context.Context, kafkago.Message, error) error

// consume retries the current message before fetching the next. A partition's
// offset is never advanced over a failed handler. Invalid JSON is quarantined.
func consume(ctx context.Context, r messageReader, handle func(context.Context, []byte) error, deadLetter deadLetterPublisher) {
	for ctx.Err() == nil {
		message, err := r.FetchMessage(ctx)
		if err != nil {
			if !waitRetry(ctx, time.Second) {
				return
			}
			continue
		}
		delay := 100 * time.Millisecond
		for {
			attemptCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
			err = handle(attemptCtx, message.Value)
			cancel()
			if err == nil {
				break
			}
			var syntax *json.SyntaxError
			var typeError *json.UnmarshalTypeError
			if errors.As(err, &syntax) || errors.As(err, &typeError) || errors.Is(err, ErrInvalidEvent) {
				if err = deadLetter(ctx, message, err); err == nil {
					break
				}
			}
			logger.Error(fmt.Sprintf("Kafka retry topic=%s partition=%d offset=%d", message.Topic, message.Partition, message.Offset), err)
			if !waitRetry(ctx, delay) {
				return
			}
			if delay < 5*time.Second {
				delay *= 2
			}
		}
		for r.CommitMessages(ctx, message) != nil {
			if !waitRetry(ctx, time.Second) {
				return
			}
		}
	}
}
func waitRetry(ctx context.Context, delay time.Duration) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
func runConsumer[T any](ctx context.Context, topic, group string, handler func(context.Context, T) error) {
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		brokers = "localhost:9092"
	}
	reader := kafkago.NewReader(kafkago.ReaderConfig{Brokers: strings.Split(brokers, ","), Topic: topic, GroupID: group, MaxBytes: 10 << 20})
	defer reader.Close()
	consume(ctx, reader, func(ctx context.Context, raw []byte) error {
		var event T
		if err := json.Unmarshal(raw, &event); err != nil {
			return err
		}
		return handler(ctx, event)
	}, func(ctx context.Context, message kafkago.Message, cause error) error {
		return PublishEvent(ctx, topic+".dlq", message.Key, deadLetterEvent{message.Topic, message.Partition, message.Offset, message.Value, "invalid event schema"})
	})
}

// Base64 encoding preserves arbitrary malformed bytes without making the DLQ
// envelope invalid JSON or logging the source payload.
type deadLetterEvent struct {
	Topic     string `json:"source_topic"`
	Partition int    `json:"source_partition"`
	Offset    int64  `json:"source_offset"`
	Payload   []byte `json:"payload_base64"`
	Error     string `json:"error"`
}
